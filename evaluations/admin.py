# evaluations/admin.py

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Quiz,
    Question,
    Reponse,
    Evaluation,
    PassageEvaluation,
    ReponseQuestion,
    PassageQuiz,
    ReponseQuiz,
)


# ============================================================================
# FORMS PERSONNALISÉS
# ============================================================================

class QuestionAdminForm(forms.ModelForm):
    """Form personnalisé avec choix dynamiques selon le contexte"""

    class Meta:
        model = Question
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)

        # Configurer le champ mode_correction
        if "mode_correction" in self.fields:
            self.fields["mode_correction"].help_text = (
                "ℹ️ Se définit automatiquement selon le type de question : "
                "<strong>Automatique</strong> pour QCM, <strong>Manuel</strong> pour texte/fichier."
            )

        # Déterminer contexte (quiz ou évaluation)
        quiz = None
        evaluation = None

        if instance and instance.pk:
            quiz = instance.quiz
            evaluation = instance.evaluation
        else:
            if self.data.get("quiz"):
                try:
                    quiz = Quiz.objects.get(pk=self.data.get("quiz"))
                except (Quiz.DoesNotExist, ValueError):
                    pass
            if self.data.get("evaluation"):
                try:
                    evaluation = Evaluation.objects.get(pk=self.data.get("evaluation"))
                except (Evaluation.DoesNotExist, ValueError):
                    pass

        # Appliquer les choix appropriés
        if quiz:
            self.fields["type_question"].choices = Question.TYPE_CHOICES_QUIZ
            self.fields["type_question"].help_text = "⚠️ <strong>Les quiz n'acceptent que les questions QCM.</strong>"
            if "evaluation" in self.fields:
                self.fields["evaluation"].widget = forms.HiddenInput()
        elif evaluation:
            self.fields["type_question"].choices = Question.TYPE_CHOICES_EVALUATION
            self.fields["type_question"].help_text = "ℹ️ <strong>Les évaluations acceptent tous les types de questions.</strong>"
            if "quiz" in self.fields:
                self.fields["quiz"].widget = forms.HiddenInput()
        else:
            self.fields["type_question"].choices = Question.TYPE_CHOICES_EVALUATION
            self.fields["type_question"].help_text = "⚠️ <strong>Sélectionnez d'abord un quiz ou une évaluation.</strong>"

    def clean_mode_correction(self):
        """Forcer la bonne valeur selon type_question"""
        type_question = self.cleaned_data.get("type_question")
        return "automatique" if type_question in ["choix_unique", "choix_multiple"] else "manuelle"

    def clean(self):
        cleaned = super().clean()
        type_question = cleaned.get("type_question")
        quiz = cleaned.get("quiz")
        evaluation = cleaned.get("evaluation")

        # Validation 1: Appartenance exclusive
        if not quiz and not evaluation:
            raise ValidationError("Une question doit être associée à un quiz ou une évaluation.")
        if quiz and evaluation:
            raise ValidationError("Une question ne peut pas appartenir aux deux à la fois.")

        # Validation 2: Type autorisé pour quiz
        if quiz and type_question not in ["choix_unique", "choix_multiple"]:
            raise ValidationError({"type_question": "Les quiz n'acceptent que les questions à choix (QCM)."})

        # Validation 3: Forcer le mode de correction
        cleaned["mode_correction"] = "automatique" if type_question in ["choix_unique", "choix_multiple"] else "manuelle"
        
        return cleaned


