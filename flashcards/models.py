from django.db import models

class User(models.Model):
    username = models.CharField(max_length=50)
    password = models.CharField(max_length=50)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class FlashcardSet(models.Model):
    title = models.CharField(max_length=50)
    description = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
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
        ).order_by('id').first()
        return next_card

    def get_previous_card_in_set(self):
        previous_card = Flashcard.objects.filter(
            flashcard_set=self.flashcard_set,
            id__lt=self.id
        ).order_by('-id').first()
        return previous_card

class Tag(models.Model):
    name = models.CharField(max_length=50)
    flashcard_sets = models.ManyToManyField(FlashcardSet)