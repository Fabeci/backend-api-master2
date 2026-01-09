# progress/serializers.py

from rest_framework import serializers
from .models import (
    ProgressionApprenant,
    ProgressionModule,
    ProgressionSequence,
    ProgressionQuiz,
    HistoriqueActivite,
    PlanAction,
    ObjectifPlanAction,
)
from evaluations.models import PassageEvaluation


# ============================================================================
# SERIALIZERS DE BASE
# ============================================================================

class ObjectifPlanActionSerializer(serializers.ModelSerializer):
    """Serializer pour les objectifs d'un plan d'action"""
    
    class Meta:
        model = ObjectifPlanAction
        fields = [
            'id',
            'plan_action',
            'titre',
            'description',
            'est_complete',
            'date_completion',
            'ordre',
        ]
        read_only_fields = ['date_completion']


class PlanActionSerializer(serializers.ModelSerializer):
    """Serializer pour les plans d'action"""
    
    objectifs = ObjectifPlanActionSerializer(many=True, read_only=True)
    pourcentage_completion = serializers.ReadOnlyField()
    est_en_retard = serializers.ReadOnlyField()
    cree_par_nom = serializers.CharField(
        source='cree_par.nom',
        read_only=True
    )
    cree_par_prenom = serializers.CharField(
        source='cree_par.prenom',
        read_only=True
    )
    cours_titre = serializers.CharField(
        source='cours.titre',
        read_only=True
    )
    
    class Meta:
        model = PlanAction
        fields = [
            'id',
            'apprenant',
            'cours',
            'cours_titre',
            'titre',
            'description',
            'date_creation',
            'date_echeance',
            'date_completion',
            'statut',
            'priorite',
            'cree_par',
            'cree_par_nom',
            'cree_par_prenom',
            'objectifs',
            'pourcentage_completion',
            'est_en_retard',
        ]
        read_only_fields = ['date_creation', 'date_completion']


class HistoriqueActiviteSerializer(serializers.ModelSerializer):
    """Serializer pour l'historique des activités"""
    
    type_activite_display = serializers.CharField(
        source='get_type_activite_display',
        read_only=True
    )
    
    class Meta:
        model = HistoriqueActivite
        fields = [
            'id',
            'apprenant',
            'type_activite',
            'type_activite_display',
            'objet_type',
            'objet_id',
            'date_activite',
            'duree_minutes',
            'description',
            'metadata',
        ]
        read_only_fields = ['date_activite']


class ProgressionSequenceSerializer(serializers.ModelSerializer):
    """Serializer pour la progression dans une séquence"""
    
    sequence_titre = serializers.CharField(
        source='sequence.titre',
        read_only=True
    )
    
    class Meta:
        model = ProgressionSequence
        fields = [
            'id',
            'progression_module',
            'sequence',
            'sequence_titre',
            'date_debut',
            'date_fin',
            'temps_passe_minutes',
            'est_terminee',
            'pourcentage_completion',
            'nombre_visites',
        ]
        read_only_fields = [
            'date_debut',
            'date_fin',
            'pourcentage_completion',
        ]


class ProgressionModuleSerializer(serializers.ModelSerializer):
    """Serializer pour la progression dans un module"""
    
    module_titre = serializers.CharField(
        source='module.titre',
        read_only=True
    )
    progressions_sequences = ProgressionSequenceSerializer(
        many=True,
        read_only=True
    )
    
    class Meta:
        model = ProgressionModule
        fields = [
            'id',
            'progression_apprenant',
            'module',
            'module_titre',
            'date_debut',
            'date_fin',
            'temps_passe_minutes',
            'est_termine',
            'pourcentage_completion',
            'progressions_sequences',
        ]
        read_only_fields = [
            'date_debut',
            'date_fin',
            'pourcentage_completion',
        ]


class ProgressionQuizSerializer(serializers.ModelSerializer):
    """Serializer pour la progression dans un quiz"""
    
    quiz_titre = serializers.CharField(
        source='passage_quiz.quiz.titre',
        read_only=True
    )
    
    class Meta:
        model = ProgressionQuiz
        fields = [
            'id',
            'progression_apprenant',
            'passage_quiz',
            'quiz_titre',
            'date_passage',
            'score',
            'temps_passe_minutes',
            'pourcentage_reussite',
            'numero_tentative',
        ]
        read_only_fields = [
            'date_passage',
            'score',
            'pourcentage_reussite',
            'numero_tentative',
        ]


