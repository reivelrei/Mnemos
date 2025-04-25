import os
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse
from dotenv import load_dotenv
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from .models import Flashcard, FlashcardSet, DailyUserStats, Review, ReviewState
from .utils import extract_and_validate_form_data, create_flashcard_set, handle_ai_generation, update_review_state

load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


@login_required
def index(request):
    user = request.user
    today = timezone.now().date()

    # Fetch all flashcard sets
    flashcard_sets = FlashcardSet.objects.all().filter(created_by=request.user)

    for flashcard_set in flashcard_sets:
        flashcards = flashcard_set.flashcard_set.all()
        total_cards = flashcards.count()

        progress_data = {
            "green": 0,
            "yellow": 0,
            "red": 0,
            "gray": 0,
        }

        if total_cards > 0:
            reviewed = Review.objects.filter(user=user, flashcard__in=flashcards)

            # Still to be figured out
            green = reviewed.filter(Q(stability__gt=20) | Q(repetitions__gt=4)).count()
            yellow = reviewed.filter(stability__lte=20, state__in=[ReviewState.REVIEW]).count()
            red = reviewed.filter(state__in=[ReviewState.LEARNING, ReviewState.RELEARNING]).count()
            reviewed_card_ids = reviewed.values_list("flashcard_id", flat=True)
            gray = total_cards - len(set(reviewed_card_ids))

            # calculate percentages
            progress_data["green"] = int((green / total_cards) * 100)
            progress_data["yellow"] = int((yellow / total_cards) * 100)
            progress_data["red"] = int((red / total_cards) * 100)
            progress_data["gray"] = max(0, 100 - (progress_data["green"] + progress_data["yellow"] + progress_data["red"]))

        flashcard_set.progress = progress_data


    # Daily stats
    today_stats = DailyUserStats.objects.filter(user=user, date=today).first()
    total_reviews = Review.objects.filter(user=user).count()
    total_cards = Flashcard.objects.filter(flashcard_set__created_by=user).count()

    # Number of consecutive days with reviews
    streak = 0
    day_cursor = today
    while DailyUserStats.objects.filter(user=user, date=day_cursor, total_reviews__gt=0).exists():
        streak += 1
        day_cursor -= timedelta(days=1)

    # Pass flashcard_sets and stats to the template
    context = {
        "flashcard_sets": flashcard_sets,
        "total_reviews": total_reviews,
        "total_cards": total_cards,
        "today_reviews": today_stats.total_reviews if today_stats else 0,
        "streak": streak,
    }
    return render(request, "flashcards/index.html", context)


@login_required
def flashcard_view(request, flashcard_id):
    flashcard = get_object_or_404(Flashcard, id=flashcard_id)
    show_back = request.GET.get("show_back", False)
    user = request.user

    if request.method == "POST" and "rating" in request.POST:
        rating = int(request.POST.get("rating"))

        update_review_state(user, flashcard, rating)

        next_card = flashcard.get_next_card_in_set()
        if next_card:
            return redirect("flashcard-detail", flashcard_id=next_card.id)
        messages.success(request, "Everything learned!")
        return redirect("index")

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
    """
    Displays Flashcard Sets that have cards due for review for the current user.
    """
    now = timezone.now()
    user = request.user

    # Find sets that have at least one flashcard with a review due for this user
    due_sets = FlashcardSet.objects.filter(
        created_by=user,  # Assuming FlashcardSet is linked to the user
        flashcard__review__user=user,
        flashcard__review__next_review_date__lte=now
    ).annotate(
        # Count the number of *due* flashcards within each set for this user
        due_flashcard_count=Count(
            "flashcard",
            filter=Q(flashcard__review__user=user, flashcard__review__next_review_date__lte=now)
        )
    ).filter(
        # Ensure we only list sets that actually have due cards
        due_flashcard_count__gt=0
    ).distinct().order_by("title")  # Order sets alphabetically by title

    context = {
        "due_sets": due_sets,
    }
    return render(request, "flashcards/review_due.html", context)


