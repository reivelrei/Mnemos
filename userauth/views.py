import logging
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()


def register_user(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 == password2:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists!")
                logger.warning(f"Username '{username}' already exists.")
                return redirect("register")
            elif User.objects.filter(email=email).exists():
                messages.error(request, "Email is already in use!")
                logger.warning(f"Email '{email}' is already in use.")
                return redirect("register")
            else:
                user = User.objects.create_user(username=username, email=email, password=password1)
                user.save()
                messages.success(request, "Account created successfully! Please log in.")
                logger.info(f"User '{username}' registered successfully.")
                return redirect("login")
        else:
            messages.error(request, "Passwords do not match!")
            return redirect("register")

    return render(request, "registration/register.html")


def login_user(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            logger.info(f"User '{username}' logged in successfully.")
            return redirect("index")
        else:
            messages.error(request, "Invalid username or password!")
            logger.warning(f"Failed login attempt for '{username}'.")
            return redirect("login")
    return render(request, "registration/login.html")


def logout_user(request):
    username = request.user.username if request.user.is_authenticated else "Anonymous"
    logout(request)
    messages.success(request, "You have been logged out!")
    logger.info(f"User '{username}' logged out successfully.")
    return redirect("login")
