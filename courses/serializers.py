# courses/serializers.py

from rest_framework import serializers
from academics.models import Groupe, Matiere, Institution, AnneeScolaire
from users.models import Apprenant, Formateur
from users.serializers import ApprenantSerializer, FormateurSerializer

from .models import (
    BlocProgress,
    Cours,
    CoursProgress,
    InscriptionCours,
    Module,
    ModuleProgress,
    Participation,
    Sequence,
    SequenceContent,
    SequenceProgress,
    Session,
    Suivi,
    BlocContenu,
    RessourceSequence,
)


# ============================================================================
# COURS
# ============================================================================

class CoursSerializer(serializers.ModelSerializer):
    """Serializer pour les cours"""
    
    # Read-only "labels" utiles côté UI
    groupe_nom = serializers.CharField(source="groupe.nom", read_only=True)
    matiere_nom = serializers.CharField(source="matiere.nom", read_only=True)
    enseignant_nom = serializers.SerializerMethodField(read_only=True)
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)

    # Stats calculées (properties)
    total_minutes_realises = serializers.IntegerField(read_only=True)
    total_heures_realisees = serializers.FloatField(read_only=True)
    taux_execution = serializers.FloatField(read_only=True)

    class Meta:
        model = Cours
        fields = [
            "id",
            "titre",
            "groupe",
            "groupe_nom",
            "enseignant",
            "enseignant_nom",
            "matiere",
            "matiere_nom",
            "institution",
            "institution_nom",
            "annee_scolaire",
            "annee_scolaire_nom",
            "volume_horaire",
            "date_debut",
            "date_fin",
            "statut",
            "total_minutes_realises",
            "total_heures_realisees",
            "taux_execution",
        ]
        extra_kwargs = {
            "titre": {"required": False, "allow_null": True, "allow_blank": True},
            "date_debut": {"required": False, "allow_null": True},
            "date_fin": {"required": False, "allow_null": True},
        }

    def get_enseignant_nom(self, obj):
        ens = getattr(obj, "enseignant", None)
        if not ens:
            return None
        prenom = getattr(ens, "prenom", "")
        nom = getattr(ens, "nom", "")
        full = (f"{prenom} {nom}").strip()
        return full or str(ens)

    def validate(self, attrs):
        """Validation des dates et unicité"""
        date_debut = attrs.get("date_debut", getattr(self.instance, "date_debut", None))
        date_fin = attrs.get("date_fin", getattr(self.instance, "date_fin", None))

        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date_fin doit être postérieure ou égale à date_debut."}
            )

        # Validation d'unicité
        groupe = attrs.get("groupe", getattr(self.instance, "groupe", None))
        matiere = attrs.get("matiere", getattr(self.instance, "matiere", None))
        enseignant = attrs.get("enseignant", getattr(self.instance, "enseignant", None))
        annee_scolaire = attrs.get("annee_scolaire", getattr(self.instance, "annee_scolaire", None))

        if groupe and matiere and enseignant and annee_scolaire:
            qs = Cours.objects.filter(
                groupe=groupe, 
                matiere=matiere, 
                enseignant=enseignant,
                annee_scolaire=annee_scolaire
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Un cours avec ce groupe, cette matière et cet enseignant existe déjà pour cette année scolaire."
                        ]
                    }
                )

        return attrs


# ============================================================================
# MODULES
# ============================================================================

class ModuleSerializer(serializers.ModelSerializer):
    """Serializer pour les modules"""
    
    cours = serializers.PrimaryKeyRelatedField(queryset=Cours.objects.all())
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)

    class Meta:
        model = Module
        fields = [
            "id", 
            "titre", 
            "description", 
            "cours",
            "institution",
            "institution_nom",
            "annee_scolaire",
            "annee_scolaire_nom"
        ]
        read_only_fields = ["institution", "annee_scolaire"]


# ============================================================================
# BLOCS DE CONTENU
# ============================================================================

