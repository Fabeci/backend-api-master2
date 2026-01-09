from rest_framework import serializers
from .models import (
    Quiz, 
    Question, 
    Reponse, 
    Evaluation, 
    PassageEvaluation,
    ReponseQuestion,
    PassageQuiz,
    ReponseQuiz
)


# ============================================================================
# SERIALIZERS DE BASE
# ============================================================================

class ReponseSerializer(serializers.ModelSerializer):
    """Serializer pour les réponses prédéfinies (choix de QCM)"""
    class Meta:
        model = Reponse
        fields = [
            'id', 
            'texte', 
            'question', 
            'est_correcte', 
            'ordre'
        ]
        read_only_fields = ['id']


class QuestionSerializer(serializers.ModelSerializer):
    """Serializer pour les questions (avec réponses imbriquées)"""
    reponses_predefinies = ReponseSerializer(many=True, read_only=True)
    type_question_display = serializers.CharField(
        source='get_type_question_display', 
        read_only=True
    )
    mode_correction_display = serializers.CharField(
        source='get_mode_correction_display', 
        read_only=True
    )
    
    class Meta:
        model = Question
        fields = [
            'id',
            'enonce_texte',
            'fichier_enonce',
            'type_question',
            'type_question_display',
            'mode_correction',
            'mode_correction_display',
            'points',
            'ordre',
            'indication_reponse',
            'quiz',
            'evaluation',
            'reponses_predefinies',
            'necessite_correction_manuelle'
        ]
        read_only_fields = ['id', 'necessite_correction_manuelle']


class QuestionCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer une question avec ses réponses"""
    reponses = ReponseSerializer(many=True, required=False)
    
    class Meta:
        model = Question
        fields = [
            'enonce_texte',
            'fichier_enonce',
            'type_question',
            'points',
            'ordre',
            'indication_reponse',
            'quiz',
            'evaluation',
            'reponses'
        ]
    
    def create(self, validated_data):
        reponses_data = validated_data.pop('reponses', [])
        question = Question.objects.create(**validated_data)
        
        # Créer les réponses prédéfinies si présentes
        for reponse_data in reponses_data:
            Reponse.objects.create(question=question, **reponse_data)
        
        return question


# ============================================================================
# SERIALIZERS POUR QUIZ
# ============================================================================

class QuizSerializer(serializers.ModelSerializer):
    """Serializer pour les quiz"""
    nombre_questions = serializers.IntegerField(
        source='questions.count', 
        read_only=True
    )
    
    class Meta:
        model = Quiz
        fields = [
            'id', 
            'titre', 
            'description',
            'sequence', 
            'date_creation',
            'date_modification',
            'nombre_questions'
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']


class QuizDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour un quiz avec toutes ses questions"""
    questions = QuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            'id', 
            'titre', 
            'description',
            'sequence', 
            'date_creation',
            'date_modification',
            'questions'
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']


class ReponseQuizSerializer(serializers.ModelSerializer):
    """Serializer pour les réponses aux questions de quiz"""
    question_texte = serializers.CharField(
        source='question.enonce_texte', 
        read_only=True
    )
    pourcentage = serializers.SerializerMethodField()
    
    class Meta:
        model = ReponseQuiz
        fields = [
            'id',
            'passage_quiz',
            'question',
            'question_texte',
            'choix_selectionnes',
            'points_obtenus',
            'date_reponse',
            'pourcentage'
        ]
        read_only_fields = ['id', 'points_obtenus', 'date_reponse']
    
    def get_pourcentage(self, obj):
        if obj.question.points == 0:
            return 0
        return round((obj.points_obtenus / obj.question.points) * 100, 2)


class PassageQuizSerializer(serializers.ModelSerializer):
    """Serializer pour un passage de quiz"""
    quiz_titre = serializers.CharField(source='quiz.titre', read_only=True)
    apprenant_nom = serializers.CharField(
        source='apprenant.user.get_full_name', 
        read_only=True
    )
    pourcentage = serializers.SerializerMethodField()
    
    class Meta:
        model = PassageQuiz
        fields = [
            'id',
            'apprenant',
            'apprenant_nom',
            'quiz',
            'quiz_titre',
            'score',
            'date_passage',
            'termine',
            'pourcentage'
        ]
        read_only_fields = ['id', 'score', 'date_passage']
    
    def get_pourcentage(self, obj):
        total_points = sum(q.points for q in obj.quiz.questions.all())
        if total_points == 0:
            return 0
        return round((obj.score / total_points) * 100, 2)


