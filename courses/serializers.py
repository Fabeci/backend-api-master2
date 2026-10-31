# courses/serializers.py

from datetime import datetime, time

from rest_framework import serializers
from django.utils import timezone
from academics.models import Groupe, Matiere, Institution, AnneeScolaire
from users.models import Apprenant, Formateur
from users.serializers import ApprenantSerializer, FormateurSerializer

from .utils import INSCRIPTION_ACTIVE_STATUSES
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
    SessionInvite,
    Suivi,
    BlocContenu,
    RessourceSequence,
)


def _publication_defaut_pour_cours(cours):
    """Un contenu créé sous un cours futur naît « programmé » à la date du cours.

    Le formateur peut ensuite remplacer ce choix (brouillon, publié, autre date).
    """
    if not cours or not getattr(cours, "date_debut", None):
        return {}
    if cours.date_debut <= timezone.localdate():
        return {}
    date_pub = timezone.make_aware(datetime.combine(cours.date_debut, time.min))
    return {
        "etat_publication": "programme",
        "date_publication_programmee": date_pub,
    }


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
    statut_calcule = serializers.ReadOnlyField()
    departement_nom = serializers.CharField(source="departement.nom", read_only=True, default=None)
    nombre_modules = serializers.SerializerMethodField(read_only=True)
    nombre_inscrits = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Cours
        fields = [
            "id",
            "titre",
            "image",
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
            "departement",
            "departement_nom",
            "volume_horaire",
            "date_debut",
            "date_fin",
            "statut",
            "statut_calcule",
            "statut_force",
            "total_minutes_realises",
            "total_heures_realisees",
            "taux_execution",
            "nombre_modules",
            "nombre_inscrits",
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

    def get_nombre_modules(self, obj):
        # ✅ Utilise l'annotation du queryset si présente (évite le N+1).
        value = getattr(obj, "nb_modules", None)
        return value if value is not None else obj.modules.count()

    def get_nombre_inscrits(self, obj):
        value = getattr(obj, "nb_inscrits", None)
        return value if value is not None else obj.inscriptions.filter(statut__in=INSCRIPTION_ACTIVE_STATUSES).count()

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
            # ✅ Publication progressive
            "etat_publication", "date_publication_programmee", "date_publication_effective",
            "titre",
            "description",
            "cours",
            "ordre",
            "duree_estimee",
            "institution",
            "institution_nom",
            "annee_scolaire",
            "annee_scolaire_nom"
        ]
        read_only_fields = ["institution", "annee_scolaire"]

# ============================================================================
# BLOCS DE CONTENU
# ============================================================================

    def validate(self, attrs):
        etat = attrs.get("etat_publication", getattr(self.instance, "etat_publication", None))
        date_p = attrs.get("date_publication_programmee",
                           getattr(self.instance, "date_publication_programmee", None))
        if etat == "programme" and date_p is None:
            raise serializers.ValidationError(
                {"date_publication_programmee": "Une date de publication est requise pour un contenu programmé."}
            )
        if etat == "programme" and date_p is not None:
            from django.utils import timezone
            now = timezone.now()
            if date_p <= now:
                # Date déjà atteinte → publication immédiate (évite un rejet
                # silencieux lorsque la minute choisie est déjà en cours).
                attrs["etat_publication"] = "publie"
                attrs["date_publication_programmee"] = None
                attrs["date_publication_effective"] = now
        return attrs

    def create(self, validated_data):
        if "etat_publication" not in self.initial_data:
            validated_data.update(
                _publication_defaut_pour_cours(validated_data.get("cours"))
            )
        return super().create(validated_data)


