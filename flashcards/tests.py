from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import FlashcardSet, Flashcard


class FlashcardSetModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="testuser", password="password")
        self.flashcard_set = FlashcardSet.objects.create(
            title="Test Set",
            description="Test Description",
            created_by=self.user
        )

    def test_flashcard_set_creation(self):
        self.assertEqual(self.flashcard_set.title, "Test Set")
        self.assertEqual(self.flashcard_set.description, "Test Description")
        self.assertEqual(self.flashcard_set.created_by, self.user)
        self.assertIsNotNone(self.flashcard_set.created_at)
        self.assertIsNotNone(self.flashcard_set.updated_at)


class FlashcardModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="testuser", password="password")
        self.flashcard_set = FlashcardSet.objects.create(
            title="Test Set",
            description="Test Description",
            created_by=self.user
        )
        self.flashcard1 = Flashcard.objects.create(
            front="Front 1", back="Back 1", flashcard_set=self.flashcard_set
        )
        self.flashcard2 = Flashcard.objects.create(
            front="Front 2", back="Back 2", flashcard_set=self.flashcard_set
        )

    def test_flashcard_creation(self):
        self.assertEqual(self.flashcard1.front, "Front 1")
        self.assertEqual(self.flashcard1.back, "Back 1")
        self.assertEqual(self.flashcard1.flashcard_set, self.flashcard_set)
        self.assertIsNotNone(self.flashcard1.created_at)

    def test_flashcard_navigation(self):
        self.assertEqual(self.flashcard1.get_next_card_in_set(), self.flashcard2)
        self.assertEqual(self.flashcard2.get_previous_card_in_set(), self.flashcard1)


class FlashcardViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="testuser", password="password")
        self.client.login(username="testuser", password="password")
        self.flashcard_set = FlashcardSet.objects.create(
            title="Test Set",
            description="Test Description",
            created_by=self.user
        )
        self.flashcard = Flashcard.objects.create(
            front="Front", back="Back", flashcard_set=self.flashcard_set
        )

    def test_index_view(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Set")

    def test_flashcard_view(self):
        response = self.client.get(reverse("flashcard-detail", args=[self.flashcard.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Front")

    def test_add_flashcard(self):
        response = self.client.post(reverse("add-flashcard", args=[self.flashcard_set.id]), {
            "front": "New Front", "back": "New Back"
        })
        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        self.assertEqual(response_json["status"], "success")
        self.assertEqual(response_json["count"], 1)
        self.assertTrue(Flashcard.objects.filter(front="New Front", back="New Back").exists())

    def test_add_flashcard_set(self):
        response = self.client.post(reverse("add-flashcard-set"), {
            "title": "New Set", "description": "New Description"
        })
        self.assertEqual(response.status_code, 200)  # No redirect anymore
        self.assertTrue(FlashcardSet.objects.filter(title="New Set").exists())

    def test_edit_flashcard(self):
        original_front = self.flashcard.front
        original_back = self.flashcard.back

        response = self.client.post(reverse("edit-flashcard", args=[self.flashcard.id]), {
            "front": "Updated Front", "back": "Updated Back"
        })
        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        self.assertTrue(response_json["success"])

        self.flashcard.refresh_from_db()
        self.assertEqual(self.flashcard.front, "Updated Front")
        self.assertEqual(self.flashcard.back, "Updated Back")
        self.assertNotEqual(self.flashcard.front, original_front)
        self.assertNotEqual(self.flashcard.back, original_back)

    def test_edit_flashcard_invalid_id(self):
        response = self.client.post(reverse("edit-flashcard", args=[42]),
                                    {"front": "Updated", "back": "Updated"})
        self.assertEqual(response.status_code, 404)

    def test_edit_flashcard_set(self):
        response = self.client.post(reverse("edit-flashcard-set", args=[self.flashcard_set.id]), {
            "title": "Updated Set Title", "description": "Updated Description"
        })
        self.assertEqual(response.status_code, 302)  # Redirect to index
        self.flashcard_set.refresh_from_db()
        self.assertEqual(self.flashcard_set.title, "Updated Set Title")
        self.assertEqual(self.flashcard_set.description, "Updated Description")

    def test_edit_flashcard_set_invalid_id(self):
        response = self.client.post(reverse("edit-flashcard-set", args=[42]),
                                    {"title": "Updated", "description": "Updated"})
        self.assertEqual(response.status_code, 404)

    def test_delete_flashcard(self):
        response = self.client.post(reverse("delete-flashcard", args=[self.flashcard.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Flashcard.objects.filter(id=self.flashcard.id).exists())

    def test_delete_flashcard_set(self):
        response = self.client.post(reverse("delete-flashcard-set", args=[self.flashcard_set.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FlashcardSet.objects.filter(id=self.flashcard_set.id).exists())
