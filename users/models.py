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
    hotel_stars = models.IntegerField(
        default=3
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
    onboarding_completed = models.BooleanField(
        default=False
    )

    class Meta:
        db_table = 'user_preference'

    def __str__(self):
        return f"{self.user.username}'s preferences"