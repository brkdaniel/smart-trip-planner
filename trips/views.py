from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ChatSession, ChatMessage
# Importam si preferintele pentru a le putea citi/actualiza
from users.models import UserPreference 
# Importam orchestratorul care va gestiona logica AI
from agents.orchestrator import handle_user_message

@login_required
def chat_view(request, session_id=None):
    # 1. Pregatim sidebar-ul: toate sesiunile userului, cele mai recente sus
    # Nota: Daca nu ai adaugat 'updated_at' in modele, foloseste 'created_at'
    sessions = ChatSession.objects.filter(user=request.user).order_by('-created_at')
    
    current_session = None
    messages = []

    # 2. Daca avem un session_id in URL, incarcam acea conversatie
    if session_id:
        current_session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        # Tiebreak by id so two messages saved in the same instant keep insertion
        # order (matches the orchestrator's '-sent_at', '-id' ordering).
        messages = current_session.messages.all().order_by('sent_at', 'id')

    # 3. Procesarea unui mesaj nou (POST)
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        prompt = request.POST.get('prompt')
        if not prompt or not prompt.strip():
            if is_ajax:
                return JsonResponse({
                    "session_id": current_session.id if current_session else None,
                    "message": None,
                    "error": "Prompt cannot be empty."
                }, status=400)
            if session_id:
                return redirect('chat_with_session', session_id=session_id)
            return redirect('chat')

        # A. Daca nu suntem intr-o sesiune (e chat nou), o cream
        if not current_session:
            # Titlu temporar din primul mesaj. Adăugăm "..." doar dacă a fost
            # trunchiat — la fel ca logica din sidebar (chat.js addNewSessionToSidebar).
            title = prompt[:30] + "..." if len(prompt) > 30 else prompt
            current_session = ChatSession.objects.create(
                user=request.user,
                title=title,
                status='pending'
            )

        # B. Salvam mesajul utilizatorului
        ChatMessage.objects.create(
            session=current_session,
            role='user',
            content=prompt
        )

        # 1. Citim preferintele din DB (invizibil)
        prefs, _ = UserPreference.objects.get_or_create(user=request.user)

        # 2. Apelam orchestratorul
        ai_response = handle_user_message(prompt, current_session, request.user)

        # D. Salvare raspuns AI
        ai_msg = ChatMessage.objects.create(
            session=current_session,
            role='assistant',
            content=ai_response
        )

        current_session.status = 'completed'
        current_session.save()

        if is_ajax:
            return JsonResponse({
                "session_id": current_session.id,
                "message": {
                    "role": ai_msg.role,
                    "content": ai_msg.content,
                    "sent_at": ai_msg.sent_at.isoformat()
                },
                "error": None
            })

        return redirect('chat_with_session', session_id=current_session.id)

    # 4. Randam pagina cu toate datele necesare
    # C2.5: preferintele pentru un mesaj de bun venit personalizat in empty-state
    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    return render(request, 'html/chat.html', {
        'sessions': sessions,           # Pentru sidebar
        'current_session': current_session, # Pentru a sti ce chat e activ
        'messages': messages,           # Mesajele din chat-ul selectat
        'preferences': prefs,           # Pentru welcome state-ul personalizat
    })


@login_required
def trip_history(request):
    """C3.1/C3.2: list the user's chat sessions with a preview of the first message."""
    sessions = (
        ChatSession.objects
        .filter(user=request.user)
        .annotate(message_count=Count('messages'))
        .order_by('-created_at')
    )
    # C3.2: attach the first user message as a preview snippet for each card.
    for session in sessions:
        first = session.messages.filter(role='user').order_by('sent_at').first()
        session.preview = first.content if first else ''

    return render(request, 'html/trip_history.html', {
        'sessions': sessions,
        'active_section': 'trips',
    })


@login_required
@require_POST
def delete_session(request, session_id):
    """B3.3: delete a chat session owned by the current user."""
    session = get_object_or_404(ChatSession, id=session_id, user=request.user)
    session.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({"deleted": True, "session_id": session_id})

    return redirect('chat')


@login_required
@require_POST
def rename_session(request, session_id):
    """B3.4: rename a chat session owned by the current user."""
    session = get_object_or_404(ChatSession, id=session_id, user=request.user)
    new_title = (request.POST.get('title') or '').strip()

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not new_title:
        if is_ajax:
            return JsonResponse(
                {"renamed": False, "error": "Titlul nu poate fi gol."},
                status=400,
            )
        return redirect('chat_with_session', session_id=session_id)

    session.title = new_title[:255]
    session.save()

    if is_ajax:
        return JsonResponse({
            "renamed": True,
            "session_id": session.id,
            "title": session.title,
        })

    return redirect('chat_with_session', session_id=session_id)