@login_required
def start_set_review_session(request, set_id):
    """
    Initializes a review session for due cards within a specific set.
    Stores the list of due card IDs in the session and redirects to the first card.
    """
    now = timezone.now()
    user = request.user
    flashcard_set = get_object_or_404(FlashcardSet, id=set_id, created_by=user)

    # Get IDs of flashcards in this set that are due for this user
    due_card_ids = list(Flashcard.objects.filter(
        flashcard_set=flashcard_set,
        review__user=user,
        review__next_review_date__lte=now
    ).order_by("review__next_review_date", "id").values_list("id", flat=True))

    if not due_card_ids:
        messages.info(request, f"No cards currently due for review in '{flashcard_set.title}'.")
        return redirect("review-due")  # Redirect back to the due sets list

    # Store the list of IDs and the set ID in the session
    request.session["due_review_set_id"] = set_id
    request.session["due_review_ids"] = due_card_ids

    # Redirect to the review view for the first card in the list
    first_card_id = due_card_ids[0]
    return redirect("review-due-card", flashcard_id=first_card_id)


@login_required
def review_due_card_view(request, flashcard_id):
    """
    Handles the display and rating submission for a card within a 'due review' session.
    Uses the session to find the next card.
    """
    # Ensure we are in a review session
    if "due_review_ids" not in request.session or not request.session["due_review_ids"]:
        messages.warning(request, "Review session not found or ended. Redirecting.")
        # Clear potentially lingering session variable if list is empty
        request.session.pop("due_review_set_id", None)
        request.session.pop("due_review_ids", None)
        return redirect("review-due")  # Or 'index'

    current_card_id = flashcard_id
    due_ids = request.session["due_review_ids"]
    set_id = request.session["due_review_set_id"]

    # Verify the requested card is actually part of the current session list
    # (Prevents accessing cards not in the current due queue via URL manipulation)
    # Convert due_ids elements to int if they aren't already (session might store strings)
    if current_card_id not in [int(id_val) for id_val in due_ids]:
        messages.error(request, "Invalid card requested for this review session.")
        # Clear session and redirect
        request.session.pop("due_review_set_id", None)
        request.session.pop("due_review_ids", None)
        return redirect("review-due")

    flashcard = get_object_or_404(Flashcard, id=current_card_id)
    show_back = request.GET.get("show_back", False)
    user = request.user

    if request.method == "POST" and "rating" in request.POST:
        rating = int(request.POST.get("rating"))

        update_review_state(user, flashcard, rating)

        # --- Session Logic for Next Card ---
        # Remove the just reviewed card ID (convert to int for comparison)
        try:
            # Ensure we are working with integers
            current_due_ids_int = [int(id_val) for id_val in request.session.get("due_review_ids", [])]
            current_due_ids_int.remove(current_card_id)
            request.session["due_review_ids"] = current_due_ids_int  # Store updated list back
        except ValueError:
            # Should not happen if validation above worked, but handle defensively
            pass  # Card already removed or wasn't there

        # Find the next card ID from the updated list in the session
        remaining_ids = request.session.get("due_review_ids", [])

        if remaining_ids:
            next_card_id = remaining_ids[0]  # Get the next one in the pre-ordered list
            return redirect("review-due-card", flashcard_id=next_card_id)
        else:
            # No more cards left in this session
            messages.success(request, f"Review complete for set '{flashcard.flashcard_set.title}'!")
            # Clear session variables
            request.session.pop("due_review_set_id", None)
            request.session.pop("due_review_ids", None)
            return redirect("review-due")  # Go back to the list of due sets

    # --- GET Request or Initial Load ---
    context = {
        "flashcard": flashcard,
        "show_back": show_back,
        "is_review_session": True,  # Flag for the template (optional)
        "remaining_in_session": len(request.session.get("due_review_ids", []))  # How many left (optional)
    }
    # Reuse the same detail template, potentially adjusting based on 'is_review_session'
    return render(request, "flashcards/flashcard_detail.html", context)
