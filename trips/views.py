from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import ChatSession, ChatMessage


@login_required
def chat_view(request):
    if request.method == 'POST':
        prompt = request.POST.get('prompt')
        session = ChatSession.objects.create(
            user=request.user,
            title=prompt[:50],
            status='pending'
        )
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=prompt
        )
        # Here you would integrate with the AI service to get a response and save it as a ChatMessage
        session.status = 'completed'
        session.save()
        return redirect('history')
    return render(request, 'trips/chat.html')


@login_required
def history_view(request):
    sessions = ChatSession.objects.filter(
        user=request.user
    ).order_by('-created_at')
    return render(request, 'trips/history.html', {'sessions': sessions})