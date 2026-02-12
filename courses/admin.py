# courses/admin.py

from django.contrib import admin
from .models import (
    Cours,
    Module,
    Sequence,
    SequenceContent,
    BlocContenu,
    RessourceSequence,
    InscriptionCours,
    Suivi,
    Session,
    Participation,
    BlocProgress,
    SequenceProgress,
    ModuleProgress,
    CoursProgress,
)


# ============================================================================
# INLINE ADMINS
# ============================================================================

class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ('titre', 'description')
    readonly_fields = ('institution', 'annee_scolaire')


class SequenceInline(admin.TabularInline):
    model = Sequence
    extra = 0
    fields = ('titre',)
    readonly_fields = ('institution', 'annee_scolaire')


class BlocContenuInline(admin.StackedInline):
    model = BlocContenu
    extra = 0
    fields = ('titre', 'type_bloc', 'ordre', 'est_visible', 'est_obligatoire')


class RessourceSequenceInline(admin.TabularInline):
    model = RessourceSequence
    extra = 0
    fields = ('titre', 'fichier', 'type_ressource', 'ordre', 'est_telechargeable')


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0
    fields = ('titre', 'date_debut', 'date_fin', 'formateur', 'participation_mode')
    readonly_fields = ('institution', 'annee_scolaire')


# ============================================================================
# MODEL ADMINS
# ============================================================================

@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titre', 'matiere', 'groupe', 'enseignant',
        'institution', 'annee_scolaire', 'statut', 'volume_horaire'
    )
    list_filter = ('statut', 'institution', 'annee_scolaire', 'matiere')
    search_fields = (
        'titre', 'matiere__nom', 'groupe__nom',
        'enseignant__nom', 'enseignant__prenom'
    )
    autocomplete_fields = ['groupe', 'matiere', 'enseignant', 'institution', 'annee_scolaire']
    inlines = [ModuleInline, SessionInline]
    date_hierarchy = 'date_debut'
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('titre', 'matiere', 'groupe', 'enseignant', 'statut')
        }),
        ('Contexte', {
            'fields': ('institution', 'annee_scolaire'),
            'description': 'Institution et année scolaire de rattachement'
        }),
        ('Planification', {
            'fields': ('date_debut', 'date_fin', 'volume_horaire')
        }),
    )


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titre', 'cours', 'institution', 'annee_scolaire'
    )
    list_filter = ('institution', 'annee_scolaire', 'cours__matiere')
    search_fields = ('titre', 'cours__titre', 'description')
    autocomplete_fields = ['cours']
    inlines = [SequenceInline]
    readonly_fields = ('institution', 'annee_scolaire')
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('titre', 'description', 'cours')
        }),
        ('Contexte (hérité du cours)', {
            'fields': ('institution', 'annee_scolaire'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titre', 'module', 'institution', 'annee_scolaire'
    )
    list_filter = ('institution', 'annee_scolaire', 'module__cours__matiere')
    search_fields = ('titre', 'module__titre', 'module__cours__titre')
    autocomplete_fields = ['module']
    inlines = [BlocContenuInline, RessourceSequenceInline]
    readonly_fields = ('institution', 'annee_scolaire')
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('titre', 'module')
        }),
        ('Contexte (hérité du module)', {
            'fields': ('institution', 'annee_scolaire'),
            'classes': ('collapse',),
        }),
    )


@admin.register(SequenceContent)
class SequenceContentAdmin(admin.ModelAdmin):
    list_display = ('id', 'sequence', 'est_publie', 'duree_estimee_minutes')
    list_filter = ('est_publie',)
    search_fields = ('sequence__titre', 'objectifs')
    autocomplete_fields = ['sequence']
    
    fieldsets = (
        ('Séquence', {
            'fields': ('sequence',)
        }),
        ('Contenu', {
            'fields': ('contenu_texte', 'contenu_html', 'video_url', 'lien_externe')
        }),
        ('Métadonnées', {
            'fields': ('objectifs', 'duree_estimee_minutes', 'est_publie')
        }),
    )


@admin.register(BlocContenu)
class BlocContenuAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titre', 'type_bloc', 'sequence', 'ordre',
        'est_visible', 'est_obligatoire', 'duree_estimee_minutes'
    )
    list_filter = ('type_bloc', 'est_visible', 'est_obligatoire', 'sequence__module__cours__institution')
    search_fields = ('titre', 'sequence__titre', 'objectifs')
    autocomplete_fields = ['sequence']
    list_editable = ('ordre', 'est_visible')
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('sequence', 'titre', 'type_bloc', 'ordre')
        }),
        ('Contenu textuel', {
            'fields': ('contenu_texte', 'contenu_html', 'contenu_markdown'),
            'classes': ('collapse',),
        }),
        ('Médias', {
            'fields': ('video_url', 'audio_url', 'image', 'fichier', 'lien_externe'),
            'classes': ('collapse',),
        }),
        ('Code', {
            'fields': ('code_source', 'langage_code'),
            'classes': ('collapse',),
        }),
        ('Paramètres pédagogiques', {
            'fields': ('objectifs', 'duree_estimee_minutes', 'est_obligatoire', 'est_visible')
        }),
    )


