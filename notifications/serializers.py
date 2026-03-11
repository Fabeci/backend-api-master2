# notifications/serializers.py
from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'message', 'type', 'type_display', 'created_at', 'is_read']
        read_only_fields = ['id', 'created_at', 'type_display']