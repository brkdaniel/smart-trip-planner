from django import forms
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'autocomplete': 'off',
    }))

    class Meta(UserCreationForm.Meta):
        fields = ('username', 'email')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            return redirect('chat')
    else:
        form = SignupForm()
    return render(request, 'html/signup.html', {'form': form})



def login_view(request):
    next_url = request.POST.get('next') or request.GET.get('next') or ''

    def _authenticate_by_email(email, password):
        user = User.objects.filter(email__iexact=email).first()
        if user and user.check_password(password):
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



@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect('login')