class BlocContenuSerializer(serializers.ModelSerializer):
    """
    Serializer universel pour lecture ET écriture (PUT/PATCH/GET).

    Règle importante :
    - allow_blank=True  → uniquement sur CharField / TextField
    - allow_null=True   → sur tous les champs nullable (URL, fichier, int...)
    - URLField / FileField / ImageField → redéclarés explicitement pour éviter
      l'erreur "Field.__init__() got an unexpected keyword argument 'allow_blank'"
    """
    icone_type = serializers.ReadOnlyField()

    # Champs URL/fichier redéclarés explicitement (sans allow_blank)
    image    = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    fichier  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    video_url    = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    audio_url    = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    lien_externe = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

    class Meta:
        model = BlocContenu
        fields = [
            'id', 'sequence', 'titre', 'type_bloc', 'ordre',
            'contenu_texte', 'contenu_html', 'contenu_markdown',
            'video_url', 'audio_url', 'image', 'fichier',
            'lien_externe', 'code_source', 'langage_code',
            'objectifs', 'duree_estimee_minutes',
            'est_obligatoire', 'est_visible',
            # ✅ Publication progressive
            'etat_publication', 'date_publication_programmee', 'date_publication_effective',
            'icone_type', 'date_creation', 'date_modification'
        ]
        read_only_fields = ['id', 'icone_type', 'date_creation', 'date_modification']
        extra_kwargs = {
            # FK / choices
            'sequence':              {'required': False},
            'type_bloc':             {'required': False},
            'ordre':                 {'required': False},
            # CharField / TextField → allow_blank OK
            'titre':                 {'required': False, 'allow_blank': True},
            'contenu_texte':         {'required': False, 'allow_null': True, 'allow_blank': True},
            'contenu_html':          {'required': False, 'allow_null': True, 'allow_blank': True},
            'contenu_markdown':      {'required': False, 'allow_null': True, 'allow_blank': True},
            'code_source':           {'required': False, 'allow_null': True, 'allow_blank': True},
            'langage_code':          {'required': False, 'allow_null': True, 'allow_blank': True},
            'objectifs':             {'required': False, 'allow_null': True, 'allow_blank': True},
            # IntegerField → allow_null uniquement (pas allow_blank)
            'duree_estimee_minutes': {'required': False, 'allow_null': True},
            # BooleanField → required uniquement
            'est_obligatoire':       {'required': False},
            'est_visible':           {'required': False},
        }

    def to_internal_value(self, data):
        """
        Convertit les chaînes vides '' en None pour les champs URL/fichier
        avant la validation DRF, évitant les erreurs URLField sur "".
        """
        url_like_fields = ['video_url', 'audio_url', 'lien_externe', 'image', 'fichier']
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        for field_name in url_like_fields:
            if mutable.get(field_name) == '':
                mutable[field_name] = None
        return super().to_internal_value(mutable)

    def validate(self, attrs):
        """
        Création → sequence, titre, type_bloc requis.
        Mise à jour → tout ce qui est envoyé est accepté.
        """
        if self.instance is None:
            errors = {}
            if 'sequence' not in attrs:
                errors['sequence'] = ['Ce champ est obligatoire.']
            if not attrs.get('titre'):
                errors['titre'] = ['Ce champ est obligatoire.']
            if 'type_bloc' not in attrs:
                errors['type_bloc'] = ['Ce champ est obligatoire.']
            if errors:
                raise serializers.ValidationError(errors)
        # Publication : impossible de publier un bloc si sa séquence (et son module) ne l'est pas
        if attrs.get("etat_publication") == "publie":
            seq = attrs.get("sequence") or getattr(self.instance, "sequence", None)
            if (not seq
                    or getattr(seq, "etat_publication", None) != "publie"
                    or getattr(getattr(seq, "module", None), "etat_publication", None) != "publie"):
                if self.instance is None:
                    # Création : on aligne le bloc sur sa séquence (brouillon).
                    attrs["etat_publication"] = "brouillon"
                else:
                    raise serializers.ValidationError(
                        {"etat_publication": "La séquence (et son module) doivent être publiés avant de publier un bloc."}
                    )
        return attrs

    def create(self, validated_data):
        seq = validated_data.get("sequence")
        if "etat_publication" not in self.initial_data:
            validated_data.update(
                _publication_defaut_pour_cours(
                    getattr(getattr(seq, "module", None), "cours", None)
                )
            )
        return super().create(validated_data)


