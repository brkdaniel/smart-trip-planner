from django import forms
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from .models import UserPreference
from .forms import (
    PreferenceForm,
    EmailChangeForm,
    StyledPasswordChangeForm,
    DeleteAccountForm,
)


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'autocomplete': 'off',
    }))

    class Meta(UserCreationForm.Meta):
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Există deja un cont cu această adresă email.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'signup-input',
            'placeholder': 'Username',
        })
        self.fields['email'].widget.attrs.update({
            'class': 'signup-input',
            'placeholder': 'Adresă email',
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'signup-input',
            'placeholder': 'Parolă',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'signup-input',
            'placeholder': 'Confirmă parola',
        })
        self.fields['username'].widget.attrs.update({
            'autocomplete': 'off',
        })
        self.fields['email'].widget.attrs.update({
            'autocomplete': 'off',
        })
        self.fields['password1'].widget.attrs.update({
            'autocomplete': 'new-password',
        })
        self.fields['password2'].widget.attrs.update({
            'autocomplete': 'new-password',
        })


class LoginForm(forms.Form):
    email = forms.EmailField(label='Adresă email')
    password = forms.CharField(
        label='Parolă',
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'off',
        }),
    )

    def style_fields(self):
        self.fields['email'].widget.attrs.update({
            'class': 'login-input',
            'placeholder': 'Adresă email',
            'autocomplete': 'off',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'login-input',
            'placeholder': 'Parolă',
            'autocomplete': 'off',
        })
        return self





def home_view(request):
    return render(request, 'html/home.html')


def signup_view(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(f"{reverse('preferences')}?onboarding=1")
    else:
        form = SignupForm()
    return render(request, 'html/signup.html', {'form': form})



def login_view(request):
    next_url = request.POST.get('next') or request.GET.get('next') or ''

    def _authenticate_by_email(email, password):
        users = list(User.objects.filter(email__iexact=email)[:2])
        if len(users) != 1:
            return None

        user = users[0]
        if user.check_password(password):
            return user
        return None

    if request.method == 'POST':
        form = LoginForm(request.POST).style_fields()
        if form.is_valid():
            user = _authenticate_by_email(
                form.cleaned_data['email'],
                form.cleaned_data['password'],
            )
            if user is None:
                form.add_error(None, 'Email sau parolă invalide.')
            else:
                login(request, user)
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect('chat')
    else:
        form = LoginForm().style_fields()
    return render(request, 'html/login.html', {
        'form': form,
        'next': next_url,
    })
@login_required
def profile_view(request):
    return redirect('preferences')


@login_required
def preferences_view(request):
    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    onboarding = request.GET.get('onboarding') == '1'

    if request.method == 'POST':
        form = PreferenceForm(request.POST, instance=prefs)
        if form.is_valid():
            form.save()
            if onboarding:
                return redirect('chat')
            messages.success(request, 'Preferințele au fost salvate.')
            return redirect('preferences')
    else:
        form = PreferenceForm(instance=prefs)

    return render(request, 'html/profile_preferences.html', {
        'form': form,
        'active_section': 'preferences',
        'onboarding': onboarding,
    })


@login_required
def change_email_view(request):
    if request.method == 'POST':
        form = EmailChangeForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.email = form.cleaned_data['email']
            request.user.save(update_fields=['email'])
            messages.success(request, 'Adresa de email a fost actualizată.')
            return redirect('change_email')
    else:
        form = EmailChangeForm(user=request.user, initial={'email': request.user.email})

    return render(request, 'html/profile_email.html', {
        'form': form,
        'active_section': 'email',
    })


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = StyledPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Parola a fost schimbată.')
            return redirect('change_password')
    else:
        form = StyledPasswordChangeForm(request.user)

    return render(request, 'html/profile_password.html', {
        'form': form,
        'active_section': 'password',
    })


@login_required
def delete_account_view(request):
    if request.method == 'POST':
        form = DeleteAccountForm(request.POST, user=request.user)
        if form.is_valid():
            user = request.user
            logout(request)
            user.delete()
            return redirect('home')
    else:
        form = DeleteAccountForm(user=request.user)

    return render(request, 'html/profile_delete.html', {
        'form': form,
        'active_section': 'delete',
    })


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect('login')