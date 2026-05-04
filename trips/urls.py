import django
from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.chat_view, name='chat'),
    path('chat/<int:session_id>/', views.chat_view, name='chat_with_session'),
]