# notifications/consumers.py
#
# WebSocket temps réel des notifications (Django Channels).
# Authentification : token DRF passé en query string `?token=<clé>`
# (le frontend stocke ce token dans localStorage['token']).
from datetime import timedelta
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone


class NotificationConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self.user = await self._get_user()
        if self.user is None:
            await self.close(code=4401)  # non authentifié
            return
        self.group_name = f"notif_user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    # Message poussé par le backend (voir notifications/signals.py)
    async def notif_message(self, event):
        await self.send_json(event["payload"])

    # ── Authentification (token DRF avec expiration) ──────────────────────────
    @database_sync_to_async
    def _get_user(self):
        from rest_framework.authtoken.models import Token

        qs = parse_qs((self.scope.get("query_string") or b"").decode())
        key = (qs.get("token") or [None])[0]
        if not key:
            return None
        try:
            token = Token.objects.select_related("user").get(key=key)
        except Token.DoesNotExist:
            return None

        ttl = getattr(settings, "AUTH_TOKEN_TTL", None)
        if ttl and token.created < timezone.now() - timedelta(seconds=int(ttl)):
            return None
        return token.user
