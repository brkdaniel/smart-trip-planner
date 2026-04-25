from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.chat_view, name='chat'),
    path('history/', views.history_view, name='history'),
]