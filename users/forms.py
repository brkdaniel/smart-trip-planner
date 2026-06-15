from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from .models import UserPreference

class PreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ['dietary_preference', 'hotel_stars', 'travel_pace', 'budget', 'interests']
        labels = {
            'dietary_preference': 'Restricții alimentare',
            'hotel_stars': 'Stele hotel (1–5)',
            'travel_pace': 'Ritm de călătorie',
            'budget': 'Buget (EUR)',
            'interests': 'Interese',
        }
        widgets = {
            'dietary_preference': forms.TextInput(attrs={
                'class': 'profile-input',
                'placeholder': 'ex: vegetarian, fără gluten',
            }),
            'hotel_stars': forms.NumberInput(attrs={
                'class': 'profile-input', 'min': 1, 'max': 5, 'step': 1,
            }),
            # C1.5: segmented/radio control instead of a plain dropdown.
            'travel_pace': forms.RadioSelect(),
            'budget': forms.NumberInput(attrs={
                'class': 'profile-input', 'min': 0, 'step': '0.01',
                'placeholder': 'ex: 1500',
            }),
            'interests': forms.Textarea(attrs={
                'class': 'profile-input', 'rows': 2,
                'placeholder': 'ex: muzee, plajă, viață de noapte',
            }),
        }


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
    AUTOCOMPLETE = {
        'old_password': 'current-password',
        'new_password1': 'new-password',
        'new_password2': 'new-password',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'profile-input'})
            if name in self.AUTOCOMPLETE:
                field.widget.attrs['autocomplete'] = self.AUTOCOMPLETE[name]


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label='Confirmă parola',
        widget=forms.PasswordInput(attrs={
            'class': 'profile-input',
            'placeholder': 'Parola ta',
            'autocomplete': 'current-password',
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