class PassageQuizDetailSerializer(PassageQuizSerializer):
    """Serializer détaillé avec toutes les réponses"""
    reponses_quiz = ReponseQuizSerializer(many=True, read_only=True)
    
    class Meta(PassageQuizSerializer.Meta):
        fields = PassageQuizSerializer.Meta.fields + ['reponses_quiz']


# ============================================================================
# SERIALIZERS POUR ÉVALUATIONS
# ============================================================================

class EvaluationSerializer(serializers.ModelSerializer):
    """Serializer pour les évaluations"""
    type_evaluation_display = serializers.CharField(
        source='get_type_evaluation_display', 
        read_only=True
    )
    cours_titre = serializers.CharField(source='cours.titre', read_only=True)
    enseignant_nom = serializers.CharField(
        source='enseignant.user.get_full_name', 
        read_only=True
    )
    nombre_questions = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Evaluation
        fields = [
            'id',
            'cours',
            'cours_titre',
            'enseignant',
            'enseignant_nom',
            'titre',
            'type_evaluation',
            'type_evaluation_display',
            'bareme',
            'duree_minutes',
            'consigne_texte',
            'fichier_sujet',
            'date_debut',
            'date_fin',
            'date_creation',
            'date_modification',
            'est_publiee',
            'nombre_questions'
        ]
        read_only_fields = [
            'id', 
            'date_creation', 
            'date_modification', 
            'nombre_questions'
        ]


class EvaluationDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour une évaluation avec ses questions"""
    questions = QuestionSerializer(many=True, read_only=True)
    type_evaluation_display = serializers.CharField(
        source='get_type_evaluation_display', 
        read_only=True
    )
    
    class Meta:
        model = Evaluation
        fields = [
            'id',
            'cours',
            'enseignant',
            'titre',
            'type_evaluation',
            'type_evaluation_display',
            'bareme',
            'duree_minutes',
            'consigne_texte',
            'fichier_sujet',
            'date_debut',
            'date_fin',
            'date_creation',
            'date_modification',
            'est_publiee',
            'questions'
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']


class ReponseQuestionSerializer(serializers.ModelSerializer):
    """Serializer pour les réponses aux questions d'évaluation"""
    question_enonce = serializers.CharField(
        source='question.enonce_texte', 
        read_only=True
    )
    question_points = serializers.FloatField(
        source='question.points', 
        read_only=True
    )
    statut_display = serializers.CharField(
        source='get_statut_display', 
        read_only=True
    )
    pourcentage_reussite = serializers.FloatField(read_only=True)
    
    class Meta:
        model = ReponseQuestion
        fields = [
            'id',
            'passage_evaluation',
            'question',
            'question_enonce',
            'question_points',
            'statut',
            'statut_display',
            'choix_selectionnes',
            'reponse_texte',
            'fichier_reponse',
            'points_obtenus',
            'commentaire_correcteur',
            'date_reponse',
            'date_correction',
            'pourcentage_reussite'
        ]
        read_only_fields = [
            'id', 
            'points_obtenus', 
            'date_reponse', 
            'date_correction'
        ]


class ReponseQuestionCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer/soumettre une réponse"""
    
    class Meta:
        model = ReponseQuestion
        fields = [
            'passage_evaluation',
            'question',
            'choix_selectionnes',
            'reponse_texte',
            'fichier_reponse'
        ]
    
    def create(self, validated_data):
        choix = validated_data.pop('choix_selectionnes', [])
        reponse = ReponseQuestion.objects.create(**validated_data)
        
        if choix:
            reponse.choix_selectionnes.set(choix)
        
        # Auto-correction pour les QCM
        if reponse.question.mode_correction == 'automatique':
            reponse.calculer_points_automatique()
        else:
            reponse.statut = 'repondu'
            reponse.save()
        
        return reponse


class PassageEvaluationSerializer(serializers.ModelSerializer):
    """Serializer pour un passage d'évaluation"""
    evaluation_titre = serializers.CharField(
        source='evaluation.titre', 
        read_only=True
    )
    evaluation_bareme = serializers.FloatField(
        source='evaluation.bareme', 
        read_only=True
    )
    apprenant_nom = serializers.CharField(
        source='apprenant.user.get_full_name', 
        read_only=True
    )
    statut_display = serializers.CharField(
        source='get_statut_display', 
        read_only=True
    )
    pourcentage = serializers.SerializerMethodField()
    est_corrige = serializers.BooleanField(read_only=True)
    necessite_correction = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = PassageEvaluation
        fields = [
            'id',
            'apprenant',
            'apprenant_nom',
            'evaluation',
            'evaluation_titre',
            'evaluation_bareme',
            'statut',
            'statut_display',
            'reponse_texte',
            'fichier_reponse',
            'note',
            'commentaire_enseignant',
            'date_debut',
            'date_soumission',
            'date_correction',
            'pourcentage',
            'est_corrige',
            'necessite_correction'
        ]
        read_only_fields = [
            'id', 
            'date_debut', 
            'date_soumission', 
            'date_correction'
        ]
    
    def get_pourcentage(self, obj):
        return obj.pourcentage()


