from rest_framework import serializers

from users.serializers import ApprenantSerializer, FormateurSerializer
from .models import Cours, InscriptionCours, Module, Participation, Sequence, Session, Suivi
        
        
# courses/serializers.py
from rest_framework import serializers
from academics.models import Groupe, Matiere
from users.models import Formateur
from .models import Cours


class CoursSerializer(serializers.ModelSerializer):
    # Read-only “labels” utiles côté UI
    groupe_nom = serializers.CharField(source="groupe.nom", read_only=True)
    matiere_nom = serializers.CharField(source="matiere.nom", read_only=True)
    enseignant_nom = serializers.SerializerMethodField(read_only=True)

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
        # Adaptation selon ton modèle Formateur (si prénom/nom existent)
        ens = getattr(obj, "enseignant", None)
        if not ens:
            return None
        prenom = getattr(ens, "prenom", "")
        nom = getattr(ens, "nom", "")
        full = (f"{prenom} {nom}").strip()
        return full or str(ens)

    def validate(self, attrs):
        """
        - date_fin >= date_debut si les deux sont fournis
        - unicité groupe+matiere+enseignant (proprement en API)
        """
        date_debut = attrs.get("date_debut", getattr(self.instance, "date_debut", None))
        date_fin = attrs.get("date_fin", getattr(self.instance, "date_fin", None))

        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date_fin doit être postérieure ou égale à date_debut."}
            )

        # Validation d'unicité (évite 500/IntegrityError)
        groupe = attrs.get("groupe", getattr(self.instance, "groupe", None))
        matiere = attrs.get("matiere", getattr(self.instance, "matiere", None))
        enseignant = attrs.get("enseignant", getattr(self.instance, "enseignant", None))

        if groupe and matiere and enseignant:
            qs = Cours.objects.filter(groupe=groupe, matiere=matiere, enseignant=enseignant)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Un cours avec ce groupe, cette matière et cet enseignant existe déjà."
                        ]
                    }
                )

        return attrs


class ModuleSerializer(serializers.ModelSerializer):
    cours = serializers.PrimaryKeyRelatedField(queryset=Cours.objects.all())

    class Meta:
        model = Module
        fields = ["id", "titre", "description", "cours"]


class SequenceSerializer(serializers.ModelSerializer):
    # Sérialiser l'attribut module lié (clé étrangère)
    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all())

    class Meta:
        model = Sequence
        fields = ['id', 'titre', 'module']

class InscriptionCoursSerializer(serializers.ModelSerializer):
    # Sérialiser les relations apprenant et cours avec des serializers imbriqués
    apprenant = ApprenantSerializer()
    cours = CoursSerializer()

    class Meta:
        model = InscriptionCours
        fields = ['id', 'apprenant', 'cours', 'date_inscription', 'statut']
        
        
class SuiviSerializer(serializers.ModelSerializer):
    apprenant = ApprenantSerializer()
    cours = CoursSerializer()

    class Meta:
        model = Suivi
        fields = ['id', 'apprenant', 'cours', 'date_debut', 'progression', 'note', 'commentaires']
        
        
class SessionSerializer(serializers.ModelSerializer):
    formateur = FormateurSerializer()
    cours = CoursSerializer()

    class Meta:
        model = Session
        fields = ['id', 'titre', 'date_debut', 'date_fin', 'formateur', 'cours']
        
        
class ParticipationSerializer(serializers.ModelSerializer):
    session = SessionSerializer()  # Sérialiser la session liée
    apprenant = ApprenantSerializer()  # Sérialiser l'apprenant lié

    class Meta:
        model = Participation
        fields = ['id', 'session', 'apprenant', 'date_participation']