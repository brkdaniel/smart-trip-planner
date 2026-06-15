from django import forms
from .models import UserPreference

class PreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ['dietary_preference', 'hotel_stars', 'travel_pace', 'budget', 'interests']