
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required, require_http_methods
from .models import UserPreference

# SIGNUP
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
        
            UserPreference.objects.create(user=user)
            login(request, user)
            return redirect('chat')
    else:
        form = UserCreationForm()
    return render(request, 'users/signup.html', {'form': form})


# LOGIN
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('chat')
    else:
        form = AuthenticationForm()
    return render(request, 'users/login.html', {'form': form})



@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect('login')



@login_required
def preferences_view(request):
    preference, _ = UserPreference.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        preference.budget = request.POST.get('budget')
        preference.dietary_preference = request.POST.get('dietary_preference')
        preference.travel_pace = request.POST.get('travel_pace')
        preference.interests = request.POST.get('interests')
        preference.hotel_stars = request.POST.get('hotel_stars')
        preference.save()
        return redirect('preferences')
    return render(request, 'users/preferences.html', {'preference': preference})