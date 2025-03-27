from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth import get_user_model

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
                return redirect("register")
            elif User.objects.filter(email=email).exists():
                messages.error(request, "Email is already in use!")
                return redirect("register")
            else:
                user = User.objects.create_user(username=username, email=email, password=password1)
                user.save()
                messages.success(request, "Account created successfully! Please log in.")
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
            return redirect("index")
        else:
            messages.error(request, "Invalid username or password!")
            return redirect("login")

    return render(request, "registration/login.html")

def logout_user(request):
    logout(request)
    messages.success(request, "You have been logged out!")
    return redirect("login")
