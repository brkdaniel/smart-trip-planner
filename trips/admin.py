from django.contrib import admin
from trips.models import ChatSession, ChatMessage

admin.site.register(ChatSession)
admin.site.register(ChatMessage)