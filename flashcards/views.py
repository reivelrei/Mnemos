from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from .models import Flashcard, FlashcardSet


@login_required
def index(request):
    # Fetch all flashcard sets
    flashcard_sets = FlashcardSet.objects.all()

    # Pass the flashcard sets to the template
    context = {
        'flashcard_sets': flashcard_sets,
    }
    return render(request, 'flashcards/index.html', context)

@login_required
def flashcard_view(request, flashcard_id):
    # Fetch the flashcard object or return a 404 error if not found
    flashcard = get_object_or_404(Flashcard, id=flashcard_id)

    # Check if the user wants to see the back of the card (via a query parameter)
    show_back = request.GET.get('show_back', False)

    # Prepare the context to pass to the template
    context = {
        'flashcard': flashcard,
        'show_back': show_back,
    }

    # Render the template with the context
    return render(request, 'flashcards/flashcard_detail.html', context)

@login_required
def edit_flashcard_set(request, flashcard_set_id):
    if request.method == 'POST':
        # Fetch the flashcard set
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id, created_by=request.user)
        #flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)

        # Update the title and description
        flashcard_set.title = request.POST.get('title')
        flashcard_set.description = request.POST.get('description')
        flashcard_set.save()

        # Redirect back to the index page
        return redirect('index')
    else:
        return redirect('index')


@login_required
def add_flashcard(request, flashcard_set_id):
    if request.method == 'POST':
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)

        # Get form data
        front = request.POST.get('front')
        back = request.POST.get('back')

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