class BlocContenuCreateSerializer(serializers.ModelSerializer):
    """Serializer dédié à la création."""

    image    = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    fichier  = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    video_url    = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    audio_url    = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    lien_externe = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

    class Meta:
        model = BlocContenu
        fields = [
            'sequence', 'titre', 'type_bloc', 'ordre',
            'contenu_texte', 'contenu_html', 'contenu_markdown',
            'video_url', 'audio_url', 'image', 'fichier',
            'lien_externe', 'code_source', 'langage_code',
            'objectifs', 'duree_estimee_minutes',
            'est_obligatoire', 'est_visible',
            'etat_publication', 'date_publication_programmee',
        ]
        extra_kwargs = {
            'contenu_texte':         {'required': False, 'allow_null': True, 'allow_blank': True},
            'contenu_html':          {'required': False, 'allow_null': True, 'allow_blank': True},
            'contenu_markdown':      {'required': False, 'allow_null': True, 'allow_blank': True},
            'code_source':           {'required': False, 'allow_null': True, 'allow_blank': True},
            'langage_code':          {'required': False, 'allow_null': True, 'allow_blank': True},
            'objectifs':             {'required': False, 'allow_null': True, 'allow_blank': True},
            'duree_estimee_minutes': {'required': False, 'allow_null': True},
            'est_obligatoire':       {'required': False},
            'est_visible':           {'required': False},
            'ordre':                 {'required': False},
        }

    def to_internal_value(self, data):
        url_like_fields = ['video_url', 'audio_url', 'lien_externe', 'image', 'fichier']
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        for field_name in url_like_fields:
            if mutable.get(field_name) == '':
                mutable[field_name] = None
        return super().to_internal_value(mutable)


# ============================================================================
# RESSOURCES SÉQUENCES
# ============================================================================

    def validate(self, attrs):
        etat = attrs.get("etat_publication", getattr(self.instance, "etat_publication", None))
        date_p = attrs.get("date_publication_programmee",
                           getattr(self.instance, "date_publication_programmee", None))
        if etat == "programme" and date_p is None:
            raise serializers.ValidationError(
                {"date_publication_programmee": "Une date de publication est requise pour un contenu programmé."}
            )
        if etat == "programme" and date_p is not None:
            from django.utils import timezone
            now = timezone.now()
            if date_p <= now:
                # Date déjà atteinte → publication immédiate (évite un rejet
                # silencieux lorsque la minute choisie est déjà en cours).
                attrs["etat_publication"] = "publie"
                attrs["date_publication_programmee"] = None
                attrs["date_publication_effective"] = now
        # Un bloc ne peut pas naître publié si sa séquence (et son module) ne le sont pas.
        if attrs.get("etat_publication") == "publie":
            seq = attrs.get("sequence")
            if (not seq
                    or getattr(seq, "etat_publication", None) != "publie"
                    or getattr(getattr(seq, "module", None), "etat_publication", None) != "publie"):
                attrs["etat_publication"] = "brouillon"
        return attrs

    def create(self, validated_data):
        seq = validated_data.get("sequence")
        if "etat_publication" not in self.initial_data:
            validated_data.update(
                _publication_defaut_pour_cours(
                    getattr(getattr(seq, "module", None), "cours", None)
                )
            )
        return super().create(validated_data)


