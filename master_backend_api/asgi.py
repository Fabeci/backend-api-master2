"""
ASGI config — Django Channels (WebSocket temps réel + HTTP).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

# L'application HTTP Django doit être initialisée AVANT d'importer le routing.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.auth import AuthMiddlewareStack               # noqa: E402
from notifications.routing import websocket_urlpatterns     # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
