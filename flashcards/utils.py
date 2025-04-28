import json
import os
import fitz
import requests
import logging
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import redirect
from dotenv import load_dotenv
from datetime import timedelta
from .models import Review, ReviewState
from .fsrs import FSRS

from flashcards.models import FlashcardSet, Flashcard
from .services import update_stats_after_review

logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def extract_and_validate_form_data(request, is_flashcard_set=True):
    """
    Unified form data extraction and validation for both flashcard sets and individual flashcards

    :param request: HTTP request
    :param is_flashcard_set: Boolean indicating if we're validating for a flashcard set
    :return: Dictionary of validated data or HttpResponse/JsonResponse if validation fails
    """
    data = {
        "generate_with_ai": request.POST.get("generate_with_ai") == "on",
        "topic": request.POST.get("topic", "").strip(),
        "pdf_file": request.FILES.get("pdf_file"),
        "num_flashcards": int(request.POST.get("num_flashcards", 10))
    }

    # The addition of a flashcard set is using HttpResponse
    # while the addition of "single" flashcards is using JsonResponse.
    if is_flashcard_set:
        data["title"] = request.POST.get("title", "").strip()
        data["description"] = request.POST.get("description", "").strip()
        if not data["title"] or not data["description"]:
            messages.error(request, "Title and description are required")
            logger.error("Title or description is missing in the request.")
            return redirect("index")
    else:
        data["front"] = request.POST.get("front", "").strip()
        data["back"] = request.POST.get("back", "").strip()
        if not data["generate_with_ai"] and (not data["front"] or not data["back"]):
            logger.error("Front or back is missing in the request.")
            return JsonResponse({"status": "error", "message": "Front and back are required for manual creation"},
                                status=400)

    # Common file validation
    if data["pdf_file"]:
        if data["pdf_file"].size > 5 * 1024 * 1024:  # 5MB limit
            logger.error("PDF file size exceeds limit.")
            if is_ajax(request):
                return JsonResponse({"status": "error", "message": "PDF file size must be less than 5MB"}, status=400)
            messages.error(request, "PDF file size must be less than 5MB")
            return redirect("index")

        if not data["pdf_file"].name.lower().endswith(".pdf"):
            logger.error("Uploaded file is not a valid PDF.")
            if is_ajax(request):
                return JsonResponse({"status": "error", "message": "Please upload a valid PDF file"}, status=400)
            messages.error(request, "Please upload a valid PDF file")
            return redirect("index")

    return data


def create_flashcard_set(user, form_data):
    """
    Creates a new flashcard set based on the provided form data.

    :param user: The user creating the flashcard set.
    :param form_data: A dictionary containing the form data.
    :return: The created FlashcardSet object.
    """
    return FlashcardSet.objects.create(
        title=form_data["title"],
        description=form_data["description"],
        created_by=user
    )


def handle_ai_generation(request, target_object, form_data):
    """
    Handles AI-based flashcard generation for a flashcard set or individual flashcard context.

    This function supports both standard HTTP requests and AJAX (XHR) requests, adjusting
    its response format accordingly.

    :param request: Django HTTP request object
    :param target_object: FlashcardSet instance to which flashcards will be added
    :param form_data: Validated form data with AI generation parameters
    :return: Tuple (success: bool, result: dict or None)
             If AJAX: result is a JSON-serializable dictionary
             If standard: result is None
    """
    text_input = extract_text_for_ai(request, form_data)

    if not text_input:
        error_message = "No content provided for AI generation"
        logger.error(error_message)

        if is_ajax(request):
            return False, {"status": "error", "message": error_message}

        messages.warning(request, error_message)
        return False, None

    try:
        flashcards = generate_flashcards_data_with_ai(text_input, form_data["num_flashcards"])
        created_count = create_flashcards_from_ai_data(flashcards, target_object)

        success_message = f"Successfully generated {created_count} flashcard(s)!"
        messages.success(request, success_message)

        if is_ajax(request):
            return True, {"count": created_count}  # SUCCESS — AJAX: Return flashcard count in JSON
        return True, None  # SUCCESS — HTTP: Just return success, no JSON needed

    except requests.exceptions.RequestException as e:
        error_message = f"AI service error: {e}"
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"

    logger.error(error_message)

    if is_ajax(request):
        return False, {"status": "error", "message": error_message}

    messages.error(request, error_message)
    return False, None