class PassageEvaluationDetailSerializer(PassageEvaluationSerializer):
    """Serializer détaillé avec toutes les réponses aux questions"""
    reponses_questions = ReponseQuestionSerializer(many=True, read_only=True)
    
    class Meta(PassageEvaluationSerializer.Meta):
        fields = PassageEvaluationSerializer.Meta.fields + ['reponses_questions']


class PassageEvaluationCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un passage d'évaluation"""
    
    class Meta:
        model = PassageEvaluation
        fields = [
            'apprenant',
            'evaluation',
            'reponse_texte',
            'fichier_reponse'
        ]
    
    def create(self, validated_data):
        # Créer le passage
        passage = PassageEvaluation.objects.create(**validated_data)
        
        # Pour les évaluations structurées, créer les réponses vides
        if passage.evaluation.type_evaluation == 'structuree':
            for question in passage.evaluation.questions.all():
                ReponseQuestion.objects.create(
                    passage_evaluation=passage,
                    question=question
                )
        
        return passage


class CorrectionReponseSerializer(serializers.ModelSerializer):
    """Serializer pour la correction manuelle d'une réponse"""
    
    class Meta:
        model = ReponseQuestion
        fields = [
            'id',
            'points_obtenus',
            'commentaire_correcteur'
        ]
    
    def update(self, instance, validated_data):
        instance.points_obtenus = validated_data.get(
            'points_obtenus', 
            instance.points_obtenus
        )
        instance.commentaire_correcteur = validated_data.get(
            'commentaire_correcteur', 
            instance.commentaire_correcteur
        )
        instance.statut = 'corrige'
        instance.date_correction = serializers.DateTimeField().to_representation(
            serializers.DateTimeField.now()
        )
        instance.save()
        return instance


class CorrectionEvaluationSerializer(serializers.ModelSerializer):
    """Serializer pour corriger une évaluation complète"""
    
    class Meta:
        model = PassageEvaluation
        fields = [
            'id',
            'note',
            'commentaire_enseignant',
            'statut'
        ]
    
    def update(self, instance, validated_data):
        instance.note = validated_data.get('note', instance.note)
        instance.commentaire_enseignant = validated_data.get(
            'commentaire_enseignant', 
            instance.commentaire_enseignant
        )
        instance.statut = 'corrige'
        instance.date_correction = serializers.DateTimeField().to_representation(
            serializers.DateTimeField.now()
        )
        instance.save()
        return instance


# ============================================================================
# SERIALIZERS STATISTIQUES
# ============================================================================

class StatistiquesApprenantSerializer(serializers.Serializer):
    """Serializer pour les statistiques d'un apprenant"""
    apprenant_id = serializers.IntegerField()
    apprenant_nom = serializers.CharField()
    
    # Quiz
    nombre_quiz_passes = serializers.IntegerField()
    score_moyen_quiz = serializers.FloatField()
    
    # Évaluations
    nombre_evaluations_passees = serializers.IntegerField()
    nombre_evaluations_corrigees = serializers.IntegerField()
    note_moyenne = serializers.FloatField()
    pourcentage_reussite = serializers.FloatField()


class StatistiquesEvaluationSerializer(serializers.Serializer):
    """Serializer pour les statistiques d'une évaluation"""
    evaluation_id = serializers.IntegerField()
    evaluation_titre = serializers.CharField()
    
    nombre_passages = serializers.IntegerField()
    nombre_corriges = serializers.IntegerField()
    note_moyenne = serializers.FloatField()
    note_min = serializers.FloatField()
    note_max = serializers.FloatField()
    taux_reussite = serializers.FloatField()  # % ayant >= 10/20