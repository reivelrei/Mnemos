from django.contrib import admin

from .models import Flashcard, FlashcardSet, User

admin.site.register(Flashcard)
admin.site.register(FlashcardSet)
admin.site.register(User)