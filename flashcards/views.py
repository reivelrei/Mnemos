from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from .models import Flashcard, FlashcardSet


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
        if title and description:
            FlashcardSet.objects.create(
                title=title,
                description=description,
                created_by=request.user
            )
        return redirect("index")  # Change to your actual view name
    return render(request, "index.html")


@login_required
def delete_flashcard_set(request, flashcard_set_id):
    if request.method == "POST":
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)
        flashcard_set.delete()
        return JsonResponse({"redirect_url": "/flashcards/"})

    return JsonResponse({"error": "Invalid request"}, status=400)