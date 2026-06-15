from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from .models import UserPreference

class PreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ['dietary_preference', 'hotel_stars', 'travel_pace', 'budget', 'interests']


class EmailChangeForm(forms.Form):
    email = forms.EmailField(
        label='Adresă email',
        widget=forms.EmailInput(attrs={
            'class': 'profile-input',
            'placeholder': 'nume@exemplu.com',
            'autocomplete': 'off',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email)
        if self.user is not None:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError('Există deja un cont cu această adresă email.')
        return email


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'profile-input',
                'autocomplete': 'off',
            })


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label='Confirmă parola',
        widget=forms.PasswordInput(attrs={
            'class': 'profile-input',
            'placeholder': 'Parola ta',
            'autocomplete': 'off',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if self.user is None or not self.user.check_password(password):
            raise forms.ValidationError('Parolă incorectă.')
        return password
