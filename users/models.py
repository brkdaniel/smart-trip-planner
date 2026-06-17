from django.db import models
from django.contrib.auth.models import User

class UserPreference(models.Model):
    
    PACE_CHOICES = [
        ('slow', 'Slow'),
        ('medium', 'Medium'),
        ('fast', 'Fast'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='preferences'
    )
    dietary_preference = models.CharField(
        max_length=255,
        blank=True
    )
    # No default: "unset" must be distinguishable from an explicit "3 stars",
    # otherwise every new user looks like they prefer 3-star hotels and the
    # Concierge reports it as a real preference. NULL = not specified yet.
    hotel_stars = models.IntegerField(
        null=True,
        blank=True,
    )
    travel_pace = models.CharField(
        max_length=10,
        choices=PACE_CHOICES,
        default='medium'
    )
    budget = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    interests = models.TextField(
        blank=True
    )
    # C2.1/A2.5: per-field ISO timestamp of when Agent 2 (Data Architect) set a
    # value, e.g. {"hotel_stars": "2026-06-15T...", ...}. Lets the UI show an
    # "inferred from chat" badge; cleared by Branch C when the user edits a field.
    ai_updated_fields = models.JSONField(
        default=dict,
        blank=True
    )

    class Meta:
        db_table = 'user_preference'

    def __str__(self):
        return f"{self.user.username}'s preferences"