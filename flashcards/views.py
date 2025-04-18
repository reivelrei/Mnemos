import os
import json
import requests
from dotenv import load_dotenv
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
        topic = request.POST.get("topic", "")
        num_flashcards = int(request.POST.get("num_flashcards", 5))

        # Create the flashcard set
        flashcard_set = FlashcardSet.objects.create(
            title=title,
            description=description,
            created_by=request.user
        )

        # If AI generation is requested
        if generate_with_ai and topic:
            try:
                # Prompt still asks for JSON, but we rely on mime type for formatting
                prompt = f"""Create {num_flashcards} flashcards about {topic}.
                Each flashcard should have a clear question (front) and concise answer (back).
                Format the response as a JSON array of objects, each with "front" and "back" keys.
                Example: [{{"front": "What is SQL?", "back": "Structured Query Language"}}]"""

                # Call Gemini API using requests
                response = requests.post(
                    GEMINI_API_URL + f"?key={GEMINI_API_KEY}",
                    headers={
                        "Content-Type": "application/json"
                    },
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

                response.raise_for_status()  # Raise an exception for HTTP errors
                gemini_data = response.json()

                # Extract the generated text
                if (gemini_data and "candidates" in gemini_data and
                        len(gemini_data["candidates"]) > 0 and
                        "content" in gemini_data["candidates"][0] and
                        "parts" in gemini_data["candidates"][0]["content"] and
                        len(gemini_data["candidates"][0]["content"]["parts"]) > 0 and
                        "text" in gemini_data["candidates"][0]["content"]["parts"][0]):

                    gemini_output = gemini_data["candidates"][0]["content"]["parts"][0]["text"]

                    # Attempt to parse the JSON response
                    try:
                        flashcards_data = json.loads(gemini_output)

                        if isinstance(flashcards_data, list):
                            for card_data in flashcards_data:
                                if isinstance(card_data, dict):
                                    Flashcard.objects.create(
                                        front=card_data.get("front", ""),
                                        back=card_data.get("back", ""),
                                        flashcard_set=flashcard_set
                                    )
                                else:
                                    print(f"Skipping non-dictionary item in flashcard list: {card_data}")
                        else:
                            # Log if the structure isn't the expected list
                            print(f"Unexpected JSON structure: Expected a list, got {type(flashcards_data)}")
                            print(f"Gemini output was: {gemini_output}")

                    except json.JSONDecodeError as e:
                        # In case the JSON is malformed or the API didn't respect the mime type for some reason
                        print(f"Error decoding JSON from Gemini output (despite requesting JSON mime type): {e}")
                        print(f"Gemini output received: {gemini_output}")
                else:
                    print("No valid text content found in Gemini API response.")
                    print(f"Full Gemini response data: {gemini_data}")

            except requests.exceptions.RequestException as e:
                print(f"Error during Gemini API request: {e}")
            except Exception as e:
                print(f"An unexpected error occurred during AI generation: {str(e)}")

        return redirect("index")

    return render(request, "index.html")


@login_required
def delete_flashcard_set(request, flashcard_set_id):
    if request.method == "POST":
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)
        flashcard_set.delete()
        return JsonResponse({"redirect_url": "/flashcards/"})

    return JsonResponse({"error": "Invalid request"}, status=400)