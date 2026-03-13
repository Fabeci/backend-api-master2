# notifications/serializers.py

from rest_framework import serializers
from .models import Notification, PreferenceNotification, DigestNotification


# ============================================================================
# NOTIFICATION
# ============================================================================

class NotificationSerializer(serializers.ModelSerializer):
    """Lecture complète d'une notification."""

    recipient_email  = serializers.EmailField(source="recipient.email",  read_only=True)
    recipient_nom    = serializers.CharField(source="recipient.nom",     read_only=True)
    recipient_prenom = serializers.CharField(source="recipient.prenom",  read_only=True)

    sender_email  = serializers.SerializerMethodField()
    sender_nom    = serializers.SerializerMethodField()

    priorite_label    = serializers.CharField(source="get_priorite_display",    read_only=True)
    canal_label       = serializers.CharField(source="get_canal_display",       read_only=True)
    type_label        = serializers.CharField(source="get_type_display",        read_only=True)
    statut_envoi_label = serializers.CharField(source="get_statut_envoi_display", read_only=True)
    entity_type_label  = serializers.CharField(source="get_entity_type_display",  read_only=True)

    est_expiree      = serializers.BooleanField(read_only=True)
    est_prete_a_envoyer = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Notification
        fields = [
            "id",
            # Destinataire
            "recipient", "recipient_email", "recipient_nom", "recipient_prenom",
            # Expéditeur
            "sender", "sender_email", "sender_nom",
            # Classification
            "type", "type_label",
            "priorite", "priorite_label",
            "canal", "canal_label",
            # Contenu
            "titre", "message", "action_url",
            # Entité liée
            "entity_type", "entity_type_label", "entity_id",
            # Contexte
            "institution", "annee_scolaire",
            # Déduplication
            "groupe_deduplication", "nb_evenements_groupes",
            # Lecture
            "is_read", "read_at",
            # Envoi
            "statut_envoi", "statut_envoi_label", "sent_at", "send_error",
            # Programmation
            "scheduled_at", "expires_at",
            # Computed
            "est_expiree", "est_prete_a_envoyer",
            # Métadonnées
            "metadata",
            # Horodatage
            "created_at",
        ]
        read_only_fields = [
            "id", "created_at", "read_at", "sent_at",
            "nb_evenements_groupes", "send_error",
        ]

    def get_sender_email(self, obj):
        return obj.sender.email if obj.sender else None

    def get_sender_nom(self, obj):
        if not obj.sender:
            return "Système"
        return f"{obj.sender.prenom} {obj.sender.nom}"


class NotificationListSerializer(serializers.ModelSerializer):
    """Serializer allégé pour les listes (centre de notifications)."""

    sender_nom    = serializers.SerializerMethodField()
    priorite_label = serializers.CharField(source="get_priorite_display", read_only=True)
    type_label     = serializers.CharField(source="get_type_display",     read_only=True)
    est_expiree    = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Notification
        fields = [
            "id", "type", "type_label", "titre", "message",
            "priorite", "priorite_label", "canal",
            "is_read", "read_at",
            "sender_nom",
            "entity_type", "entity_id", "action_url",
            "nb_evenements_groupes",
            "est_expiree", "expires_at",
            "created_at",
        ]

    def get_sender_nom(self, obj):
        if not obj.sender:
            return "Système"
        return f"{obj.sender.prenom} {obj.sender.nom}"


class MarquerLueSerializer(serializers.Serializer):
    """Payload pour marquer une ou plusieurs notifications comme lues."""
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Liste d'IDs. Si absent → toutes les notifications non lues."
    )


# ============================================================================
# PRÉFÉRENCES
# ============================================================================

class PreferenceNotificationSerializer(serializers.ModelSerializer):
    type_label  = serializers.CharField(source="get_type_display",  read_only=True)
    canal_label = serializers.CharField(source="get_canal_display", read_only=True)

    class Meta:
        model  = PreferenceNotification
        fields = ["id", "user", "type", "type_label", "canal", "canal_label", "est_active"]
        read_only_fields = ["id", "user"]

    def validate(self, data):
        user = self.context["request"].user
        type_  = data.get("type",  getattr(self.instance, "type",  None))
        canal  = data.get("canal", getattr(self.instance, "canal", None))

        qs = PreferenceNotification.objects.filter(user=user, type=type_, canal=canal)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Une préférence pour ce type et ce canal existe déjà."
            )
        return data


# ============================================================================
# DIGEST
# ============================================================================

class DigestNotificationSerializer(serializers.ModelSerializer):
    notifications = NotificationListSerializer(many=True, read_only=True)
    frequence_label = serializers.CharField(source="get_frequence_display", read_only=True)

    class Meta:
        model  = DigestNotification
        fields = [
            "id", "user", "frequence", "frequence_label",
            "notifications", "envoye", "envoye_le",
            "periode_debut", "periode_fin", "created_at",
        ]
        read_only_fields = ["id", "envoye", "envoye_le", "created_at"]