@admin.register(RessourceSequence)
class RessourceSequenceAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titre', 'sequence', 'type_ressource',
        'taille_lisible', 'est_telechargeable', 'nombre_telechargements'
    )
    list_filter = ('type_ressource', 'est_telechargeable', 'sequence__module__cours__institution')
    search_fields = ('titre', 'description', 'sequence__titre')
    autocomplete_fields = ['sequence', 'ajoute_par']
    readonly_fields = ('taille_fichier', 'nombre_telechargements', 'date_ajout', 'date_modification')
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('sequence', 'titre', 'description', 'type_ressource')
        }),
        ('Fichier', {
            'fields': ('fichier', 'taille_fichier')
        }),
        ('Paramètres', {
            'fields': ('est_telechargeable', 'ordre', 'ajoute_par')
        }),
        ('Statistiques', {
            'fields': ('nombre_telechargements', 'date_ajout', 'date_modification'),
            'classes': ('collapse',),
        }),
    )


@admin.register(InscriptionCours)
class InscriptionCoursAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'apprenant', 'cours', 'statut',
        'institution', 'annee_scolaire', 'date_inscription'
    )
    list_filter = ('statut', 'institution', 'annee_scolaire', 'cours__matiere')
    search_fields = (
        'apprenant__nom', 'apprenant__prenom', 'apprenant__email',
        'cours__titre', 'cours__matiere__nom'
    )
    autocomplete_fields = ['apprenant', 'cours']
    readonly_fields = ('institution', 'annee_scolaire', 'date_inscription')

    # ✅ TEMPORAIRE: désactiver car SQLite plante si une date est invalide
    # date_hierarchy = 'date_inscription'


@admin.register(Suivi)
class SuiviAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'apprenant', 'cours', 'progression',
        'note', 'institution', 'annee_scolaire'
    )
    list_filter = ('institution', 'annee_scolaire', 'cours__matiere')
    search_fields = (
        'apprenant__nom', 'apprenant__prenom',
        'cours__titre', 'commentaires'
    )
    autocomplete_fields = ['apprenant', 'cours']
    readonly_fields = ('institution', 'annee_scolaire', 'date_debut')
    
    fieldsets = (
        ('Suivi', {
            'fields': ('apprenant', 'cours', 'progression', 'note', 'commentaires')
        }),
        ('Contexte (hérité du cours)', {
            'fields': ('institution', 'annee_scolaire'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titre', 'cours', 'formateur', 'date_debut',
        'date_fin', 'participation_mode', 'institution', 'annee_scolaire'
    )
    list_filter = ('participation_mode', 'institution', 'annee_scolaire', 'cours__matiere')
    search_fields = (
        'titre', 'cours__titre', 'formateur__nom', 'formateur__prenom'
    )
    autocomplete_fields = ['cours', 'formateur']
    readonly_fields = ('institution', 'annee_scolaire', 'duree_minutes')
    date_hierarchy = 'date_debut'
    
    fieldsets = (
        ('Session', {
            'fields': ('titre', 'cours', 'formateur', 'participation_mode')
        }),
        ('Dates', {
            'fields': ('date_debut', 'date_fin', 'duree_minutes')
        }),
        ('Contexte (hérité du cours)', {
            'fields': ('institution', 'annee_scolaire'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'session', 'apprenant', 'statut', 'source',
        'institution', 'annee_scolaire', 'created_at'
    )
    list_filter = ('statut', 'source', 'institution', 'annee_scolaire')
    search_fields = (
        'session__titre', 'apprenant__nom', 'apprenant__prenom'
    )
    autocomplete_fields = ['session', 'apprenant']
    readonly_fields = ('institution', 'annee_scolaire', 'created_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Participation', {
            'fields': ('session', 'apprenant', 'statut', 'source')
        }),
        ('Contexte (hérité de la session)', {
            'fields': ('institution', 'annee_scolaire'),
            'classes': ('collapse',),
        }),
        ('Dates', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',),
        }),
    )


# ============================================================================
# PROGRESSION ADMINS
# ============================================================================

@admin.register(BlocProgress)
class BlocProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'apprenant', 'bloc', 'est_termine', 'completed_at')
    list_filter = ('est_termine',)
    search_fields = ('apprenant__nom', 'apprenant__prenom', 'bloc__titre')
    autocomplete_fields = ['apprenant', 'bloc']
    readonly_fields = ('completed_at', 'updated_at')


@admin.register(SequenceProgress)
class SequenceProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'apprenant', 'sequence', 'est_termine', 'completed_at')
    list_filter = ('est_termine',)
    search_fields = ('apprenant__nom', 'apprenant__prenom', 'sequence__titre')
    autocomplete_fields = ['apprenant', 'sequence']
    readonly_fields = ('completed_at', 'updated_at')


@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'apprenant', 'module', 'est_termine', 'completed_at')
    list_filter = ('est_termine',)
    search_fields = ('apprenant__nom', 'apprenant__prenom', 'module__titre')
    autocomplete_fields = ['apprenant', 'module']
    readonly_fields = ('completed_at', 'updated_at')


@admin.register(CoursProgress)
class CoursProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'apprenant', 'cours', 'est_termine', 'completed_at')
    list_filter = ('est_termine',)
    search_fields = ('apprenant__nom', 'apprenant__prenom', 'cours__titre')
    autocomplete_fields = ['apprenant', 'cours']
    readonly_fields = ('completed_at', 'updated_at')