def extract_text_for_ai(request, form_data):
    """
    Extracts text from the provided PDF file or topic for AI processing.

    :param request: The HTTP request object.
    :param form_data: A dictionary containing the form data.
    :return: The extracted text for AI flashcard generation.
    """
    text_for_ai = form_data["topic"]

    if form_data["pdf_file"]:
        try:
            pdf_bytes = form_data["pdf_file"].read()
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text_for_ai = "\n".join([page.get_text() for page in doc])
        except Exception as e:
            print(f"Error processing PDF: {e}")
            messages.warning(request, "PDF processing failed, using topic text instead.")
            text_for_ai = form_data["topic"] if form_data["topic"] else ""

    return text_for_ai


def generate_flashcards_data_with_ai(text, num_flashcards):
    """
    Leverages the Gemini API to extract key concepts and formulate them
    into question-and-answer pairs suitable for flashcards.

    :param text: The text content to generate flashcards from.
    :param num_flashcards: The number of flashcards to generate.
    :return: A list of dictionaries, where each dictionary represents a flashcard
            with "front" and "back" keys (both strings).
    """
    prompt = f"""Create {num_flashcards} flashcards from the following content:
    {text}

    Each flashcard should have:
    - A clear, specific question (front)
    - A concise, accurate answer (back)
    - Focus on key concepts and important information

    Format response as JSON array of objects with "front" and "back" keys.
    Example: [{{"front": "What is SQL?", "back": "Structured Query Language"}}]"""

    response = requests.post(
        GEMINI_API_URL + f"?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "response_mime_type": "application/json",
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
    )
    response.raise_for_status()
    gemini_data = response.json()

    if (gemini_data.get("candidates") and
            gemini_data["candidates"][0].get("content", {}).get("parts")):
        gemini_output = gemini_data["candidates"][0]["content"]["parts"][0].get("text", "")
        flashcards_data = json.loads(gemini_output)
        if not isinstance(flashcards_data, list):
            raise ValueError("AI response format was unexpected")
        return flashcards_data

    raise ValueError("No valid response from AI service")


def create_flashcards_from_ai_data(flashcards_data, flashcard_set):
    if not isinstance(flashcards_data, list):
        raise ValueError("Expected list of flashcards from AI")

    created_count = 0
    for card_data in flashcards_data:
        try:
            if isinstance(card_data, dict) and card_data.get("front") and card_data.get("back"):
                Flashcard.objects.create(
                    front=card_data["front"].strip(),
                    back=card_data["back"].strip(),
                    flashcard_set=flashcard_set
                )
                created_count += 1
        except Exception as e:
            print(f"Error creating flashcard: {e}")
            continue

    if created_count == 0:
        raise ValueError("No valid flashcards created from AI data")
    return created_count


def is_ajax(request):
    """ Check if the request is an AJAX request. """
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def update_review_state(user, flashcard, rating):
    now = timezone.now()
    review_state, created = Review.objects.get_or_create(
        user=user,
        flashcard=flashcard,
        defaults={
            "state": ReviewState.NEW,
            "stability": 0.0, # Initial S before first calc
            "difficulty": FSRS.DEFAULT_PARAMS[4], # Initial D often set near w[4]
            "repetitions": 0,
            "lapses": 0,
            "last_review_date": None,
            "next_review_date": now # Set initial next_review_date to now to make it appear immediately
        }
    )

    # Instantiate the FSRS calculator
    fsrs_calc = FSRS()

    # Perform the FSRS calculation
    result = fsrs_calc.update_state(
        current_state=review_state.state,
        current_s=review_state.stability,
        current_d=review_state.difficulty,
        last_review_date=review_state.last_review_date,
        now=now,
        app_rating=rating
    )

    # Update the Review object with the new state
    review_state.stability = result["new_s"]
    review_state.difficulty = result["new_d"]
    review_state.state = result["new_state"]
    review_state.last_review_date = now
    review_state.next_review_date = now + timedelta(days=result["interval"])

    # Update repetitions and lapses
    review_state.repetitions += 1
    if rating == 1:
        review_state.lapses += 1

    # Store the last rating given (optional)
    # review_state.last_performance_rating = user_rating

    review_state.save()

    # Update daily stats and set progress (rating > 2, maybe change number later)
    update_stats_after_review(review_state, performance_correct=(rating > 2))

    return review_state
