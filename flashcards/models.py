from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _


class FlashcardSet(models.Model):
    title = models.CharField(max_length=50)
    description = models.CharField(max_length=255)
    created_by = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title}"


class Flashcard(models.Model):
    front = models.CharField(max_length=255)
    back = models.CharField(max_length=255)
    flashcard_set = models.ForeignKey(FlashcardSet, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Flashcard: {self.front} (Set: {self.flashcard_set.title})"

    def get_next_card_in_set(self):
        next_card = Flashcard.objects.filter(
            flashcard_set=self.flashcard_set,
            id__gt=self.id
        ).order_by("id").first()
        return next_card

    def get_previous_card_in_set(self):
        previous_card = Flashcard.objects.filter(
            flashcard_set=self.flashcard_set,
            id__lt=self.id
        ).order_by("-id").first()
        return previous_card


class Tag(models.Model):
    name = models.CharField(max_length=50)
    flashcard_sets = models.ManyToManyField(FlashcardSet)


class ReviewState(models.TextChoices):
    NEW = "NEW", _("New")
    LEARNING = "LRN", _("Learning")
    REVIEW = "REV", _("Review")
    RELEARNING = "REL", _("Relearning")


class Review(models.Model):
    flashcard = models.ForeignKey("Flashcard", on_delete=models.CASCADE)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    # FSRS Parameters - calculated after each review
    stability = models.FloatField(default=0.0)  # S value (unit: days)
    difficulty = models.FloatField(
        default=5.0)  # D value (standard FSRS scale 1-10). Initial value is often set based on first grade.
    # Consider default=0.0, maybe it makes more sense for S and D before first review

    # Scheduling & History Tracking
    repetitions = models.IntegerField(default=0)  # Number of times reviewed
    lapses = models.IntegerField(default=0)  # Track number of times user forgot (graded "Again")
    state = models.CharField(
        max_length=3,
        choices=ReviewState.choices,
        default=ReviewState.NEW
    )
    last_review_date = models.DateTimeField(null=True, blank=True)
    next_review_date = models.DateTimeField(db_index=True)  # indexed for faster lookups

    # Optional: Store the last rating given
    # last_performance_rating = models.IntegerField(null=True, blank=True) # 1-4 scale

    class Meta:
        ordering = ["next_review_date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "flashcard"], name="unique_user_flashcard_review_state")
        ]
        indexes = [
            models.Index(fields=["user", "next_review_date"]),  # Useful for fetching due cards for a user
        ]

    def __str__(self):
        return f"{self.flashcard} - Due: {self.next_review_date.strftime('%Y-%m-%d %H:%M')}"