class ReponseAdminForm(forms.ModelForm):
    """Form pour valider les réponses prédéfinies"""
    
    class Meta:
        model = Reponse
        fields = "__all__"
    
    def clean(self):
        cleaned = super().clean()
        question = cleaned.get("question")
        est_correcte = cleaned.get("est_correcte")
        
        # Vérifier que la question est bien un QCM
        if question and question.type_question not in ["choix_unique", "choix_multiple"]:
            raise ValidationError(
                f"Impossible d'ajouter une réponse prédéfinie à une question de type "
                f"'{question.get_type_question_display()}'. Seules les questions QCM acceptent des réponses prédéfinies."
            )
        
        # Pour choix unique, vérifier qu'il n'y a qu'une seule réponse correcte
        if question and question.type_question == "choix_unique" and est_correcte:
            autres_correctes = Reponse.objects.filter(
                question=question,
                est_correcte=True
            ).exclude(pk=self.instance.pk if self.instance.pk else None)
            
            if autres_correctes.exists():
                raise ValidationError(
                    "Cette question à choix unique a déjà une réponse correcte. "
                    "Veuillez d'abord décocher l'autre réponse correcte."
                )
        
        return cleaned


# ============================================================================
# INLINE ADMIN
# ============================================================================

class ReponseInline(admin.TabularInline):
    """Affiche les réponses prédéfinies UNIQUEMENT pour les QCM"""
    model = Reponse
    form = ReponseAdminForm
    extra = 0  # Pas de lignes vides par défaut
    fields = ["texte", "est_correcte", "ordre"]
    ordering = ["ordre"]
    
    def get_extra(self, request, obj=None, **kwargs):
        """Définir le nombre de lignes vides selon le type de question"""
        if obj and obj.type_question in ["choix_unique", "choix_multiple"]:
            # Si pas encore de réponses, proposer 4 lignes
            if obj.reponses_predefinies.count() == 0:
                return 4
            # Sinon, proposer 1 ligne supplémentaire
            return 1
        # Pour les questions non-QCM, aucune ligne
        return 0
    
    def get_max_num(self, request, obj=None, **kwargs):
        """Limiter le nombre de réponses selon le type"""
        if obj and obj.type_question in ["choix_unique", "choix_multiple"]:
            return 10  # Max 10 réponses pour un QCM
        return 0  # Aucune réponse pour les questions non-QCM
    
    def has_add_permission(self, request, obj=None):
        """Autoriser l'ajout UNIQUEMENT pour les QCM"""
        if obj and obj.type_question in ["choix_unique", "choix_multiple"]:
            return True
        return False
    
    def get_formset(self, request, obj=None, **kwargs):
        """Personnaliser le formset selon le type de question"""
        formset = super().get_formset(request, obj, **kwargs)
        
        # Si ce n'est pas un QCM, désactiver complètement
        if obj and obj.type_question not in ["choix_unique", "choix_multiple"]:
            formset.max_num = 0
            formset.extra = 0
        
        return formset


class QuestionInlineQuiz(admin.TabularInline):
    """Affiche les questions dans l'admin des quiz"""
    model = Question
    extra = 0
    fields = ["enonce_texte", "type_question", "mode_correction", "points", "ordre"]
    readonly_fields = ["enonce_texte", "type_question", "mode_correction", "points"]
    ordering = ["ordre"]
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class QuestionInlineEvaluation(admin.TabularInline):
    """Affiche les questions dans l'admin des évaluations"""
    model = Question
    extra = 0
    fields = ["enonce_texte", "type_question", "mode_correction", "points", "ordre"]
    readonly_fields = ["enonce_texte", "type_question", "mode_correction", "points"]
    ordering = ["ordre"]
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ReponseQuestionInline(admin.TabularInline):
    """Affiche les réponses dans l'admin des passages d'évaluation"""
    model = ReponseQuestion
    extra = 0
    fields = ["question", "statut", "points_obtenus", "voir_details"]
    readonly_fields = ["question", "statut", "voir_details"]
    can_delete = False

    def voir_details(self, obj):
        if obj.pk:
            url = reverse("admin:evaluations_reponsequestion_change", args=[obj.pk])
            return format_html('<a href="{}">Voir/Corriger</a>', url)
        return "-"

    voir_details.short_description = "Actions"

    def has_add_permission(self, request, obj=None):
        return False


