
from django import forms
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .models import UserPreference


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            'budget',
            'dietary_preference',
            'travel_pace',
            'interests',
            'hotel_stars',
        ]


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



def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
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
        form = UserPreferenceForm(request.POST, instance=preference)
        if form.is_valid():
            form.save()
            return redirect('preferences')
    else:
        form = UserPreferenceForm(instance=preference)

    return render(request, 'users/preferences.html', {
        'preference': preference,
        'form': form,
    })