class RessourceSequenceSerializer(serializers.ModelSerializer):
    """Serializer pour les ressources/pièces jointes"""
    
    taille_lisible = serializers.ReadOnlyField()
    extension = serializers.ReadOnlyField()
    icone_extension = serializers.ReadOnlyField()
    ajoute_par_nom = serializers.SerializerMethodField(read_only=True)

    # Contexte pédagogique (lecture seule) — évite les N+1 côté client
    sequence_titre = serializers.CharField(source='sequence.titre', read_only=True)
    module_titre = serializers.CharField(source='sequence.module.titre', read_only=True)
    cours_id = serializers.IntegerField(source='sequence.module.cours_id', read_only=True)
    cours_titre = serializers.CharField(source='sequence.module.cours.titre', read_only=True)
    
    class Meta:
        model = RessourceSequence
        fields = [
            'id', 'sequence', 'titre', 'description', 'fichier',
            'type_ressource', 'taille_fichier', 'taille_lisible',
            'extension', 'icone_extension', 'est_telechargeable',
            'nombre_telechargements', 'ordre', 'date_ajout',
            'date_modification', 'ajoute_par', 'ajoute_par_nom',
            'sequence_titre', 'module_titre', 'cours_id', 'cours_titre',
        ]
        read_only_fields = [
            'id', 'taille_fichier', 'nombre_telechargements',
            'date_ajout', 'date_modification'
        ]
    
    def get_ajoute_par_nom(self, obj):
        # ✅ Le modèle User n'a pas `get_full_name` : on compose prénom + nom.
        u = getattr(obj, 'ajoute_par', None)
        if not u:
            return None
        nom_complet = f"{getattr(u, 'prenom', '') or ''} {getattr(u, 'nom', '') or ''}".strip()
        return nom_complet or getattr(u, 'email', None)


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
            # ✅ Publication progressive
            'etat_publication', 'date_publication_programmee', 'date_publication_effective',
            'titre',
            'description',
            'ordre',
            'module',
            'institution',
            'institution_nom',
            'annee_scolaire',
            'annee_scolaire_nom'
        ]
        read_only_fields = ["institution", "annee_scolaire"]

    def validate(self, attrs):
        etat = attrs.get("etat_publication", getattr(self.instance, "etat_publication", None))
        date_p = attrs.get("date_publication_programmee",
                           getattr(self.instance, "date_publication_programmee", None))
        if etat == "programme" and date_p is None:
            raise serializers.ValidationError(
                {"date_publication_programmee": "Une date de publication est requise pour un contenu programmé."}
            )
        if etat == "programme" and date_p is not None:
            from django.utils import timezone
            now = timezone.now()
            if date_p <= now:
                # Date déjà atteinte → publication immédiate (évite un rejet
                # silencieux lorsque la minute choisie est déjà en cours).
                attrs["etat_publication"] = "publie"
                attrs["date_publication_programmee"] = None
                attrs["date_publication_effective"] = now
        if attrs.get("etat_publication") == "publie":
            module = attrs.get("module") or getattr(self.instance, "module", None)
            if not module or getattr(module, "etat_publication", None) != "publie":
                if self.instance is None:
                    # Création : on aligne la séquence sur son module (brouillon).
                    attrs["etat_publication"] = "brouillon"
                else:
                    raise serializers.ValidationError(
                        {"etat_publication": "Le module doit être publié avant de publier une séquence."}
                    )
        return attrs

    def create(self, validated_data):
        module = validated_data.get("module")
        if "etat_publication" not in self.initial_data:
            validated_data.update(
                _publication_defaut_pour_cours(
                    getattr(module, "cours", None)
                )
            )
        return super().create(validated_data)


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
            'id', 'titre', 'description', 'ordre', 'module', 'module_titre',
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
    # lecture nested
    apprenant = ApprenantSerializer(read_only=True)
    cours = CoursSerializer(read_only=True)

    institution_nom = serializers.CharField(source="institution.nom", read_only=True)
    annee_scolaire_nom = serializers.CharField(source="annee_scolaire.annee_format_classique", read_only=True)

    # écriture : apprenant_id / cours_id
    apprenant_id = serializers.PrimaryKeyRelatedField(
        queryset=Apprenant.objects.all(),
        source='apprenant',
        write_only=True,
        required=True,
    )
    cours_id = serializers.PrimaryKeyRelatedField(
        queryset=Cours.objects.all(),
        source='cours',
        write_only=True,
        required=True,
    )

    # read_only (hérités du cours)
    institution = serializers.PrimaryKeyRelatedField(read_only=True)
    annee_scolaire = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = InscriptionCours
        fields = [
            'id',
            'apprenant', 'apprenant_id',
            'cours', 'cours_id',
            'date_inscription', 'statut',
            'institution', 'institution_nom',
            'annee_scolaire', 'annee_scolaire_nom'
        ]
        extra_kwargs = {
            'statut': {'required': False},
            'date_inscription': {'required': False},
        }

    def _inherit_context_from_cours(self, validated_data):
        """
        Force institution + annee_scolaire depuis le cours
        (évite les inscriptions avec institution_id NULL -> invisibles côté LIST).
        """
        cours = validated_data.get('cours') or getattr(self.instance, 'cours', None)
        if cours:
            # Si ton modèle InscriptionCours autorise null=True, ça évite de mettre None
            if getattr(cours, 'institution_id', None):
                validated_data['institution'] = cours.institution
            if getattr(cours, 'annee_scolaire_id', None):
                validated_data['annee_scolaire'] = cours.annee_scolaire
        return validated_data

    def create(self, validated_data):
        validated_data = self._inherit_context_from_cours(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._inherit_context_from_cours(validated_data)
        return super().update(instance, validated_data)
    
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


class SessionInviteSerializer(serializers.ModelSerializer):
    """Invité externe d'une séance (ajouté manuellement)."""
    class Meta:
        model = SessionInvite
        fields = ["id", "email", "nom", "created_at"]


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

    # Invités externes ajoutés manuellement (en plus des éligibles automatiques)
    invites = SessionInviteSerializer(source="invites_externes", many=True, read_only=True)

    # Champ transitoire (non stocké) : générer le lien de visio à la création.
    generer_lien_auto = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Session
        fields = [
            'id', 'titre', 'description', 'lieu', 'date_debut', 'date_fin',
            'formateur', 'formateur_id', 'cours', 'cours_id',
            'participation_mode', 'statut', 'nb_presents', 'duree_minutes',
            'lien_visio', 'lien_jitsi', 'meet_space_name', 'meet_derniere_sync',
            'teams_join_url', 'teams_meeting_id',
            'visio_provider', 'generer_lien_auto',
            'invites',
            'institution', 'institution_nom',
            'annee_scolaire', 'annee_scolaire_nom'
        ]
        read_only_fields = ['id', 'duree_minutes', 'institution', 'annee_scolaire',
                            'meet_space_name', 'meet_derniere_sync',
                            'teams_join_url', 'teams_meeting_id']

    def validate(self, attrs):
        """Cohérence des dates + absence de conflit formateur/groupe."""
        debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        cours = attrs.get('cours', getattr(self.instance, 'cours', None))

        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin doit être postérieure à la date de début."}
            )

        if debut and fin and cours:
            base = Session.objects.filter(date_debut__lt=fin, date_fin__gt=debut)
            if self.instance is not None:
                base = base.exclude(pk=self.instance.pk)
            if base.filter(cours__enseignant_id=cours.enseignant_id).exists():
                raise serializers.ValidationError(
                    {"date_debut": "Le formateur a déjà une séance sur ce créneau."}
                )
            if base.filter(cours__groupe_id=cours.groupe_id).exists():
                raise serializers.ValidationError(
                    {"date_debut": "Ce groupe a déjà une séance sur ce créneau."}
                )
        return attrs

    # ── Visio : le lien n'est exposé qu'aux personnes CONCERNÉES ──────────
    # (formateur du cours = organisateur, ou apprenant inscrit ; + superuser).
    # Les autres (parent, admin/responsable, autres rôles) ne reçoivent pas le lien.
    _VISIO_FIELD_NAMES = (
        "lien_visio", "lien_jitsi", "teams_join_url",
        "meet_space_name", "teams_meeting_id",
    )

    @staticmethod
    def _peut_voir_visio(session, request) -> bool:
        user = getattr(request, "user", None) if request is not None else None
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        # Responsable académique : autorisé à rejoindre.
        try:
            from users.access_control import role_key
            if role_key(user) in ("responsable", "responsableacademique"):
                return True
        except Exception:
            pass
        try:
            if str(session.formateur_id) == str(user.pk):
                return True
        except Exception:
            pass

        # ✅ Fenêtre d'accès : 15 min avant le début, 30 min après la fin.
        try:
            from datetime import timedelta
            from django.utils import timezone
            if session.date_debut:
                now = timezone.now()
                if now < session.date_debut - timedelta(minutes=15):
                    return False
                if session.date_fin and now > session.date_fin + timedelta(minutes=30):
                    return False
        except Exception:
            pass
        try:
            from courses.models import InscriptionCours
            from django.db.models.functions import Lower
            return (
                InscriptionCours.objects
                .filter(cours_id=session.cours_id, apprenant_id=user.pk)
                .annotate(st=Lower("statut"))
                .filter(st__in=["inscrit", "en_cours", "en cours", "encours", "termine", "terminé"])
                .exists()
            )
        except Exception:
            return False

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._peut_voir_visio(instance, self.context.get("request")):
            for field in self._VISIO_FIELD_NAMES:
                if field in data:
                    data[field] = ""
        return data


class SessionLiteSerializer(serializers.ModelSerializer):
    """Serializer léger pour les sessions"""

    class Meta:
        model = Session
        fields = [
            "id", "titre", "date_debut", "date_fin",
            "cours", "formateur", "participation_mode",
            "statut", "nb_presents", "duree_minutes",
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