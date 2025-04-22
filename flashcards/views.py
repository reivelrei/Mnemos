import os
import json
import requests
import fitz
from dotenv import load_dotenv
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from .models import Flashcard, FlashcardSet

load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@login_required
def index(request):
    # Fetch all flashcard sets
    flashcard_sets = FlashcardSet.objects.all().filter(created_by=request.user)

    # Pass the flashcard sets to the template
    context = {
        "flashcard_sets": flashcard_sets,
    }
    return render(request, "flashcards/index.html", context)


@login_required
def flashcard_view(request, flashcard_id):
    # Fetch the flashcard object or return a 404 error if not found
    flashcard = get_object_or_404(Flashcard, id=flashcard_id)

    # Check if the user wants to see the back of the card (via a query parameter)
    show_back = request.GET.get("show_back", False)

    # Prepare the context to pass to the template
    context = {
        "flashcard": flashcard,
        "show_back": show_back,
    }

    # Render the template with the context
    return render(request, "flashcards/flashcard_detail.html", context)


@login_required
def edit_flashcard_set(request, flashcard_set_id):
    if request.method == "POST":
        # Fetch the flashcard set
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id, created_by=request.user)

        # Update the title and description
        flashcard_set.title = request.POST.get("title")
        flashcard_set.description = request.POST.get("description")
        flashcard_set.save()

        return redirect("index")
    else:
        return redirect("index")


@login_required
def edit_flashcard(request, flashcard_id):
    if request.method == "POST":
        flashcard = get_object_or_404(Flashcard, id=flashcard_id)

        flashcard.front = request.POST.get("front")
        flashcard.back = request.POST.get("back")
        flashcard.save()

        # Return JSON response instead of redirecting
        return JsonResponse({"success": True, "front": flashcard.front, "back": flashcard.back})

    return JsonResponse({"success": False}, status=400)


@login_required
def add_flashcard(request, flashcard_set_id):
    if request.method == "POST":
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)

        # Get form data
        front = request.POST.get("front")
        back = request.POST.get("back")

        # Create and save new flashcard
        flashcard = Flashcard.objects.create(
            front=front,
            back=back,
            flashcard_set=flashcard_set
        )

        # Return JSON response instead of redirecting
        return JsonResponse({
            "success": True,
            "flashcard": {
                "front": flashcard.front,
                "back": flashcard.back
            }
        })

    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


@login_required
def delete_flashcard(request, flashcard_id):
    if request.method == "POST":
        flashcard = get_object_or_404(Flashcard, id=flashcard_id)
        flashcard_set = flashcard.flashcard_set

        # Get next or previous flashcard before deleting
        previous_card = flashcard.get_previous_card_in_set()
        next_card = flashcard.get_next_card_in_set()

        flashcard.delete()

        # Check if there are any flashcards left in the set
        remaining_flashcards = Flashcard.objects.filter(flashcard_set=flashcard_set)

        if not remaining_flashcards.exists():
            return JsonResponse({"redirect_url": "/flashcards/"})  # Redirect to flashcards if set is empty
        elif next_card and Flashcard.objects.filter(id=next_card.id).exists():
            return JsonResponse({"redirect_url": f"/flashcards/{next_card.id}/"})  # Redirect to next
        elif previous_card and Flashcard.objects.filter(id=previous_card.id).exists():
            return JsonResponse({"redirect_url": f"/flashcards/{previous_card.id}/"})  # Redirect to previous
        else:
            return JsonResponse({"redirect_url": "/flashcards/"})  # Fallback to flashcards

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def add_flashcard_set(request):
    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        generate_with_ai = request.POST.get("generate_with_ai") == "on"
        topic = request.POST.get("topic", "").strip()
        pdf_file = request.FILES.get("pdf_file")
        num_flashcards = int(request.POST.get("num_flashcards", 10))

        # Basic validation
        if not title or not description:
            messages.error(request, "Title and description are required")
            return redirect("index")

        # File validation
        if pdf_file:
            if pdf_file.size > 5 * 1024 * 1024:  # 5MB limit
                messages.error(request, "PDF file size must be less than 5MB")
                return redirect("index")

            if not pdf_file.name.lower().endswith('.pdf'):
                messages.error(request, "Please upload a valid PDF file")
                return redirect("index")

        # Create the flashcard set
        flashcard_set = FlashcardSet.objects.create(
            title=title,
            description=description,
            created_by=request.user
        )

        # AI Flashcard Generation Logic
        if generate_with_ai:
            text_for_ai = topic  # Default to topic

            # Process PDF if uploaded
            if pdf_file:
                try:
                    pdf_bytes = pdf_file.read()
                    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                        text_for_ai = "\n".join([page.get_text() for page in doc])
                except Exception as e:
                    print(f"Error processing PDF: {e}")
                    messages.warning(request, "PDF processing failed, using topic text only")
                    text_for_ai = topic if topic else ""

            # Only proceed if we have content to generate from
            if text_for_ai:
                try:
                    prompt = f"""Create {num_flashcards} flashcards from the following content:
                    {text_for_ai}

                    Each flashcard should have:
                    - A clear, specific question (front)
                    - A concise, accurate answer (back)
                    - Focus on key concepts and important information

                    Format response as JSON array of objects with "front" and "back" keys.
                    Example: [{{"front": "What is SQL?", "back": "Structured Query Language"}}]"""

                    # Call Gemini API
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

                    # Process API response
                    if (gemini_data.get("candidates") and
                            gemini_data["candidates"][0].get("content", {}).get("parts")):

                        gemini_output = gemini_data["candidates"][0]["content"]["parts"][0].get("text", "")

                        try:
                            flashcards_data = json.loads(gemini_output)
                            if isinstance(flashcards_data, list):
                                created_count = 0
                                for card_data in flashcards_data:
                                    if isinstance(card_data, dict) and card_data.get("front") and card_data.get("back"):
                                        Flashcard.objects.create(
                                            front=card_data["front"],
                                            back=card_data["back"],
                                            flashcard_set=flashcard_set
                                        )
                                        created_count += 1

                                messages.success(request, f"Successfully created {created_count} flashcards with AI")
                            else:
                                messages.warning(request, "AI response format was unexpected")
                        except json.JSONDecodeError:
                            messages.warning(request, "Could not parse AI response")
                    else:
                        messages.warning(request, "No valid response from AI service")

                except requests.exceptions.RequestException as e:
                    messages.error(request, f"AI service error: {str(e)}")
                except Exception as e:
                    messages.error(request, f"An unexpected error occurred: {str(e)}")
            else:
                messages.warning(request, "No content provided for AI generation")

        return redirect("index")

    return render(request, "index.html")


@login_required
def delete_flashcard_set(request, flashcard_set_id):
    if request.method == "POST":
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)
        flashcard_set.delete()
        return JsonResponse({"redirect_url": "/flashcards/"})

    return JsonResponse({"error": "Invalid request"}, status=400)
