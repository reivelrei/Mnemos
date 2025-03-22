from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Flashcard, FlashcardSet


def index(request):
    # Fetch all flashcard sets
    flashcard_sets = FlashcardSet.objects.all()

    # Pass the flashcard sets to the template
    context = {
        'flashcard_sets': flashcard_sets,
    }
    return render(request, 'flashcards/index.html', context)


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

#@login_required
def edit_flashcard_set(request, flashcard_set_id):
    if request.method == 'POST':
        # Fetch the flashcard set
        # flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id, created_by=request.user)
        flashcard_set = get_object_or_404(FlashcardSet, id=flashcard_set_id)

        # Update the title and description
        flashcard_set.title = request.POST.get('title')
        flashcard_set.description = request.POST.get('description')
        flashcard_set.save()

        # Redirect back to the index page
        return redirect('index')
    else:
        return redirect('index')