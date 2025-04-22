import json
import os
import fitz
import requests
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from dotenv import load_dotenv

from flashcards.models import FlashcardSet, Flashcard

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

    # Field-specific validation
    if is_flashcard_set:
        data["title"] = request.POST.get("title", "").strip()
        data["description"] = request.POST.get("description", "").strip()
        if not data["title"] or not data["description"]:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({"status": "error", "message": "Title and description are required"}, status=400)
            messages.error(request, "Title and description are required")
            return redirect("index")
    else:
        data["front"] = request.POST.get("front", "").strip()
        data["back"] = request.POST.get("back", "").strip()
        if not data["generate_with_ai"] and (not data["front"] or not data["back"]):
            return JsonResponse({"status": "error", "message": "Front and back are required for manual creation"},
                                status=400)

    # Common file validation
    if data["pdf_file"]:
        if data["pdf_file"].size > 2.5 * 1024 * 1024:  # 2.5MB limit
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({"status": "error", "message": "PDF file size must be less than 5MB"}, status=400)
            messages.error(request, "PDF file size must be less than 5MB")
            return redirect("index")

        if not data["pdf_file"].name.lower().endswith(".pdf"):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
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


def handle_ai_generation(request, target_object, form_data, is_flashcard_set=True):
    """
    Unified AI generation handler for both flashcard sets and individual flashcards

    :param request: HTTP request
    :param target_object: Either FlashcardSet or Flashcard object
    :param form_data: Validated form data
    :param is_flashcard_set: Boolean indicating the target type
    :return: Tuple of (success_status, result) where result is either count or flashcard data
    """
    text_for_ai = extract_text_for_ai(request, form_data)

    if not text_for_ai:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return (False, {"status": "error", "message": "No content provided for AI generation"})
        messages.warning(request, "No content provided for AI generation")
        return (False, None)

    try:
        flashcards_data = generate_flashcards_data_with_ai(text_for_ai, form_data["num_flashcards"])

        if is_flashcard_set:
            created_count = create_flashcards_from_ai_data(flashcards_data, target_object)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return (True, {"count": created_count})
            messages.success(request, f"Successfully created {created_count} flashcards with AI")
            return (True, None)
        else:
            create_flashcards_from_ai_data(flashcards_data, target_object)
            return (True, {"count": len(flashcards_data)})

    except requests.exceptions.RequestException as e:
        error_msg = f"AI service error: {str(e)}"
    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return (False, {"status": "error", "message": error_msg})
    messages.error(request, error_msg)
    return (False, None)



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