class PassageEvaluationSimpleSerializer(serializers.ModelSerializer):
    """Serializer simplifié pour les passages d'évaluation"""
    
    evaluation_titre = serializers.CharField(
        source='evaluation.titre',
        read_only=True
    )
    pourcentage = serializers.SerializerMethodField()
    
    class Meta:
        model = PassageEvaluation
        fields = [
            'id',
            'evaluation',
            'evaluation_titre',
            'statut',
            'note',
            'date_debut',
            'date_soumission',
            'pourcentage',
        ]
    
    def get_pourcentage(self, obj):
        return obj.pourcentage()


class ProgressionApprenantSerializer(serializers.ModelSerializer):
    """Serializer pour la progression globale d'un apprenant"""
    
    apprenant_nom = serializers.CharField(
        source='apprenant.nom',
        read_only=True
    )
    apprenant_prenom = serializers.CharField(
        source='apprenant.prenom',
        read_only=True
    )
    cours_titre = serializers.CharField(
        source='cours.titre',
        read_only=True
    )
    temps_total_formate = serializers.ReadOnlyField()
    est_termine = serializers.ReadOnlyField()
    nombre_evaluations_reussies = serializers.ReadOnlyField()
    
    # Sous-progressions
    progressions_modules = ProgressionModuleSerializer(
        many=True,
        read_only=True
    )
    progressions_quiz = ProgressionQuizSerializer(
        many=True,
        read_only=True
    )
    
    # Évaluations (depuis PassageEvaluation)
    evaluations_passees = serializers.SerializerMethodField()
    
    class Meta:
        model = ProgressionApprenant
        fields = [
            'id',
            'apprenant',
            'apprenant_nom',
            'apprenant_prenom',
            'cours',
            'cours_titre',
            'date_debut',
            'date_derniere_activite',
            'date_completion',
            'pourcentage_completion',
            'temps_total_minutes',
            'temps_total_formate',
            'statut',
            'derniere_sequence',
            'dernier_module',
            'note_moyenne_evaluations',
            'taux_reussite_quiz',
            'est_termine',
            'nombre_evaluations_reussies',
            'progressions_modules',
            'progressions_quiz',
            'evaluations_passees',
        ]
        read_only_fields = [
            'date_debut',
            'date_derniere_activite',
            'date_completion',
            'pourcentage_completion',
            'temps_total_minutes',
            'note_moyenne_evaluations',
            'taux_reussite_quiz',
        ]
    
    def get_evaluations_passees(self, obj):
        """Récupère les évaluations passées depuis PassageEvaluation"""
        passages = PassageEvaluation.objects.filter(
            apprenant=obj.apprenant,
            evaluation__cours=obj.cours
        )
        return PassageEvaluationSimpleSerializer(passages, many=True).data


class ProgressionApprenantDetailSerializer(ProgressionApprenantSerializer):
    """Serializer détaillé avec historique et plans d'action"""
    
    historique_recent = serializers.SerializerMethodField()
    plans_action = serializers.SerializerMethodField()
    
    class Meta(ProgressionApprenantSerializer.Meta):
        fields = ProgressionApprenantSerializer.Meta.fields + [
            'historique_recent',
            'plans_action',
        ]
    
    def get_historique_recent(self, obj):
        """Dernières 10 activités"""
        activites = obj.apprenant.historique_activites.all()[:10]
        return HistoriqueActiviteSerializer(activites, many=True).data
    
    def get_plans_action(self, obj):
        """Plans d'action liés au cours"""
        plans = obj.apprenant.plans_action.filter(cours=obj.cours)
        return PlanActionSerializer(plans, many=True).data


# ============================================================================
# SERIALIZERS DE CRÉATION
# ============================================================================

class ProgressionApprenantCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer une progression"""
    
    class Meta:
        model = ProgressionApprenant
        fields = ['apprenant', 'cours']
    
    def validate(self, data):
        """Vérifier que l'apprenant est inscrit au cours"""
        from courses.models import InscriptionCours
        
        if not InscriptionCours.objects.filter(
            apprenant=data['apprenant'],
            cours=data['cours']
        ).exists():
            raise serializers.ValidationError(
                "L'apprenant n'est pas inscrit à ce cours."
            )
        
        return data


class PlanActionCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un plan d'action"""
    
    objectifs = ObjectifPlanActionSerializer(many=True, required=False)
    
    class Meta:
        model = PlanAction
        fields = [
            'apprenant',
            'cours',
            'titre',
            'description',
            'date_echeance',
            'priorite',
            'cree_par',
            'objectifs',
        ]
    
    def create(self, validated_data):
        objectifs_data = validated_data.pop('objectifs', [])
        plan = PlanAction.objects.create(**validated_data)
        
        for objectif_data in objectifs_data:
            ObjectifPlanAction.objects.create(plan_action=plan, **objectif_data)
        
        return plan