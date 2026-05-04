from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import ChatSession, ChatMessage
# Importam si preferintele pentru a le putea citi/actualiza
from users.models import UserPreference 

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
        messages = current_session.messages.all().order_by('sent_at')

    # 3. Procesarea unui mesaj nou (POST)
    if request.method == 'POST':
        prompt = request.POST.get('prompt')
        if not prompt or not prompt.strip():
            if session_id:
                return redirect('chat_with_session', session_id=session_id)
            return redirect('chat')

        # A. Daca nu suntem intr-o sesiune (e chat nou), o cream
        if not current_session:
            current_session = ChatSession.objects.create(
                user=request.user,
                title=prompt[:30] + "...", # Titlu temporar din primul mesaj
                status='pending'
            )

        # B. Salvam mesajul utilizatorului
        ChatMessage.objects.create(
            session=current_session,
            role='user',
            content=prompt
        )

        # C. LOGICA AI (Planner + Researcher/Amadeus)
        # 1. Citim preferintele din DB (invizibil)
        prefs, _ = UserPreference.objects.get_or_create(user=request.user)
        
        # 2. Aici vei apela API-ul tau de AI (Agentul 1)
        # ai_response = agent_orchestrator(prompt, prefs)
        ai_response = "Buna! Am inteles ca vrei sa mergi in " + prompt + ". Verific acum optiunile..."

        # D. Salvare raspuns AI
        ChatMessage.objects.create(
            session=current_session,
            role='assistant',
            content=ai_response
        )

        current_session.status = 'completed'
        current_session.save()

        # Ne redirectionam catre aceeasi sesiune pentru a vedea raspunsul
        return redirect('chat_with_session', session_id=current_session.id)

    # 4. Randam pagina cu toate datele necesare
    return render(request, 'html/chat.html', {
        'sessions': sessions,           # Pentru sidebar
        'current_session': current_session, # Pentru a sti ce chat e activ
        'messages': messages            # Mesajele din chat-ul selectat
    })