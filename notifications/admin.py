# notifications/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Notification, PreferenceNotification, DigestNotification


# ============================================================================
# NOTIFICATION
# ============================================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = [
        "id", "recipient", "sender_display", "type", "canal",
        "priorite_badge", "statut_envoi_badge", "is_read", "est_expiree_display", "created_at"
    ]
    list_filter   = ["type", "canal", "priorite", "statut_envoi", "is_read", "institution"]
    search_fields = ["recipient__email", "recipient__nom", "titre", "message", "groupe_deduplication"]
    readonly_fields = [
        "created_at", "read_at", "sent_at", "send_error",
        "nb_evenements_groupes", "est_expiree_display"
    ]
    ordering      = ["-created_at"]
    date_hierarchy = "created_at"

    fieldsets = (
        ("Destinataire & Expéditeur", {
            "fields": ("recipient", "sender")
        }),
        ("Classification", {
            "fields": ("type", "priorite", "canal")
        }),
        ("Contenu", {
            "fields": ("titre", "message", "action_url")
        }),
        ("Entité liée", {
            "fields": ("entity_type", "entity_id")
        }),
        ("Contexte institutionnel", {
            "fields": ("institution", "annee_scolaire")
        }),
        ("Déduplication", {
            "fields": ("groupe_deduplication", "nb_evenements_groupes"),
            "classes": ("collapse",)
        }),
        ("État de lecture", {
            "fields": ("is_read", "read_at")
        }),
        ("État d'envoi", {
            "fields": ("statut_envoi", "sent_at", "send_error")
        }),
        ("Programmation & Expiration", {
            "fields": ("scheduled_at", "expires_at")
        }),
        ("Métadonnées", {
            "fields": ("metadata",),
            "classes": ("collapse",)
        }),
        ("Horodatage", {
            "fields": ("created_at",)
        }),
    )

    def sender_display(self, obj):
        return obj.sender.email if obj.sender else "🤖 Système"
    sender_display.short_description = "Expéditeur"

    def priorite_badge(self, obj):
        colors = {
            "basse":    "#6c757d",
            "moyenne":  "#0d6efd",
            "haute":    "#fd7e14",
            "critique": "#dc3545",
        }
        color = colors.get(obj.priorite, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_priorite_display()
        )
    priorite_badge.short_description = "Priorité"

    def statut_envoi_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "sent":    "#198754",
            "failed":  "#dc3545",
            "skipped": "#6c757d",
        }
        color = colors.get(obj.statut_envoi, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.statut_envoi.upper()
        )
    statut_envoi_badge.short_description = "Envoi"

    def est_expiree_display(self, obj):
        return "✅ Active" if not obj.est_expiree else "❌ Expirée"
    est_expiree_display.short_description = "Expiration"


# ============================================================================
# PRÉFÉRENCES
# ============================================================================

@admin.register(PreferenceNotification)
class PreferenceNotificationAdmin(admin.ModelAdmin):
    list_display  = ["user", "type", "canal", "est_active"]
    list_filter   = ["canal", "est_active", "type"]
    search_fields = ["user__email", "user__nom"]
    list_editable = ["est_active"]
    ordering      = ["user__email", "type", "canal"]


# ============================================================================
# DIGEST
# ============================================================================

@admin.register(DigestNotification)
class DigestNotificationAdmin(admin.ModelAdmin):
    list_display  = ["user", "frequence", "periode_debut", "periode_fin", "envoye", "envoye_le"]
    list_filter   = ["frequence", "envoye"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "envoye_le"]
    ordering      = ["-created_at"]