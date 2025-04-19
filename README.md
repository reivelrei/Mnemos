# Mnemos

A powerful and intelligent flashcard application built with Django to enhance learning through smart algorithms and AI-assisted flashcard creation.

## Features

- **User Authentication**: Secure account registration and login system.
- **Flashcard Management**:
  - Create and organize flashcard sets.
  - Add, edit, and delete flashcards within sets.
- **Smart Learning Algorithm**:
  - Optimized review scheduling to reinforce learning effectively.
- **AI-Powered Flashcard Creation**:
  - Generate flashcards sets quickly using AI to save time and improve content quality.

## Technologies Used
- Django (Python) - Backend framework
- SQLite - Database management
- Gemini API Integration - AI-assisted flashcard creation
- HTML, CSS, JavaScript - Frontend

## Installation

1. **Clone the Repository**
   ```sh
   git clone https://github.com/reivelrei/Mnemos.git
   ```
2. **Create a Virtual Environment and Install Dependencies**
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   pip install -r requirements.txt
   ```
3. **Set Up Database**
   ```sh
   python manage.py migrate
   ```
4. **Run the Development Server**
   ```sh
   python manage.py runserver
   ```
5. **Access the App**
   Open `http://127.0.0.1:8000` in your browser.

## Usage
1. Register or log in to your account.
2. Create a new flashcard set.
3. Add flashcards manually or use AI to generate them.
4. Use the smart learning feature to review and reinforce knowledge.
   
## License
This project is licensed under the MIT License.

## Contact
For any inquiries or contributions, please contact [reivelrei@gmail.com].
