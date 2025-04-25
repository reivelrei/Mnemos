from datetime import datetime
from django.utils.timezone import now
from .models import DailyUserStats, FlashcardSetProgress, Review

def update_stats_after_review(review: Review, performance_correct: bool = True):
    """
    Call this after a Review is saved. Optionally pass whether the answer was correct (if you're tracking it).
    """
    today = now().date()

    # DAILY STATS
    daily_stats, _ = DailyUserStats.objects.get_or_create(
        user=review.user,
        date=today,
    )

    daily_stats.total_reviews += 1

    if performance_correct:
        daily_stats.correct_reviews += 1

    if review.repetitions == 1:
        daily_stats.new_cards_studied += 1

    # review.stability > 20, maybe change number later
    if review.stability > 20:
        daily_stats.cards_mastered += 1

    daily_stats.save()

    # SET PROGRESS
    flashcard_set = review.flashcard.flashcard_set
    set_progress, _ = FlashcardSetProgress.objects.get_or_create(
        user=review.user,
        flashcard_set=flashcard_set
    )

    set_progress.last_reviewed = now()

    # Update total cards
    total_cards = flashcard_set.flashcard_set.all().count()
    set_progress.total_cards = total_cards

    # Count reviewed cards
    reviewed_cards = Review.objects.filter(
        user=review.user,
        flashcard__flashcard_set=flashcard_set
    ).count()

    set_progress.cards_reviewed = reviewed_cards

    # Count mastered cards
    mastered_cards = Review.objects.filter(
        user=review.user,
        flashcard__flashcard_set=flashcard_set,
        stability__gt=20  # maybe change number later
    ).count()

    set_progress.cards_mastered = mastered_cards

    set_progress.save()