class ReponseQuizInline(admin.TabularInline):
    """Affiche les réponses dans l'admin des passages de quiz"""
    model = ReponseQuiz
    extra = 0
    fields = ["question", "points_obtenus"]
    readonly_fields = ["question", "points_obtenus"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# ============================================================================
# ADMIN QUIZ
# ============================================================================

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ["id","titre", "sequence", "nombre_questions_display", "date_creation", "voir_questions"]
    list_filter = ["sequence", "date_creation"]
    search_fields = ["titre", "description", "sequence__titre"]
    readonly_fields = ["date_creation", "date_modification"]

    fieldsets = (
        ("Informations générales", {"fields": ("titre", "sequence", "description")}),
        ("Dates", {"fields": ("date_creation", "date_modification"), "classes": ("collapse",)}),
    )

    inlines = [QuestionInlineQuiz]

    def nombre_questions_display(self, obj):
        count = obj.questions.count()
        return format_html(
            '<span style="background-color: #4CAF50; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            count,
        )

    nombre_questions_display.short_description = "Questions"

    def voir_questions(self, obj):
        url = f"/admin/evaluations/question/?quiz__id__exact={obj.id}"
        return format_html('<a class="button" href="{}">Voir les questions →</a>', url)

    voir_questions.short_description = "Actions"


# ============================================================================
# ADMIN QUESTIONS
# ============================================================================

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionAdminForm

    list_display = ["id", "enonce_court", "appartenance", "type_question", "mode_correction_display", "points", "ordre", "nombre_reponses"]
    list_filter = ["type_question", "mode_correction", ("quiz", admin.EmptyFieldListFilter), ("evaluation", admin.EmptyFieldListFilter)]
    search_fields = ["enonce_texte"]

    fieldsets = (
        ("Appartenance", {
            "fields": ("quiz", "evaluation"), 
            "description": "⚠️ <strong>Choisissez soit un quiz (QCM uniquement), soit une évaluation (tous types).</strong>"
        }),
        ("Énoncé", {"fields": ("enonce_texte", "fichier_enonce")}),
        ("Configuration", {
            "fields": ("type_question", "mode_correction", "points", "ordre"), 
            "description": "ℹ️ Le <strong>mode de correction</strong> se définit automatiquement selon le type de question."
        }),
        ("Indication (pour réponses libres)", {"fields": ("indication_reponse",), "classes": ("collapse",)}),
    )

    inlines = [ReponseInline]

    def get_inline_instances(self, request, obj=None):
        """Afficher les inlines UNIQUEMENT si c'est un QCM"""
        if obj and obj.type_question in ["choix_unique", "choix_multiple"]:
            return super().get_inline_instances(request, obj)
        return []

    def enonce_court(self, obj):
        return obj.enonce_texte[:70] + "..." if len(obj.enonce_texte) > 70 else obj.enonce_texte

    enonce_court.short_description = "Énoncé"

    def appartenance(self, obj):
        if obj.quiz:
            return format_html('<span style="color:#2196F3;font-weight:bold;">📝 Quiz: {}</span>', obj.quiz.titre)
        if obj.evaluation:
            return format_html('<span style="color:#FF9800;font-weight:bold;">📊 Évaluation: {}</span>', obj.evaluation.titre)
        return "-"

    appartenance.short_description = "Appartient à"

    def mode_correction_display(self, obj):
        if obj.mode_correction == "automatique":
            return format_html('<span style="background:#4CAF50;color:white;padding:3px 10px;border-radius:3px;font-weight:bold;">🤖 Auto</span>')
        return format_html('<span style="background:#FF9800;color:white;padding:3px 10px;border-radius:3px;font-weight:bold;">✍️ Manuel</span>')

    mode_correction_display.short_description = "Correction"

    def nombre_reponses(self, obj):
        # Si ce n'est pas un QCM
        if obj.type_question not in ["choix_unique", "choix_multiple"]:
            return format_html('<span style="color:gray;font-style:italic;">N/A (réponse libre)</span>')

        # Si c'est un QCM
        count = obj.reponses_predefinies.count()
        if count == 0:
            return format_html('<span style="color:red;font-weight:bold;">⚠️ Aucune réponse</span>')

        correctes = obj.reponses_predefinies.filter(est_correcte=True).count()
        
        # Validation selon le type
        if obj.type_question == "choix_unique" and correctes != 1:
            return format_html(
                '<span style="color:orange;font-weight:bold;">⚠️ {} réponses ({} correcte(s)) - Il faut exactement 1 réponse correcte!</span>',
                count, correctes
            )
        elif obj.type_question == "choix_multiple" and correctes == 0:
            return format_html(
                '<span style="color:orange;font-weight:bold;">⚠️ {} réponses (0 correcte) - Il faut au moins 1 réponse correcte!</span>',
                count
            )
        
        return format_html('<span style="color:green;">{} réponses ({} correcte(s))</span>', count, correctes)

    nombre_reponses.short_description = "Réponses"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Avertir si QCM sans réponses
        if obj.type_question in ["choix_unique", "choix_multiple"]:
            count = obj.reponses_predefinies.count()
            correctes = obj.reponses_predefinies.filter(est_correcte=True).count()
            
            if count == 0:
                self.message_user(
                    request, 
                    "⚠️ N'oubliez pas d'ajouter des réponses prédéfinies à cette question QCM !", 
                    level="WARNING"
                )
            elif obj.type_question == "choix_unique" and correctes != 1:
                self.message_user(
                    request,
                    f"⚠️ Une question à choix unique doit avoir exactement 1 réponse correcte (actuellement: {correctes}).",
                    level="WARNING"
                )
            elif obj.type_question == "choix_multiple" and correctes == 0:
                self.message_user(
                    request,
                    "⚠️ Une question à choix multiple doit avoir au moins 1 réponse correcte.",
                    level="WARNING"
                )


# ============================================================================
# ADMIN RÉPONSES PRÉDÉFINIES
# ============================================================================

@admin.register(Reponse)
class ReponseAdmin(admin.ModelAdmin):
    form = ReponseAdminForm
    
    list_display = ["id", "texte_court", "question_liee", "type_question_display", "est_correcte_display", "ordre"]
    list_filter = ["est_correcte", "question__type_question"]
    search_fields = ["texte", "question__enonce_texte"]
    list_editable = ["ordre"]

    fieldsets = ((None, {"fields": ("question", "texte", "est_correcte", "ordre")}),)

    def texte_court(self, obj):
        return obj.texte[:100] + "..." if len(obj.texte) > 100 else obj.texte

    texte_court.short_description = "Texte"

    def question_liee(self, obj):
        return obj.question.enonce_texte[:50] + "..." if obj.question.enonce_texte else "-"

    question_liee.short_description = "Question"
    
    def type_question_display(self, obj):
        """Afficher le type de la question"""
        return obj.question.get_type_question_display()
    
    type_question_display.short_description = "Type question"

    def est_correcte_display(self, obj):
        if obj.est_correcte:
            return format_html('<span style="color:white;background:green;padding:3px 8px;border-radius:3px;">✓ Correcte</span>')
        return format_html('<span style="color:white;background:red;padding:3px 8px;border-radius:3px;">✗ Incorrecte</span>')

    est_correcte_display.short_description = "Statut"
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filtrer pour n'afficher que les questions QCM"""
        if db_field.name == "question":
            kwargs["queryset"] = Question.objects.filter(
                type_question__in=["choix_unique", "choix_multiple"]
            )
            kwargs["help_text"] = "⚠️ Seules les questions à choix (QCM) peuvent avoir des réponses prédéfinies."
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ============================================================================
# ADMIN ÉVALUATIONS
# ============================================================================

@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ["id","titre", "cours", "enseignant", "type_evaluation", "bareme", "statut_publication", "nombre_questions_display", "nombre_passages_display", "date_creation"]
    list_filter = ["type_evaluation", "est_publiee", "cours", "enseignant", "date_creation"]
    search_fields = ["titre", "consigne_texte", "cours__titre"]
    readonly_fields = ["date_creation", "date_modification", "nombre_questions"]

    fieldsets = (
        ("Informations générales", {"fields": ("cours", "enseignant", "titre", "type_evaluation")}),
        ("Configuration", {"fields": ("bareme", "duree_minutes", "est_publiee")}),
        ("Contenu (pour évaluation simple)", {
            "fields": ("consigne_texte", "fichier_sujet"), 
            "classes": ("collapse",), 
            "description": 'Utilisé uniquement si type = "simple"'
        }),
        ("Période de disponibilité", {"fields": ("date_debut", "date_fin"), "classes": ("collapse",)}),
        ("Métadonnées", {"fields": ("date_creation", "date_modification", "nombre_questions"), "classes": ("collapse",)}),
    )

    inlines = [QuestionInlineEvaluation]
    actions = ["publier_evaluations", "depublier_evaluations"]

    def statut_publication(self, obj):
        if obj.est_publiee:
            return format_html('<span style="color:white;background:green;padding:3px 10px;border-radius:3px;">✓ Publiée</span>')
        return format_html('<span style="color:white;background:orange;padding:3px 10px;border-radius:3px;">⚠ Brouillon</span>')

    statut_publication.short_description = "Statut"

    def nombre_questions_display(self, obj):
        if obj.type_evaluation == "structuree":
            return format_html('<span style="background:#2196F3;color:white;padding:3px 10px;border-radius:3px;">{} questions</span>', obj.nombre_questions)
        return format_html('<span style="color:gray;">N/A (simple)</span>')

    nombre_questions_display.short_description = "Questions"

    def nombre_passages_display(self, obj):
        count = obj.passages.count()
        corriges = obj.passages.filter(statut="corrige").count()
        en_attente = obj.passages.filter(statut="soumis").count()

        return format_html(
            "<div style='font-size:12px;'>Total: <b>{}</b><br><span style='color:green;'>Corrigés: {}</span><br><span style='color:orange;'>En attente: {}</span></div>",
            count, corriges, en_attente
        )

    nombre_passages_display.short_description = "Passages"

    def publier_evaluations(self, request, queryset):
        updated = queryset.update(est_publiee=True)
        self.message_user(request, f"{updated} évaluation(s) publiée(s).")

    publier_evaluations.short_description = "Publier les évaluations sélectionnées"

    def depublier_evaluations(self, request, queryset):
        updated = queryset.update(est_publiee=False)
        self.message_user(request, f"{updated} évaluation(s) dépubliée(s).")

    depublier_evaluations.short_description = "Dépublier les évaluations sélectionnées"


# ============================================================================
# ADMIN PASSAGES D'ÉVALUATIONS
# ============================================================================

@admin.register(PassageEvaluation)
class PassageEvaluationAdmin(admin.ModelAdmin):
    list_display = ["id", "apprenant", "evaluation", "statut_display", "note_display", "pourcentage_display", "date_soumission", "actions_display"]
    list_filter = ["statut", "evaluation", "evaluation__cours", "date_debut", "date_soumission"]
    search_fields = ["apprenant__email", "apprenant__nom", "apprenant__prenom", "evaluation__titre"]
    readonly_fields = ["date_debut", "date_soumission", "date_correction", "est_corrige", "necessite_correction"]

    fieldsets = (
        ("Informations", {"fields": ("apprenant", "evaluation", "statut")}),
        ("Réponse (pour évaluation simple)", {"fields": ("reponse_texte", "fichier_reponse"), "classes": ("collapse",)}),
        ("Correction", {"fields": ("note", "commentaire_enseignant")}),
        ("Dates", {"fields": ("date_debut", "date_soumission", "date_correction"), "classes": ("collapse",)}),
        ("Calculs", {"fields": ("est_corrige", "necessite_correction"), "classes": ("collapse",)}),
    )

    inlines = [ReponseQuestionInline]
    actions = ["marquer_comme_corrige"]

    def statut_display(self, obj):
        colors = {"en_cours": "gray", "soumis": "orange", "corrige": "green"}
        return format_html('<span style="color:white;background:{};padding:3px 10px;border-radius:3px;">{}</span>', colors.get(obj.statut, "gray"), obj.get_statut_display())

    statut_display.short_description = "Statut"

    def note_display(self, obj):
        if obj.note is None:
            return format_html('<span style="color:gray;">Non corrigé</span>')
        note = float(obj.note or 0)
        bareme = float(obj.evaluation.bareme or 0)
        color = "green" if bareme and note >= bareme / 2 else "red"
        return format_html('<span style="color:{};font-weight:bold;font-size:14px;">{} / {}</span>', color, f"{note:.1f}", f"{bareme:.1f}")

    note_display.short_description = "Note"

    def pourcentage_display(self, obj):
        pct = obj.pourcentage()
        if pct is None:
            return "-"
        pct = float(pct)
        color = "green" if pct >= 50 else "red"
        pct_formatted = f"{pct:.1f}"
        return format_html('<span style="color:{};font-weight:bold;">{}%</span>', color, pct_formatted)

    pourcentage_display.short_description = "%"

    def actions_display(self, obj):
        if obj.statut == "soumis" and obj.necessite_correction:
            return format_html('<a class="button" href="{}">Corriger</a>', reverse("admin:evaluations_passageevaluation_change", args=[obj.pk]))
        return "-"

    actions_display.short_description = "Actions"

    def marquer_comme_corrige(self, request, queryset):
        count = 0
        for passage in queryset:
            if passage.statut == "soumis":
                total = sum(float(r.points_obtenus or 0) for r in passage.reponses_questions.all())
                passage.note = total
                passage.statut = "corrige"
                passage.save()
                count += 1

        if count > 0:
            self.message_user(request, f"{count} passage(s) marqué(s) comme corrigé(s).", level="SUCCESS")
        else:
            self.message_user(request, "Aucun passage à corriger.", level="WARNING")

    marquer_comme_corrige.short_description = "Marquer comme corrigé (calcul auto)"


# ============================================================================
# ADMIN RÉPONSES AUX QUESTIONS
# ============================================================================

@admin.register(ReponseQuestion)
class ReponseQuestionAdmin(admin.ModelAdmin):
    list_display = ["id", "apprenant_display", "question_display", "statut_display", "points_display", "date_reponse"]
    list_filter = ["statut", "question__type_question", "passage_evaluation__evaluation", "date_reponse"]
    search_fields = ["passage_evaluation__apprenant__email", "passage_evaluation__apprenant__nom", "question__enonce_texte"]
    readonly_fields = ["passage_evaluation", "question", "date_reponse", "date_correction", "pourcentage_reussite"]

    fieldsets = (
        ("Informations", {"fields": ("passage_evaluation", "question", "statut")}),
        ("Réponse de l'apprenant", {"fields": ("choix_selectionnes", "reponse_texte", "fichier_reponse")}),
        ("Correction", {"fields": ("points_obtenus", "commentaire_correcteur")}),
        ("Dates et statistiques", {"fields": ("date_reponse", "date_correction", "pourcentage_reussite"), "classes": ("collapse",)}),
    )

    filter_horizontal = ["choix_selectionnes"]

    def apprenant_display(self, obj):
        a = obj.passage_evaluation.apprenant
        return f"{a.prenom} {a.nom}"

    apprenant_display.short_description = "Apprenant"

    def question_display(self, obj):
        return obj.question.enonce_texte[:60] + "..." if len(obj.question.enonce_texte) > 60 else obj.question.enonce_texte

    question_display.short_description = "Question"

    def statut_display(self, obj):
        colors = {"non_repondu": "gray", "repondu": "orange", "corrige": "green"}
        return format_html('<span style="color:white;background:{};padding:3px 10px;border-radius:3px;">{}</span>', colors.get(obj.statut, "gray"), obj.get_statut_display())

    statut_display.short_description = "Statut"

    def points_display(self, obj):
        pts = float(obj.points_obtenus or 0)
        max_pts = float(obj.question.points or 0)
        color = "green" if max_pts and pts >= max_pts / 2 else "red"
        return format_html('<span style="color:{};font-weight:bold;">{} / {}</span>', color, f"{pts:.1f}", f"{max_pts:.1f}")

    points_display.short_description = "Points"


# ============================================================================
# ADMIN PASSAGES DE QUIZ
# ============================================================================

@admin.register(PassageQuiz)
class PassageQuizAdmin(admin.ModelAdmin):
    list_display = ["id", "apprenant", "quiz", "score_display", "termine", "date_passage"]
    list_filter = ["termine", "quiz", "date_passage"]
    search_fields = ["apprenant__email", "apprenant__nom", "apprenant__prenom", "quiz__titre"]
    readonly_fields = ["date_passage", "score"]

    fieldsets = (
        ("Informations", {"fields": ("apprenant", "quiz")}),
        ("Résultats", {"fields": ("score", "termine", "date_passage")}),
    )

    inlines = [ReponseQuizInline]

    def score_display(self, obj):
        score = float(getattr(obj, "score", 0) or 0)
        agg = obj.quiz.questions.aggregate(total=Sum("points")) if obj.quiz_id else {"total": 0}
        bareme = float(agg.get("total") or 0)
        pourcentage = (score / bareme * 100.0) if bareme > 0 else 0.0

        color = "green" if pourcentage >= 80 else "orange" if pourcentage >= 50 else "red"

        if bareme > 0:
            return format_html('<span style="color:{};font-weight:bold;">{} / {} ({}%)</span>', color, f"{score:.1f}", f"{bareme:.1f}", f"{pourcentage:.0f}")

        return format_html('<span style="color:{};font-weight:bold;">{} pts</span>', color, f"{score:.1f}")

    score_display.short_description = "Score"


# ============================================================================
# ADMIN RÉPONSES DE QUIZ
# ============================================================================

@admin.register(ReponseQuiz)
class ReponseQuizAdmin(admin.ModelAdmin):
    list_display = ["id", "apprenant_display", "quiz_display", "question_display", "points_display", "date_reponse"]
    list_filter = ["passage_quiz__quiz", "date_reponse"]
    search_fields = ["passage_quiz__apprenant__email", "passage_quiz__apprenant__nom", "question__enonce_texte"]
    readonly_fields = ["passage_quiz", "question", "points_obtenus", "date_reponse"]

    fieldsets = (
        ("Informations", {"fields": ("passage_quiz", "question")}),
        ("Réponse", {"fields": ("choix_selectionnes", "points_obtenus")}),
        ("Date", {"fields": ("date_reponse",)}),
    )

    filter_horizontal = ["choix_selectionnes"]

    def apprenant_display(self, obj):
        a = obj.passage_quiz.apprenant
        return f"{a.prenom} {a.nom}"

    apprenant_display.short_description = "Apprenant"

    def quiz_display(self, obj):
        return obj.passage_quiz.quiz.titre

    quiz_display.short_description = "Quiz"

    def question_display(self, obj):
        return obj.question.enonce_texte[:50] + "..." if len(obj.question.enonce_texte) > 50 else obj.question.enonce_texte

    question_display.short_description = "Question"

    def points_display(self, obj):
        pts = float(obj.points_obtenus or 0)
        max_pts = float(obj.question.points or 0)
        color = "green" if pts > 0 else "red"
        return format_html('<span style="color:{};font-weight:bold;">{} / {}</span>', color, f"{pts:.1f}", f"{max_pts:.1f}")

    points_display.short_description = "Points"


# ============================================================================
# PERSONNALISATION DU SITE ADMIN
# ============================================================================

admin.site.site_header = "Administration - Système d'Évaluation"
admin.site.site_title = "Admin Évaluations"
admin.site.index_title = "Gestion des Quiz et Évaluations"