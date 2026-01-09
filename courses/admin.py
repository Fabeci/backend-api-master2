# courses/admin.py
from django.contrib import admin
from django.db.models import Count
from .models import Cours, Module, Sequence, Session, InscriptionCours, Participation, Suivi

@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "titre",
        "matiere",
        "groupe",
        "enseignant",
        "volume_horaire",
        "statut",
        "date_debut",
        "date_fin",
        "total_heures_realisees",
        "taux_execution",
    )
    list_filter = ("titre","statut", "matiere", "groupe", "enseignant")
    search_fields = ("titre","matiere__nom", "groupe__nom", "enseignant__nom", "enseignant__prenom")
    autocomplete_fields = ("groupe", "enseignant", "matiere")
    ordering = ("-id",)

    @admin.display(description="Heures réalisées")
    def total_heures_realisees(self, obj: Cours):
        return obj.total_heures_realisees

    @admin.display(description="Taux exécution (%)")
    def taux_execution(self, obj: Cours):
        return obj.taux_execution


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("id", "titre", "cours")
    list_filter = ("cours",)
    search_fields = ("titre", "cours__matiere__nom", "cours__groupe__nom")
    autocomplete_fields = ("cours",)


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ("id", "titre", "module", "cours")
    list_filter = ("module",)
    search_fields = ("titre", "module__titre", "module__cours__matiere__nom")
    autocomplete_fields = ("module",)

    @admin.display(description="Cours")
    def cours(self, obj: Sequence):
        return obj.module.cours


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "titre",
        "cours",
        "formateur",
        "participation_mode",
        "date_debut",
        "date_fin",
        "duree_minutes",
    )
    list_filter = ("participation_mode", "cours", "formateur")
    search_fields = ("titre", "cours__matiere__nom", "cours__groupe__nom", "formateur__nom", "formateur__prenom")
    autocomplete_fields = ("cours", "formateur")
    ordering = ("-date_debut",)

    @admin.display(description="Durée (min)")
    def duree_minutes(self, obj: Session):
        return obj.duree_minutes


@admin.register(InscriptionCours)
class InscriptionCoursAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "cours", "date_inscription", "statut")
    list_filter = ("statut", "date_inscription", "cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "apprenant__email", "cours__matiere__nom", "cours__groupe__nom")
    autocomplete_fields = ("apprenant", "cours")
    ordering = ("-date_inscription",)


@admin.register(Suivi)
class SuiviAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "cours", "progression", "note", "date_debut")
    list_filter = ("date_debut", "cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "apprenant__email", "cours__matiere__nom")
    autocomplete_fields = ("apprenant", "cours")
    ordering = ("-date_debut",)


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "apprenant",
        "source",
        "statut",
        "created_at",
        "completed_at",
    )
    list_filter = ("source", "statut", "created_at", "session")
    search_fields = (
        "apprenant__nom",
        "apprenant__prenom",
        "apprenant__email",
        "session__titre",
        "session__cours__matiere__nom",
    )
    autocomplete_fields = ("session", "apprenant")
    ordering = ("-created_at",)