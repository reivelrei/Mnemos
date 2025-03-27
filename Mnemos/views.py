from django.shortcuts import redirect

def home(request):
    if request.user.is_authenticated:
        return redirect("index")
    else:
        return redirect("login")
