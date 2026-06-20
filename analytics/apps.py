from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'

    def ready(self):
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