class BlocContenuSerializer(serializers.ModelSerializer):
    """Serializer pour les blocs de contenu"""
    
    icone_type = serializers.ReadOnlyField()
    
    class Meta:
        model = BlocContenu
        fields = [
            'id', 'sequence', 'titre', 'type_bloc', 'ordre',
            'contenu_texte', 'contenu_html', 'contenu_markdown',
            'video_url', 'audio_url', 'image', 'fichier',
            'lien_externe', 'code_source', 'langage_code',
            'objectifs', 'duree_estimee_minutes',
            'est_obligatoire', 'est_visible',
            'icone_type', 'date_creation', 'date_modification'
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']


class BlocContenuCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un bloc de contenu"""
    
    class Meta:
        model = BlocContenu
        fields = [
            'sequence', 'titre', 'type_bloc', 'ordre',
            'contenu_texte', 'contenu_html', 'contenu_markdown',
            'video_url', 'audio_url', 'image', 'fichier',
            'lien_externe', 'code_source', 'langage_code',
            'objectifs', 'duree_estimee_minutes',
            'est_obligatoire', 'est_visible'
        ]


# ============================================================================
# RESSOURCES SÉQUENCES
# ============================================================================

class RessourceSequenceSerializer(serializers.ModelSerializer):
    """Serializer pour les ressources/pièces jointes"""
    
    taille_lisible = serializers.ReadOnlyField()
    extension = serializers.ReadOnlyField()
    icone_extension = serializers.ReadOnlyField()
    ajoute_par_nom = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = RessourceSequence
        fields = [
            'id', 'sequence', 'titre', 'description', 'fichier',
            'type_ressource', 'taille_fichier', 'taille_lisible',
            'extension', 'icone_extension', 'est_telechargeable',
            'nombre_telechargements', 'ordre', 'date_ajout',
            'date_modification', 'ajoute_par', 'ajoute_par_nom'
        ]
        read_only_fields = [
            'id', 'taille_fichier', 'nombre_telechargements',
            'date_ajout', 'date_modification'
        ]
    
    def get_ajoute_par_nom(self, obj):
        if obj.ajoute_par:
            return obj.ajoute_par.get_full_name()
        return None


class RessourceSequenceCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer une ressource"""
    
    class Meta:
        model = RessourceSequence
        fields = [
            'sequence', 'titre', 'description', 'fichier',
            'type_ressource', 'est_telechargeable', 'ordre'
        ]


# ============================================================================
# SÉQUENCES
# ============================================================================

class SequenceSerializer(serializers.ModelSerializer):
    """Serializer simple pour les séquences"""
    
    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all())
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)

    class Meta:
        model = Sequence
        fields = [
            'id', 
            'titre', 
            'module',
            'institution',
            'institution_nom',
            'annee_scolaire',
            'annee_scolaire_nom'
        ]
        read_only_fields = ["institution", "annee_scolaire"]


class SequenceDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé avec blocs et ressources"""
    
    blocs_contenu = BlocContenuSerializer(many=True, read_only=True)
    ressources_sequences = RessourceSequenceSerializer(many=True, read_only=True)
    module_titre = serializers.CharField(source='module.titre', read_only=True)
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)
    
    # Statistiques calculées
    nombre_blocs = serializers.SerializerMethodField()
    nombre_ressources = serializers.SerializerMethodField()
    duree_totale_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = Sequence
        fields = [
            'id', 'titre', 'module', 'module_titre',
            'institution', 'institution_nom',
            'annee_scolaire', 'annee_scolaire_nom',
            'nombre_blocs', 'nombre_ressources', 'duree_totale_minutes',
            'blocs_contenu', 'ressources_sequences'
        ]
        read_only_fields = ["institution", "annee_scolaire"]
    
    def get_nombre_blocs(self, obj):
        return obj.blocs_contenu.count()
    
    def get_nombre_ressources(self, obj):
        return obj.ressources_sequences.count()
    
    def get_duree_totale_minutes(self, obj):
        return sum(
            bloc.duree_estimee_minutes 
            for bloc in obj.blocs_contenu.all()
        )


# ============================================================================
# INSCRIPTIONS, SUIVIS, SESSIONS, PARTICIPATIONS
# ============================================================================

class InscriptionCoursSerializer(serializers.ModelSerializer):
    apprenant = ApprenantSerializer(read_only=True)
    cours = CoursSerializer(read_only=True)
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)
    
    # Pour la création
    apprenant_id = serializers.PrimaryKeyRelatedField(
        queryset=Apprenant.objects.all(),
        source='apprenant',
        write_only=True
    )
    cours_id = serializers.PrimaryKeyRelatedField(
        queryset=Cours.objects.all(),
        source='cours',
        write_only=True
    )

    class Meta:
        model = InscriptionCours
        fields = [
            'id', 'apprenant', 'apprenant_id', 'cours', 'cours_id',
            'date_inscription', 'statut',
            'institution', 'institution_nom',
            'annee_scolaire', 'annee_scolaire_nom'
        ]
        read_only_fields = ['institution', 'annee_scolaire']


class SuiviSerializer(serializers.ModelSerializer):
    apprenant = ApprenantSerializer(read_only=True)
    cours = CoursSerializer(read_only=True)
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)
    
    # Pour la création
    apprenant_id = serializers.PrimaryKeyRelatedField(
        queryset=Apprenant.objects.all(),
        source='apprenant',
        write_only=True
    )
    cours_id = serializers.PrimaryKeyRelatedField(
        queryset=Cours.objects.all(),
        source='cours',
        write_only=True
    )

    class Meta:
        model = Suivi
        fields = [
            'id', 'apprenant', 'apprenant_id', 'cours', 'cours_id',
            'date_debut', 'progression', 'note', 'commentaires',
            'institution', 'institution_nom',
            'annee_scolaire', 'annee_scolaire_nom'
        ]
        read_only_fields = ['institution', 'annee_scolaire']


class SessionSerializer(serializers.ModelSerializer):
    formateur = FormateurSerializer(read_only=True)
    cours = CoursSerializer(read_only=True)
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)
    
    # Pour la création
    formateur_id = serializers.PrimaryKeyRelatedField(
        queryset=Formateur.objects.all(),
        source='formateur',
        write_only=True
    )
    cours_id = serializers.PrimaryKeyRelatedField(
        queryset=Cours.objects.all(),
        source='cours',
        write_only=True
    )
    
    duree_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Session
        fields = [
            'id', 'titre', 'date_debut', 'date_fin',
            'formateur', 'formateur_id', 'cours', 'cours_id',
            'participation_mode', 'duree_minutes',
            'institution', 'institution_nom',
            'annee_scolaire', 'annee_scolaire_nom'
        ]
        read_only_fields = ['id', 'duree_minutes', 'institution', 'annee_scolaire']


class SessionLiteSerializer(serializers.ModelSerializer):
    """Serializer léger pour les sessions"""
    
    class Meta:
        model = Session
        fields = [
            "id", "titre", "date_debut", "date_fin",
            "cours", "formateur", "participation_mode",
            "institution", "annee_scolaire"
        ]

class SequenceContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SequenceContent
        fields = [
            "id",
            "sequence",
            "contenu_texte",
            "contenu_html",
            "video_url",
            "lien_externe",
            "objectifs",
            "duree_estimee_minutes",
            "est_publie",
            "date_creation",
            "date_modification",
        ]

class ParticipationSerializer(serializers.ModelSerializer):
    session = SessionSerializer(read_only=True)
    apprenant = ApprenantSerializer(read_only=True)
    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)
    
    # Pour la création
    session_id = serializers.PrimaryKeyRelatedField(
        queryset=Session.objects.all(),
        source='session',
        write_only=True
    )
    apprenant_id = serializers.PrimaryKeyRelatedField(
        queryset=Apprenant.objects.all(),
        source='apprenant',
        write_only=True
    )

    class Meta:
        model = Participation
        fields = [
            "id", "session", "session_id", "apprenant", "apprenant_id",
            "source", "statut", "created_at", "completed_at",
            "institution", "institution_nom",
            "annee_scolaire", "annee_scolaire_nom"
        ]
        read_only_fields = ['id', 'created_at', 'institution', 'annee_scolaire']


# ============================================================================
# PROGRESSION
# ============================================================================

class BlocProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlocProgress
        fields = ["id", "bloc", "est_termine", "completed_at", "updated_at"]
        read_only_fields = ["id", "completed_at", "updated_at"]


class SequenceProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SequenceProgress
        fields = ["id", "sequence", "est_termine", "completed_at", "updated_at"]
        read_only_fields = ["id", "completed_at", "updated_at"]


class ModuleProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModuleProgress
        fields = ["id", "module", "est_termine", "completed_at", "updated_at"]
        read_only_fields = ["id", "completed_at", "updated_at"]


class CoursProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoursProgress
        fields = ["id", "cours", "est_termine", "completed_at", "updated_at"]
        read_only_fields = ["id", "completed_at", "updated_at"]


# Serializer "action" (PUT) simple pour set terminé/non terminé
class ProgressToggleSerializer(serializers.Serializer):
    est_termine = serializers.BooleanField()