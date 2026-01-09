# progress/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    ProgressionApprenant,
    ProgressionModule,
    ProgressionSequence,
    ProgressionQuiz,
    HistoriqueActivite,
    PlanAction,
    ObjectifPlanAction,
)


# ============================================================================
# INLINES
# ============================================================================

class ProgressionSequenceInline(admin.TabularInline):
    model = ProgressionSequence
    extra = 0
    fields = ['sequence', 'est_terminee', 'temps_passe_minutes', 'nombre_visites']
    readonly_fields = ['temps_passe_minutes', 'nombre_visites']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


class ProgressionModuleInline(admin.TabularInline):
    model = ProgressionModule
    extra = 0
    fields = ['module', 'est_termine', 'pourcentage_completion', 'temps_passe_minutes']
    readonly_fields = ['pourcentage_completion', 'temps_passe_minutes']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


class ObjectifPlanActionInline(admin.TabularInline):
    model = ObjectifPlanAction
    extra = 1
    fields = ['titre', 'description', 'est_complete', 'ordre']
    ordering = ['ordre']


# ============================================================================
# ADMIN PROGRESSION APPRENANT
# ============================================================================

@admin.register(ProgressionApprenant)
class ProgressionApprenantAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'apprenant_display',
        'cours_display',
        'statut_display',
        'pourcentage_display',
        'temps_total_display',
        'note_moyenne_display',
        'date_derniere_activite',
    ]
    list_filter = [
        'statut',
        'cours',
        'date_debut',
    ]
    search_fields = [
        'apprenant__nom',
        'apprenant__prenom',
        'apprenant__email',
        'cours__titre',
    ]
    readonly_fields = [
        'date_debut',
        'date_derniere_activite',
        'date_completion',
        'pourcentage_completion',
        'temps_total_minutes',
        'note_moyenne_evaluations',
        'taux_reussite_quiz',
        'temps_total_formate',
        'est_termine',
        'nombre_evaluations_reussies',
    ]
    
    fieldsets = (
        ('Informations', {
            'fields': ('apprenant', 'cours', 'statut')
        }),
        ('Position actuelle', {
            'fields': ('dernier_module', 'derniere_sequence')
        }),
        ('Métriques de progression', {
            'fields': (
                'pourcentage_completion',
                'temps_total_minutes',
                'temps_total_formate',
            )
        }),
        ('Performances', {
            'fields': (
                'note_moyenne_evaluations',
                'taux_reussite_quiz',
                'nombre_evaluations_reussies',
            )
        }),
        ('Dates', {
            'fields': ('date_debut', 'date_derniere_activite', 'date_completion'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ProgressionModuleInline]
    
    actions = ['recalculer_progressions']
    
    def apprenant_display(self, obj):
        return f"{obj.apprenant.prenom} {obj.apprenant.nom}"
    apprenant_display.short_description = "Apprenant"
    
    def cours_display(self, obj):
        return obj.cours.titre
    cours_display.short_description = "Cours"
    
    def statut_display(self, obj):
        colors = {
            'non_commence': 'gray',
            'en_cours': 'orange',
            'termine': 'green',
            'abandonne': 'red',
            'suspendu': 'blue',
        }
        return format_html(
            '<span style="color:white;background:{};padding:3px 10px;border-radius:3px;">{}</span>',
            colors.get(obj.statut, 'gray'),
            obj.get_statut_display()
        )
    statut_display.short_description = "Statut"
    
    def pourcentage_display(self, obj):
        """Affichage du pourcentage de progression"""
        color = 'green' if obj.pourcentage_completion >= 50 else 'orange'
        # ✅ Formatter AVANT d'utiliser dans format_html
        pourcentage_formatted = f"{obj.pourcentage_completion:.1f}"
        return format_html(
            '<span style="color:{};font-weight:bold;font-size:14px;">{}%</span>',
            color,
            pourcentage_formatted
        )
    pourcentage_display.short_description = "Progression"
    
    def temps_total_display(self, obj):
        return obj.temps_total_formate
    temps_total_display.short_description = "Temps total"
    
    def note_moyenne_display(self, obj):
        """Affichage de la note moyenne"""
        if obj.note_moyenne_evaluations is not None:
            note = float(obj.note_moyenne_evaluations)
            color = 'green' if note >= 10 else 'red'
            # ✅ Formatter AVANT d'utiliser dans format_html
            note_formatted = f"{note:.1f}"
            return format_html(
                '<span style="color:{};font-weight:bold;">{}/20</span>',
                color,
                note_formatted
            )
        return '-'
    note_moyenne_display.short_description = "Note moyenne"
    
    def recalculer_progressions(self, request, queryset):
        count = 0
        for progression in queryset:
            progression.calculer_progression()
            progression.calculer_note_moyenne_evaluations()
            progression.calculer_taux_reussite_quiz()
            count += 1
        
        self.message_user(
            request,
            f'{count} progression(s) recalculée(s).',
            level='SUCCESS'
        )
    recalculer_progressions.short_description = "Recalculer les progressions"


# ============================================================================
# ADMIN PROGRESSION MODULE
# ============================================================================

@admin.register(ProgressionModule)
class ProgressionModuleAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'apprenant_display',
        'module_display',
        'est_termine',
        'pourcentage_display',
        'temps_passe_minutes',
    ]
    list_filter = ['est_termine', 'module']
    search_fields = [
        'progression_apprenant__apprenant__nom',
        'progression_apprenant__apprenant__prenom',
        'module__titre',
    ]
    readonly_fields = ['date_debut', 'date_fin', 'pourcentage_completion']
    
    fieldsets = (
        ('Informations', {
            'fields': ('progression_apprenant', 'module')
        }),
        ('Progression', {
            'fields': ('est_termine', 'pourcentage_completion', 'temps_passe_minutes')
        }),
        ('Dates', {
            'fields': ('date_debut', 'date_fin'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ProgressionSequenceInline]
    
    actions = ['recalculer_progressions_modules']
    
    def apprenant_display(self, obj):
        apprenant = obj.progression_apprenant.apprenant
        return f"{apprenant.prenom} {apprenant.nom}"
    apprenant_display.short_description = "Apprenant"
    
    def module_display(self, obj):
        return obj.module.titre
    module_display.short_description = "Module"
    
    def pourcentage_display(self, obj):
        # ✅ Formatter AVANT
        pourcentage_formatted = f"{obj.pourcentage_completion:.1f}"
        return format_html(
            '<span style="font-weight:bold;">{}%</span>',
            pourcentage_formatted
        )
    pourcentage_display.short_description = "Progression"
    
    def recalculer_progressions_modules(self, request, queryset):
        count = 0
        for progression_module in queryset:
            progression_module.calculer_progression()
            count += 1
        
        self.message_user(
            request,
            f'{count} progression(s) de module recalculée(s).',
            level='SUCCESS'
        )
    recalculer_progressions_modules.short_description = "Recalculer les progressions"


# ============================================================================
# ADMIN PROGRESSION SEQUENCE
# ============================================================================

@admin.register(ProgressionSequence)
class ProgressionSequenceAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'apprenant_display',
        'sequence_display',
        'est_terminee',
        'pourcentage_display',
        'temps_passe_minutes',
        'nombre_visites',
    ]
    list_filter = ['est_terminee']
    search_fields = [
        'progression_module__progression_apprenant__apprenant__nom',
        'progression_module__progression_apprenant__apprenant__prenom',
        'sequence__titre',
    ]
    readonly_fields = ['date_debut', 'date_fin', 'pourcentage_completion']
    
    fieldsets = (
        ('Informations', {
            'fields': ('progression_module', 'sequence')
        }),
        ('Progression', {
            'fields': ('est_terminee', 'pourcentage_completion', 'temps_passe_minutes', 'nombre_visites')
        }),
        ('Dates', {
            'fields': ('date_debut', 'date_fin'),
            'classes': ('collapse',)
        }),
    )
    
    def apprenant_display(self, obj):
        apprenant = obj.progression_module.progression_apprenant.apprenant
        return f"{apprenant.prenom} {apprenant.nom}"
    apprenant_display.short_description = "Apprenant"
    
    def sequence_display(self, obj):
        return obj.sequence.titre
    sequence_display.short_description = "Séquence"
    
    def pourcentage_display(self, obj):
        # ✅ Formatter AVANT
        pourcentage_formatted = f"{obj.pourcentage_completion:.1f}"
        return format_html(
            '<span style="font-weight:bold;">{}%</span>',
            pourcentage_formatted
        )
    pourcentage_display.short_description = "%"


# ============================================================================
# ADMIN PROGRESSION QUIZ
# ============================================================================

@admin.register(ProgressionQuiz)
class ProgressionQuizAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'apprenant_display',
        'quiz_display',
        'score_display',
        'pourcentage_display',
        'numero_tentative',
        'date_passage',
    ]
    list_filter = ['date_passage']
    search_fields = [
        'progression_apprenant__apprenant__nom',
        'progression_apprenant__apprenant__prenom',
        'passage_quiz__quiz__titre',
    ]
    readonly_fields = [
        'date_passage',
        'score',
        'pourcentage_reussite',
        'numero_tentative',
    ]
    
    fieldsets = (
        ('Informations', {
            'fields': ('progression_apprenant', 'passage_quiz')
        }),
        ('Résultats', {
            'fields': ('score', 'pourcentage_reussite', 'temps_passe_minutes', 'numero_tentative')
        }),
        ('Dates', {
            'fields': ('date_passage',),
        }),
    )
    
    def apprenant_display(self, obj):
        apprenant = obj.progression_apprenant.apprenant
        return f"{apprenant.prenom} {apprenant.nom}"
    apprenant_display.short_description = "Apprenant"
    
    def quiz_display(self, obj):
        return obj.passage_quiz.quiz.titre
    quiz_display.short_description = "Quiz"
    
    def score_display(self, obj):
        score = float(obj.score)
        # ✅ Formatter AVANT
        score_formatted = f"{score:.1f}"
        return format_html(
            '<span style="font-weight:bold;">{} pts</span>',
            score_formatted
        )
    score_display.short_description = "Score"
    
    def pourcentage_display(self, obj):
        pourcentage = float(obj.pourcentage_reussite)
        color = 'green' if pourcentage >= 50 else 'red'
        # ✅ Formatter AVANT
        pourcentage_formatted = f"{pourcentage:.1f}"
        return format_html(
            '<span style="color:{};font-weight:bold;">{}%</span>',
            color,
            pourcentage_formatted
        )
    pourcentage_display.short_description = "Réussite"


# ============================================================================
# ADMIN HISTORIQUE ACTIVITE
# ============================================================================

@admin.register(HistoriqueActivite)
class HistoriqueActiviteAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'apprenant_display',
        'type_activite_display',
        'objet_info',
        'duree_minutes',
        'date_activite',
    ]
    list_filter = ['type_activite', 'date_activite']
    search_fields = [
        'apprenant__nom',
        'apprenant__prenom',
        'apprenant__email',
        'description',
    ]
    readonly_fields = ['date_activite']
    
    fieldsets = (
        ('Informations', {
            'fields': ('apprenant', 'type_activite', 'description')
        }),
        ('Objet concerné', {
            'fields': ('objet_type', 'objet_id')
        }),
        ('Détails', {
            'fields': ('duree_minutes', 'metadata', 'date_activite')
        }),
    )
    
    date_hierarchy = 'date_activite'
    
    def apprenant_display(self, obj):
        return f"{obj.apprenant.prenom} {obj.apprenant.nom}"
    apprenant_display.short_description = "Apprenant"
    
    def type_activite_display(self, obj):
        return obj.get_type_activite_display()
    type_activite_display.short_description = "Type d'activité"
    
    def objet_info(self, obj):
        if obj.objet_type and obj.objet_id:
            return f"{obj.objet_type} #{obj.objet_id}"
        return '-'
    objet_info.short_description = "Objet"


# ============================================================================
# ADMIN PLAN D'ACTION
# ============================================================================

@admin.register(PlanAction)
class PlanActionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'titre',
        'apprenant_display',
        'cours_display',
        'statut_display',
        'priorite_display',
        'pourcentage_display',
        'echeance_display',
    ]
    list_filter = ['statut', 'priorite', 'date_creation', 'date_echeance']
    search_fields = [
        'titre',
        'description',
        'apprenant__nom',
        'apprenant__prenom',
        'cours__titre',
    ]
    readonly_fields = [
        'date_creation',
        'date_completion',
        'pourcentage_completion',
        'est_en_retard',
    ]
    
    fieldsets = (
        ('Informations', {
            'fields': ('apprenant', 'cours', 'titre', 'description')
        }),
        ('Configuration', {
            'fields': ('priorite', 'statut', 'date_echeance')
        }),
        ('Suivi', {
            'fields': ('cree_par', 'pourcentage_completion', 'est_en_retard')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_completion'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ObjectifPlanActionInline]
    
    actions = ['marquer_plans_termines']
    
    def apprenant_display(self, obj):
        return f"{obj.apprenant.prenom} {obj.apprenant.nom}"
    apprenant_display.short_description = "Apprenant"
    
    def cours_display(self, obj):
        return obj.cours.titre if obj.cours else '-'
    cours_display.short_description = "Cours"
    
    def statut_display(self, obj):
        colors = {
            'a_faire': 'gray',
            'en_cours': 'orange',
            'termine': 'green',
            'annule': 'red',
        }
        return format_html(
            '<span style="color:white;background:{};padding:3px 10px;border-radius:3px;">{}</span>',
            colors.get(obj.statut, 'gray'),
            obj.get_statut_display()
        )
    statut_display.short_description = "Statut"
    
    def priorite_display(self, obj):
        colors = {
            'basse': 'blue',
            'moyenne': 'orange',
            'haute': 'red',
            'urgente': 'darkred',
        }
        return format_html(
            '<span style="color:{};font-weight:bold;">{}</span>',
            colors.get(obj.priorite, 'gray'),
            obj.get_priorite_display()
        )
    priorite_display.short_description = "Priorité"
    
    def pourcentage_display(self, obj):
        pourcentage = obj.pourcentage_completion
        # ✅ Formatter AVANT
        pourcentage_formatted = f"{pourcentage:.0f}"
        color = 'green' if pourcentage >= 50 else 'orange'
        return format_html(
            '<span style="color:{};font-weight:bold;">{}%</span>',
            color,
            pourcentage_formatted
        )
    pourcentage_display.short_description = "Progression"
    
    def echeance_display(self, obj):
        if obj.date_echeance:
            if obj.est_en_retard:
                return format_html(
                    '<span style="color:red;font-weight:bold;">⚠️ {}</span>',
                    obj.date_echeance
                )
            return obj.date_echeance
        return '-'
    echeance_display.short_description = "Échéance"
    
    def marquer_plans_termines(self, request, queryset):
        count = 0
        for plan in queryset:
            if plan.statut != 'termine':
                plan.marquer_comme_termine()
                count += 1
        
        self.message_user(
            request,
            f'{count} plan(s) d\'action marqué(s) comme terminé(s).',
            level='SUCCESS'
        )
    marquer_plans_termines.short_description = "Marquer comme terminés"


# ============================================================================
# ADMIN OBJECTIF PLAN D'ACTION
# ============================================================================

@admin.register(ObjectifPlanAction)
class ObjectifPlanActionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'plan_display',
        'titre',
        'est_complete_display',
        'ordre',
        'date_completion',
    ]
    list_filter = ['est_complete', 'plan_action']
    search_fields = [
        'titre',
        'description',
        'plan_action__titre',
    ]
    readonly_fields = ['date_completion']
    list_editable = ['ordre']
    
    fieldsets = (
        ('Informations', {
            'fields': ('plan_action', 'titre', 'description')
        }),
        ('Statut', {
            'fields': ('est_complete', 'date_completion', 'ordre')
        }),
    )
    
    actions = ['marquer_objectifs_completes', 'marquer_objectifs_incompletes']
    
    def plan_display(self, obj):
        return obj.plan_action.titre
    plan_display.short_description = "Plan d'action"
    
    def est_complete_display(self, obj):
        if obj.est_complete:
            return format_html(
                '<span style="color:white;background:green;padding:3px 10px;border-radius:3px;">✓ Complété</span>'
            )
        return format_html(
            '<span style="color:white;background:gray;padding:3px 10px;border-radius:3px;">✗ En attente</span>'
        )
    est_complete_display.short_description = "Statut"
    
    def marquer_objectifs_completes(self, request, queryset):
        count = 0
        for objectif in queryset:
            if not objectif.est_complete:
                objectif.marquer_comme_complete()
                count += 1
        
        self.message_user(
            request,
            f'{count} objectif(s) marqué(s) comme complété(s).',
            level='SUCCESS'
        )
    marquer_objectifs_completes.short_description = "Marquer comme complétés"
    
    def marquer_objectifs_incompletes(self, request, queryset):
        count = 0
        for objectif in queryset:
            if objectif.est_complete:
                objectif.marquer_comme_incomplete()
                count += 1
        
        self.message_user(
            request,
            f'{count} objectif(s) marqué(s) comme incomplet(s).',
            level='WARNING'
        )
    marquer_objectifs_incompletes.short_description = "Marquer comme incomplets"


# ============================================================================
# PERSONNALISATION ADMIN
# ============================================================================

admin.site.site_header = "Administration - Progression des apprenants"
admin.site.site_title = "Admin Progression"
admin.site.index_title = "Gestion de la progression"