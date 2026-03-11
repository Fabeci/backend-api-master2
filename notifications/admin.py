# notifications/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['user_email', 'type_badge', 'message_preview', 'is_read', 'created_at', 'institution']
    list_filter   = ['type', 'is_read', 'created_at', 'institution']
    search_fields = ['user__email', 'user__nom', 'user__prenom', 'message']
    readonly_fields = ['created_at']
    ordering      = ['-created_at']
    list_per_page = 25

    actions = ['mark_as_read', 'mark_as_unread']

    # ── Colonnes personnalisées ───────────────────────────────────────────────

    @admin.display(description="Utilisateur", ordering='user__email')
    def user_email(self, obj):
        return f"{obj.user.prenom} {obj.user.nom} ({obj.user.email})"

    @admin.display(description="Type")
    def type_badge(self, obj):
        colors = {
            'INFO':    ('#1a56db', '#eff4ff'),
            'SUCCESS': ('#10b981', '#ecfdf5'),
            'WARNING': ('#f59e0b', '#fffbeb'),
            'ERROR':   ('#ef4444', '#fef2f2'),
        }
        color, bg = colors.get(obj.type, ('#374151', '#f4f6fb'))
        return format_html(
            '<span style="padding:2px 10px;border-radius:20px;background:{};color:{};'
            'font-size:11px;font-weight:700;">{}</span>',
            bg, color, obj.get_type_display()
        )

    @admin.display(description="Message")
    def message_preview(self, obj):
        return obj.message[:80] + ('…' if len(obj.message) > 80 else '')

    # ── Actions ───────────────────────────────────────────────────────────────

    @admin.action(description="Marquer comme lue(s)")
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(is_read=False).update(is_read=True)
        self.message_user(request, f"{updated} notification(s) marquée(s) comme lue(s).")

    @admin.action(description="Marquer comme non lue(s)")
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False)
        self.message_user(request, f"{updated} notification(s) marquée(s) comme non lue(s).")