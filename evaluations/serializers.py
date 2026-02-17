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
            'necessite_correction_manuelle',
            'est_qcm'
        ]
        read_only_fields = ['id', 'necessite_correction_manuelle', 'est_qcm']


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
    sequence_titre = serializers.CharField(
        source='sequence.titre',
        read_only=True
    )
    
    class Meta:
        model = Quiz
        fields = [
            'id', 
            'titre', 
            'description',
            'sequence',
            'sequence_titre',
            'date_creation',
            'date_modification',
            'nombre_questions'
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']


class QuizDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour un quiz avec toutes ses questions"""
    questions = QuestionSerializer(many=True, read_only=True)
    sequence_titre = serializers.CharField(
        source='sequence.titre',
        read_only=True
    )
    
    class Meta:
        model = Quiz
        fields = [
            'id', 
            'titre', 
            'description',
            'sequence',
            'sequence_titre',
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
    question_points = serializers.FloatField(
        source='question.points',
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
            'question_points',
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
    apprenant_nom = serializers.SerializerMethodField()
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
    
    def get_apprenant_nom(self, obj):
        try:
            return f"{obj.apprenant.prenom} {obj.apprenant.nom}"
        except:
            return str(obj.apprenant)
    
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
    type_evaluation_display = serializers.CharField(
        source='get_type_evaluation_display',
        read_only=True
    )
    cours_titre = serializers.CharField(source='cours.titre', read_only=True)

    enseignant_nom = serializers.SerializerMethodField()
    nombre_questions = serializers.IntegerField(read_only=True)
    est_accessible = serializers.SerializerMethodField()
    peut_soumettre = serializers.SerializerMethodField()
    est_auto_corrigeable = serializers.SerializerMethodField()
    

    # ✅ Nouveau: pour pouvoir lier des questions à la création / update
    questions_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

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
            'nombre_questions',
            'est_accessible',
            'peut_soumettre',
            'est_auto_corrigeable',
            'questions_ids'
        ]
        read_only_fields = [
            'id', 
            'date_creation', 
            'date_modification', 
            'nombre_questions',
            'est_accessible',
            'peut_soumettre',
            'est_auto_corrigeable',
            'questions_ids',
        ]
    
    def get_enseignant_nom(self, obj):
        try:
            return f"{obj.enseignant.prenom} {obj.enseignant.nom}"
        except:
            return str(obj.enseignant)
    
    def get_est_accessible(self, obj):
        return obj.est_accessible()
    
    def get_peut_soumettre(self, obj):
        return obj.peut_soumettre()
    
    def get_est_auto_corrigeable(self, obj):
        return obj.est_auto_corrigeable()


    def validate(self, attrs):
        type_eval = attrs.get('type_evaluation', getattr(self.instance, 'type_evaluation', None))
        consigne = attrs.get('consigne_texte', getattr(self.instance, 'consigne_texte', ''))
        fichier = attrs.get('fichier_sujet', getattr(self.instance, 'fichier_sujet', None))
        q_ids = attrs.get('questions_ids', None)

        # simple => consigne/fichier requis
        if type_eval == 'simple':
            if not consigne and not fichier:
                raise serializers.ValidationError({
                    'consigne_texte': "Une évaluation simple doit avoir une consigne texte ou un fichier sujet.",
                    'fichier_sujet': "Une évaluation simple doit avoir une consigne texte ou un fichier sujet.",
                })

        # structuree => au moins une question (à la création: questions_ids requis)
        if type_eval == 'structuree':
            if self.instance:
                # update: si pas fourni, on accepte (les questions peuvent déjà exister)
                if q_ids is not None and len(q_ids) == 0:
                    raise serializers.ValidationError({'questions_ids': "Ajoute au moins une question."})
            else:
                if not q_ids or len(q_ids) == 0:
                    raise serializers.ValidationError({'questions_ids': "Une évaluation structurée doit contenir au moins une question."})

        # mixte => consigne/fichier ET au moins une question
        if type_eval == 'mixte':
            if not consigne and not fichier:
                raise serializers.ValidationError({
                    'consigne_texte': "Une évaluation mixte doit avoir une consigne texte ou un fichier sujet.",
                    'fichier_sujet': "Une évaluation mixte doit avoir une consigne texte ou un fichier sujet.",
                })
            if self.instance:
                if q_ids is not None and len(q_ids) == 0:
                    raise serializers.ValidationError({'questions_ids': "Une évaluation mixte doit contenir au moins une question."})
            else:
                if not q_ids or len(q_ids) == 0:
                    raise serializers.ValidationError({'questions_ids': "Une évaluation mixte doit contenir au moins une question."})

        return attrs

    def create(self, validated_data):
        q_ids = validated_data.pop('questions_ids', [])
        evaluation = super().create(validated_data)

        if q_ids:
            # ⚠️ suppose que Question a FK evaluation (related_name='questions')
            evaluation.questions.filter(id__in=q_ids).update(evaluation=evaluation)
            # ou si relation M2M, il faut evaluation.questions.set(q_ids)

        return evaluation

    def update(self, instance, validated_data):
        q_ids = validated_data.pop('questions_ids', None)
        instance = super().update(instance, validated_data)

        if q_ids is not None:
            instance.questions.exclude(id__in=q_ids).update(evaluation=None)
            instance.questions.filter(id__in=q_ids).update(evaluation=instance)
            # si M2M: instance.questions.set(q_ids)

        return instance

class EvaluationDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour une évaluation avec ses questions"""
    questions = QuestionSerializer(many=True, read_only=True)
    type_evaluation_display = serializers.CharField(
        source='get_type_evaluation_display', 
        read_only=True
    )
    cours_titre = serializers.CharField(source='cours.titre', read_only=True)
    enseignant_nom = serializers.SerializerMethodField()
    est_accessible = serializers.SerializerMethodField()
    peut_soumettre = serializers.SerializerMethodField()
    est_auto_corrigeable = serializers.SerializerMethodField()
    
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
            'questions',
            'est_accessible',
            'peut_soumettre',
            'est_auto_corrigeable'
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']
    
    def get_enseignant_nom(self, obj):
        try:
            return f"{obj.enseignant.prenom} {obj.enseignant.nom}"
        except:
            return str(obj.enseignant)
    
    def get_est_accessible(self, obj):
        return obj.est_accessible()
    
    def get_peut_soumettre(self, obj):
        return obj.peut_soumettre()
    
    def get_est_auto_corrigeable(self, obj):
        return obj.est_auto_corrigeable()


class EvaluationAccessibiliteSerializer(serializers.Serializer):
    """Serializer pour les informations d'accessibilité d'une évaluation"""
    evaluation_id = serializers.IntegerField()
    est_publiee = serializers.BooleanField()
    est_accessible = serializers.BooleanField()
    peut_soumettre = serializers.BooleanField()
    date_debut = serializers.DateTimeField(allow_null=True)
    date_fin = serializers.DateTimeField(allow_null=True)
    passage_existe = serializers.BooleanField()
    passage = serializers.DictField(allow_null=True)
    action_possible = serializers.CharField(allow_null=True)


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
    question_type = serializers.CharField(
        source='question.type_question',
        read_only=True
    )
    question_mode_correction = serializers.CharField(
        source='question.mode_correction',
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
            'question_type',
            'question_mode_correction',
            'statut',
            'statut_display',
            'choix_selectionnes',
            'reponse_texte',
            'fichier_reponse',
            'points_obtenus',
            'commentaire_correcteur',
            'date_reponse',
            'date_modification',
            'date_correction',
            'pourcentage_reussite'
        ]
        read_only_fields = [
            'id', 
            'points_obtenus', 
            'date_reponse',
            'date_modification',
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
    evaluation_type = serializers.CharField(
        source='evaluation.type_evaluation',
        read_only=True
    )
    apprenant_nom = serializers.SerializerMethodField()
    statut_display = serializers.CharField(
        source='get_statut_display', 
        read_only=True
    )
    pourcentage = serializers.SerializerMethodField()
    est_corrige = serializers.BooleanField(read_only=True)
    necessite_correction = serializers.BooleanField(read_only=True)
    peut_etre_repris = serializers.SerializerMethodField()
    peut_etre_soumis = serializers.SerializerMethodField()
    
    class Meta:
        model = PassageEvaluation
        fields = [
            'id',
            'apprenant',
            'apprenant_nom',
            'evaluation',
            'evaluation_titre',
            'evaluation_bareme',
            'evaluation_type',
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
            'necessite_correction',
            'peut_etre_repris',
            'peut_etre_soumis'
        ]
        read_only_fields = [
            'id', 
            'date_debut', 
            'date_soumission', 
            'date_correction'
        ]
    
    def get_apprenant_nom(self, obj):
        try:
            return f"{obj.apprenant.prenom} {obj.apprenant.nom}"
        except:
            return str(obj.apprenant)
    
    def get_pourcentage(self, obj):
        return obj.pourcentage()
    
    def get_peut_etre_repris(self, obj):
        return obj.peut_etre_repris()
    
    def get_peut_etre_soumis(self, obj):
        return obj.peut_etre_soumis()


class PassageEvaluationDetailSerializer(PassageEvaluationSerializer):
    """Serializer détaillé avec toutes les réponses aux questions"""
    reponses_questions = ReponseQuestionSerializer(many=True, read_only=True)
    evaluation_details = serializers.SerializerMethodField()
    
    class Meta(PassageEvaluationSerializer.Meta):
        fields = PassageEvaluationSerializer.Meta.fields + [
            'reponses_questions',
            'evaluation_details'
        ]
    
    def get_evaluation_details(self, obj):
        """Retourne les détails complets de l'évaluation"""
        return {
            'id': obj.evaluation.id,
            'titre': obj.evaluation.titre,
            'type_evaluation': obj.evaluation.type_evaluation,
            'bareme': obj.evaluation.bareme,
            'duree_minutes': obj.evaluation.duree_minutes,
            'consigne_texte': obj.evaluation.consigne_texte,
            'fichier_sujet': obj.evaluation.fichier_sujet.url if obj.evaluation.fichier_sujet else None,
            'date_debut': obj.evaluation.date_debut,
            'date_fin': obj.evaluation.date_fin,
            'est_auto_corrigeable': obj.evaluation.est_auto_corrigeable()
        }


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
    
    def validate_points_obtenus(self, value):
        """Valider que les points ne dépassent pas le maximum"""
        instance = self.instance
        if instance and value > instance.question.points:
            raise serializers.ValidationError(
                f"Les points obtenus ({value}) ne peuvent pas dépasser "
                f"les points de la question ({instance.question.points})."
            )
        if value < 0:
            raise serializers.ValidationError(
                "Les points obtenus ne peuvent pas être négatifs."
            )
        return value


class CorrectionEvaluationSerializer(serializers.ModelSerializer):
    """Serializer pour corriger une évaluation complète"""
    
    class Meta:
        model = PassageEvaluation
        fields = [
            'id',
            'note',
            'commentaire_enseignant'
        ]
    
    def validate_note(self, value):
        """Valider que la note ne dépasse pas le barème"""
        instance = self.instance
        if instance and value > instance.evaluation.bareme:
            raise serializers.ValidationError(
                f"La note ({value}) ne peut pas dépasser "
                f"le barème ({instance.evaluation.bareme})."
            )
        if value < 0:
            raise serializers.ValidationError(
                "La note ne peut pas être négative."
            )
        return value


# ============================================================================
# SERIALIZERS STATISTIQUES
# ============================================================================

class StatistiquesApprenantSerializer(serializers.Serializer):
    """Serializer pour les statistiques d'un apprenant"""
    apprenant_id = serializers.IntegerField()
    
    # Quiz
    nombre_quiz_passes = serializers.IntegerField()
    score_moyen_quiz = serializers.FloatField()
    
    # Évaluations
    nombre_evaluations_passees = serializers.IntegerField()
    nombre_evaluations_corrigees = serializers.IntegerField()
    nombre_evaluations_en_attente = serializers.IntegerField()
    note_moyenne = serializers.FloatField()


class StatistiquesEvaluationSerializer(serializers.Serializer):
    """Serializer pour les statistiques d'une évaluation"""
    evaluation_id = serializers.IntegerField()
    
    nombre_passages = serializers.IntegerField()
    note_moyenne = serializers.FloatField()
    note_min = serializers.FloatField()
    note_max = serializers.FloatField()
    taux_reussite = serializers.FloatField()
    bareme = serializers.FloatField()