import os
from datetime import timedelta

from django.utils import timezone
from django.contrib import messages
from django.urls import reverse
from dotenv import load_dotenv
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from .fsrs import FSRS
from .models import Flashcard, FlashcardSet, Review, ReviewState
from .utils import extract_and_validate_form_data, create_flashcard_set, handle_ai_generation

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
    flashcard = get_object_or_404(Flashcard, id=flashcard_id)
    show_back = request.GET.get("show_back", False)
    user = request.user
    now = timezone.now()

    if request.method == 'POST' and 'rating' in request.POST:
        rating = int(request.POST.get('rating'))
        review_state, created = Review.objects.get_or_create(
            user=user,
            flashcard=flashcard,
            defaults={
                'state': ReviewState.NEW,
                'stability': 0.0,  # Initial S before first calc
                'difficulty': FSRS.DEFAULT_PARAMS[4],  # Initial D often set near w[4]
                'repetitions': 0,
                'lapses': 0,
                'last_review_date': None,
                # Set initial next_review_date to now to make it appear immediately
                'next_review_date': now
            }
        )

        # Instantiate the FSRS calculator
        fsrs_calc = FSRS()  # Uses default parameters

        # Perform the FSRS calculation
        result = fsrs_calc.update_state(
            current_state=review_state.state,
            current_s=review_state.stability,
            current_d=review_state.difficulty,
            last_review_date=review_state.last_review_date,
            now=now,
            app_rating=rating  # Your app's rating (e.g., 0-5)
        )

        # Update the Review object with the new state
        review_state.stability = result['new_s']
        review_state.difficulty = result['new_d']
        review_state.state = result['new_state']
        review_state.last_review_date = now
        review_state.next_review_date = now + timedelta(days=result['interval'])

        # Update repetitions and lapses
        review_state.repetitions += 1
        # if fsrs_calc._map_rating(rating) == 1:  # If rating was 'Again'
        if rating == 1:  # If rating was 'Again'
            review_state.lapses += 1

        # Store the last rating given (optional)
        # review_state.last_performance_rating = user_rating

        review_state.save()


        next_card = flashcard.get_next_card_in_set()
        if next_card:
            return redirect('flashcard-detail', flashcard_id=next_card.id)
        messages.success(request, "Everything learned!")
        return redirect('index')

    context = {
        "flashcard": flashcard,
        "show_back": show_back,
    }
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

        messages.success(request, f"Successfully updated flashcard set!")

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
        try:
            form_data = extract_and_validate_form_data(request, is_flashcard_set=False)
            if not isinstance(form_data, dict):
                return form_data  # Returns JsonResponse if validation fails

            flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id, created_by=request.user)

            if form_data["generate_with_ai"]:
                success, result = handle_ai_generation(request, flashcard_set, form_data)
                if not success:
                    return JsonResponse(result, status=400)
                return JsonResponse({"status": "success", "count": result["count"]})

            # Manual creation
            Flashcard.objects.create(
                front=form_data["front"],
                back=form_data["back"],
                flashcard_set=flashcard_set
            )
            return JsonResponse({"status": "success", "count": 1})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)


@login_required
def delete_flashcard(request, flashcard_id):
    if request.method == "POST":
        flashcard = get_object_or_404(Flashcard, id=flashcard_id)
        flashcard_set = flashcard.flashcard_set

        # Get next or previous flashcard before deleting
        previous_card = flashcard.get_previous_card_in_set()
        next_card = flashcard.get_next_card_in_set()

        flashcard.delete()
        messages.success(request, "Deleted flashcard successfully!")

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
        # Extract and validate form data
        form_data = extract_and_validate_form_data(request, is_flashcard_set=True)
        if isinstance(form_data, HttpResponse):
            return form_data  # Returns redirect if validation fails

        # Create flashcard set
        flashcard_set = create_flashcard_set(request.user, form_data)

        # Handle AI generation if requested
        if form_data["generate_with_ai"]:
            handle_ai_generation(request, flashcard_set, form_data)
        else:
            messages.success(request, "Successfully created empty flashcard set!")
        return JsonResponse({"redirect_url": reverse("index")})

    return render(request, "index.html")


@login_required
def delete_flashcard_set(request, flashcard_set_id):
    if request.method == "POST":
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)
        flashcard_set.delete()
        messages.success(request, "Deleted flashcard set successfully!")
        return JsonResponse({"redirect_url": "/flashcards/"})

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
def review_due(request):
    # Get flashcards due for review
    due_flashcards = Flashcard.objects.filter(
        review__user=request.user,
        review__next_review_date__lte=timezone.now()
    ).distinct().order_by('review__next_review_date')

    context = {
        "due_flashcards": due_flashcards,
    }
    return render(request, "flashcards/review_due.html", context)
