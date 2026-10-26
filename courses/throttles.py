# courses/throttles.py
"""Limitations de débit spécifiques au chat pédagogique."""
from rest_framework.throttling import UserRateThrottle


class ChatTuteurThrottle(UserRateThrottle):
    """Limite les envois de messages au tuteur IA (scope `chat_tuteur`)."""
    scope = "chat_tuteur"
