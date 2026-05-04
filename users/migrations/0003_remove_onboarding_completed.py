from django.db import migrations



class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_userpreference_onboarding_completed'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userpreference',
            name='onboarding_completed',
        ),
    ]
    