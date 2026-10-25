import os

from rest_framework import serializers

from .models import (
    Ressource,
    RessourceSupplementaire,
    PieceJointe,
    RessourcePieceJointe,
    RessourceSuppPieceJointe,
)

# ✅ SÉCURITÉ : liste blanche d'extensions et taille maximale.
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".txt", ".zip",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".webm", ".mp3", ".wav", ".ogg",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 Mo


class FileValidationMixin:
    def validate_fichier(self, value):
        ext = os.path.splitext(getattr(value, "name", "") or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Extension non autorisée. Formats acceptés : "
                + ", ".join(sorted(ALLOWED_EXTENSIONS))
            )
        if getattr(value, "size", 0) > MAX_FILE_SIZE:
            raise serializers.ValidationError("Fichier trop volumineux (max 50 Mo).")
        return value


class RessourceSerializer(FileValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = Ressource
        fields = ['id', 'titre', 'fichier', 'sequence', 'date_ajout']


class RessourceSupplementaireSerializer(FileValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = RessourceSupplementaire
        fields = ['id', 'titre', 'fichier', 'sequence', 'apprenant', 'date_ajout']


class PieceJointeSerializer(FileValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = PieceJointe
        fields = ['id', 'fichier', 'ressource', 'ressource_supplementaire']


class RessourcePieceJointeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RessourcePieceJointe
        fields = ['id', 'ressource', 'piece_jointe']


class RessourceSuppPieceJointeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RessourceSuppPieceJointe
        fields = ['id', 'ressource', 'piece_jointe']
