# notifications/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NotificationViewSet,
    PreferenceNotificationViewSet,
    DigestNotificationViewSet,
)

router = DefaultRouter()
router.register(r"notifications",  NotificationViewSet,           basename="notifications")
router.register(r"preferences",    PreferenceNotificationViewSet, basename="preferences-notifications")
router.register(r"digests",        DigestNotificationViewSet,     basename="digests-notifications")

urlpatterns = [
    path("", include(router.urls)),
]