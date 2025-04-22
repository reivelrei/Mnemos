import json
import os
import fitz
import requests
from django.contrib import messages
from django.shortcuts import redirect
from dotenv import load_dotenv

from flashcards.models import FlashcardSet, Flashcard

load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def extract_and_validate_form_data(request):
    """
    Extracts and validates form data from the request.

    :param request: The HTTP request object containing form data.
    :return: A dictionary containing validated form data.
    """
    title = request.POST.get("title")
    description = request.POST.get("description")
    generate_with_ai = request.POST.get("generate_with_ai") == "on"
    topic = request.POST.get("topic", "").strip()
    pdf_file = request.FILES.get("pdf_file")
    num_flashcards = int(request.POST.get("num_flashcards", 10))

    # Validate title and description
    if not title or not description:
        messages.error(request, "Title and description are required")
        return redirect("index")

    # File validation
    if pdf_file:
        if pdf_file.size > 5 * 1024 * 1024:  # 5MB limit
            messages.error(request, "PDF file size must be less than 5MB")
            return redirect("index")

        if not pdf_file.name.lower().endswith(".pdf"):
            messages.error(request, "Please upload a valid PDF file")
            return redirect("index")

    return {
        "title": title,
        "description": description,
        "generate_with_ai": generate_with_ai,
        "topic": topic,
        "pdf_file": pdf_file,
        "num_flashcards": num_flashcards
    }


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


def handle_ai_generation(request, flashcard_set, form_data):
    """
    Handles the AI flashcard generation process.

    :param request: The HTTP request object.
    :param flashcard_set: The flashcard set to which the generated flashcards will be added.
    :param form_data: A dictionary containing the form data.
    :return: None
    """
    text_for_ai = extract_text_for_ai(request, form_data)

    if not text_for_ai:
        messages.warning(request, "No content provided for AI generation")
        return

    try:
        flashcards_data = generate_flashcards_data_with_ai(text_for_ai, form_data["num_flashcards"])
        created_count = create_flashcards_from_ai_data(flashcards_data, flashcard_set)
        messages.success(request, f"Successfully created {created_count} flashcards with AI")
    except requests.exceptions.RequestException as e:
        messages.error(request, f"AI service error: {str(e)}")
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {str(e)}")


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
            messages.warning(request, "PDF processing failed, using topic text only")
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
    """
    Creates flashcards from the AI-generated data.

    :param flashcards_data: A list of dictionaries containing flashcard data.
    :param flashcard_set: The flashcard set to which the flashcards will be added.
    :return: The number of flashcards created.
    """
    created_count = 0
    for card_data in flashcards_data:
        if isinstance(card_data, dict) and card_data.get("front") and card_data.get("back"):
            Flashcard.objects.create(
                front=card_data["front"],
                back=card_data["back"],
                flashcard_set=flashcard_set
            )
            created_count += 1
    return created_count