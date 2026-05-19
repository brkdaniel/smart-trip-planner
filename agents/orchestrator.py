from trips.models import ChatSession
from django.contrib.auth.models import User

def handle_user_message(prompt: str, session: ChatSession, user: User) -> str:
    """
    Returns the assistant's reply text. 
    Side effect: may update UserPreference.
    """
    # TODO (Branch A): Replace this stub with actual Claude/Gemini LLM calls.
    # For now, it just echoes the prompt so we know the frontend is connected.
    return f"Stub response: I received your message - '{prompt}'"