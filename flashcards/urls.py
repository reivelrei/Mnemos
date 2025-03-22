from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path('<int:flashcard_id>/', views.flashcard_view, name='flashcard-detail'),
    path('edit-flashcard-set/<int:flashcard_set_id>/', views.edit_flashcard_set, name='edit-flashcard-set'),
]
