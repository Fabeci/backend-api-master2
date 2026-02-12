from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Count, Q

from .models import (
    Cours,
    Module,
    Sequence,
    SequenceContent,
    Session,
    InscriptionCours,
    Participation,
    Suivi,
    BlocContenu,
    RessourceSequence,

    # --- PROGRESSION
    BlocProgress,
    SequenceProgress,
    ModuleProgress,
    CoursProgress,
)


def model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def safe_count_related(obj, rel_name: str) -> int:
    """
    Compte proprement un related manager si présent.
    """
    if not hasattr(obj, rel_name):
        return 0
    try:
        return getattr(obj, rel_name).count()
    except Exception:
        return 0


# =============================================================================
# COURS
# =============================================================================
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

        "modules_count",
        "sessions_count",
        "inscriptions_count",

        # ✅ Progression
        "cours_termines_count",
        "taux_completion_cours",
    )
    list_filter = ("statut", "matiere", "groupe", "enseignant")
    search_fields = ("titre", "matiere__nom", "groupe__nom", "enseignant__nom", "enseignant__prenom")
    autocomplete_fields = ("groupe", "enseignant", "matiere")
    ordering = ("-id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # ⚠️ ces relations existent chez toi, mais on protège au cas où
        try:
            qs = qs.annotate(
                _modules_count=Count("modules", distinct=True),
                _sessions_count=Count("sessions", distinct=True),
                _inscriptions_count=Count("inscriptions", distinct=True),
            )
        except Exception:
            pass
        return qs

    @admin.display(description="Heures réalisées")
    def total_heures_realisees(self, obj: Cours):
        return getattr(obj, "total_heures_realisees", 0)

    @admin.display(description="Taux exécution (%)")
    def taux_execution(self, obj: Cours):
        return getattr(obj, "taux_execution", 0)

    @admin.display(description="Modules")
    def modules_count(self, obj: Cours):
        return getattr(obj, "_modules_count", safe_count_related(obj, "modules"))

    @admin.display(description="Sessions")
    def sessions_count(self, obj: Cours):
        return getattr(obj, "_sessions_count", safe_count_related(obj, "sessions"))

    @admin.display(description="Inscriptions")
    def inscriptions_count(self, obj: Cours):
        return getattr(obj, "_inscriptions_count", safe_count_related(obj, "inscriptions"))

    # ✅ Progression
    @admin.display(description="Cours terminés (apprenants)")
    def cours_termines_count(self, obj: Cours):
        return CoursProgress.objects.filter(cours=obj, est_termine=True).count()

    @admin.display(description="Complétion cours (%)")
    def taux_completion_cours(self, obj: Cours):
        inscrits = self.inscriptions_count(obj)
        if not inscrits:
            return 0
        termines = self.cours_termines_count(obj)
        return round((termines / inscrits) * 100, 1)


# =============================================================================
# MODULE
# =============================================================================
@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "titre",
        "cours",
        "sequences_count",

        # ✅ Progression
        "module_termines_count",
        "taux_completion_module",
    )
    list_filter = ("cours",)
    search_fields = ("titre", "cours__matiere__nom", "cours__groupe__nom")
    autocomplete_fields = ("cours",)
    ordering = ("-id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            qs = qs.annotate(_sequences_count=Count("sequences", distinct=True))
        except Exception:
            pass
        return qs

    @admin.display(description="Séquences")
    def sequences_count(self, obj: Module):
        return getattr(obj, "_sequences_count", safe_count_related(obj, "sequences"))

    # ✅ Progression
    @admin.display(description="Modules terminés (apprenants)")
    def module_termines_count(self, obj: Module):
        return ModuleProgress.objects.filter(module=obj, est_termine=True).count()

    @admin.display(description="Complétion module (%)")
    def taux_completion_module(self, obj: Module):
        inscrits = safe_count_related(obj.cours, "inscriptions") if obj.cours_id else 0
        if not inscrits:
            return 0
        termines = self.module_termines_count(obj)
        return round((termines / inscrits) * 100, 1)


# =============================================================================
# SEQUENCE
# =============================================================================
@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "titre",
        "module",
        "cours",
        "blocs_count",
        "ressources_count",
        "has_contenu",

        # ✅ Progression
        "sequence_termines_count",
        "taux_completion_sequence",
    )
    list_filter = ("module", "module__cours")
    search_fields = ("titre", "module__titre", "module__cours__matiere__nom", "module__cours__groupe__nom")
    autocomplete_fields = ("module",)
    ordering = ("-id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            qs = qs.select_related("module", "module__cours").annotate(
                _blocs_count=Count("blocs_contenu", distinct=True),
                _ressources_count=Count("ressources_sequences", distinct=True),
            )
        except Exception:
            qs = qs.select_related("module", "module__cours")
        return qs

    @admin.display(description="Cours")
    def cours(self, obj: Sequence):
        return obj.module.cours if obj.module_id else None

    @admin.display(description="Blocs")
    def blocs_count(self, obj: Sequence):
        return getattr(obj, "_blocs_count", safe_count_related(obj, "blocs_contenu"))

    @admin.display(description="Ressources")
    def ressources_count(self, obj: Sequence):
        return getattr(obj, "_ressources_count", safe_count_related(obj, "ressources_sequences"))

    @admin.display(description="Contenu (OneToOne)")
    def has_contenu(self, obj: Sequence):
        # ton modèle semble avoir un OneToOne : related_name="contenu"
        return hasattr(obj, "contenu")

    # ✅ Progression
    @admin.display(description="Séquences terminées (apprenants)")
    def sequence_termines_count(self, obj: Sequence):
        return SequenceProgress.objects.filter(sequence=obj, est_termine=True).count()

    @admin.display(description="Complétion séquence (%)")
    def taux_completion_sequence(self, obj: Sequence):
        cours = obj.module.cours if obj.module_id else None
        inscrits = safe_count_related(cours, "inscriptions") if cours else 0
        if not inscrits:
            return 0
        termines = self.sequence_termines_count(obj)
        return round((termines / inscrits) * 100, 1)


# =============================================================================
# SEQUENCE CONTENT
# =============================================================================
@admin.register(SequenceContent)
class SequenceContentAdmin(admin.ModelAdmin):
    list_display = ("sequence", "module", "cours", "date_creation", "date_modification", "est_publie")
    list_filter = ("est_publie", "sequence__module__cours", "sequence__module")
    search_fields = ("sequence__titre", "sequence__module__titre", "sequence__module__cours__titre")
    ordering = ("sequence__module__cours", "sequence__module", "sequence")

    readonly_fields = tuple(
        f for f in ("date_creation", "date_modification")
        if model_has_field(SequenceContent, f)
    )

    @admin.display(description="Module")
    def module(self, obj):
        return getattr(obj.sequence, "module", None)

    @admin.display(description="Cours")
    def cours(self, obj):
        seq = getattr(obj, "sequence", None)
        mod = getattr(seq, "module", None) if seq else None
        return getattr(mod, "cours", None) if mod else None


# =============================================================================
# BLOC CONTENU
# =============================================================================
@admin.register(BlocContenu)
class BlocContenuAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sequence",
        "module",
        "cours",
        "ordre",
        "titre",
        "type_bloc",
        "est_obligatoire",
        "est_visible",
        "duree_estimee_minutes",
        "date_creation",
        "date_modification",

        # ✅ Progression
        "progressions_done_count",
        "taux_completion_bloc",
    )
    list_filter = ("type_bloc", "est_visible", "est_obligatoire", "sequence__module__cours")
    search_fields = ("titre", "sequence__titre", "sequence__module__titre", "sequence__module__cours__titre")
    ordering = ("sequence", "ordre")
    autocomplete_fields = ("sequence",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            qs = qs.select_related("sequence__module__cours").annotate(
                _progressions_done_count=Count(
                    "progressions",
                    filter=Q(progressions__est_termine=True),
                    distinct=True
                )
            )
        except Exception:
            qs = qs.select_related("sequence__module__cours")
        return qs

    @admin.display(description="Module")
    def module(self, obj):
        seq = getattr(obj, "sequence", None)
        return getattr(seq, "module", None) if seq else None

    @admin.display(description="Cours")
    def cours(self, obj):
        seq = getattr(obj, "sequence", None)
        mod = getattr(seq, "module", None) if seq else None
        return getattr(mod, "cours", None) if mod else None

    @admin.display(description="Terminés (apprenants)")
    def progressions_done_count(self, obj: BlocContenu):
        return getattr(
            obj,
            "_progressions_done_count",
            BlocProgress.objects.filter(bloc=obj, est_termine=True).count()
        )

    @admin.display(description="Complétion bloc (%)")
    def taux_completion_bloc(self, obj: BlocContenu):
        cours = obj.sequence.module.cours if obj.sequence_id and obj.sequence.module_id else None
        inscrits = safe_count_related(cours, "inscriptions") if cours else 0
        if not inscrits:
            return 0
        termines = self.progressions_done_count(obj)
        return round((termines / inscrits) * 100, 1)


# =============================================================================
# RESSOURCES
# =============================================================================
@admin.register(RessourceSequence)
class RessourceSequenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sequence",
        "module",
        "cours",
        "ordre",
        "titre",
        "type_ressource",
        "taille_lisible",
        "est_telechargeable",
        "nombre_telechargements",
        "date_ajout",
        "date_modification",
    )
    list_filter = ("type_ressource", "est_telechargeable", "sequence__module__cours")
    search_fields = ("titre", "sequence__titre", "sequence__module__titre", "sequence__module__cours__titre")
    ordering = ("sequence", "ordre")
    autocomplete_fields = ("sequence", "ajoute_par")

    @admin.display(description="Module")
    def module(self, obj):
        seq = getattr(obj, "sequence", None)
        return getattr(seq, "module", None) if seq else None

    @admin.display(description="Cours")
    def cours(self, obj):
        seq = getattr(obj, "sequence", None)
        mod = getattr(seq, "module", None) if seq else None
        return getattr(mod, "cours", None) if mod else None

    @admin.display(description="Taille")
    def taille_lisible(self, obj: RessourceSequence):
        return getattr(obj, "taille_lisible", "")


# =============================================================================
# SESSION
# =============================================================================
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
        "participants_count",
    )
    list_filter = ("participation_mode", "cours", "formateur")
    search_fields = ("titre", "cours__matiere__nom", "cours__groupe__nom", "formateur__nom", "formateur__prenom")
    autocomplete_fields = ("cours", "formateur")
    ordering = ("-date_debut",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            qs = qs.annotate(_participants_count=Count("participations", distinct=True))
        except Exception:
            pass
        return qs

    @admin.display(description="Durée (min)")
    def duree_minutes(self, obj: Session):
        return getattr(obj, "duree_minutes", 0)

    @admin.display(description="Participants")
    def participants_count(self, obj: Session):
        return getattr(obj, "_participants_count", safe_count_related(obj, "participations"))


# =============================================================================
# INSCRIPTIONS
# =============================================================================
@admin.register(InscriptionCours)
class InscriptionCoursAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "cours", "date_inscription", "statut")
    list_filter = ("statut", "date_inscription", "cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "apprenant__email", "cours__matiere__nom", "cours__groupe__nom")
    autocomplete_fields = ("apprenant", "cours")
    ordering = ("-date_inscription",)


# =============================================================================
# SUIVI
# =============================================================================
@admin.register(Suivi)
class SuiviAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "cours", "progression", "note", "date_debut")
    list_filter = ("date_debut", "cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "apprenant__email", "cours__matiere__nom")
    autocomplete_fields = ("apprenant", "cours")
    ordering = ("-date_debut",)


# =============================================================================
# PARTICIPATION
# =============================================================================
@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "cours",
        "apprenant",
        "source",
        "statut",
        "created_at",
        "completed_at",
    )
    list_filter = ("source", "statut", "created_at", "session")
    search_fields = ("apprenant__nom", "apprenant__prenom", "apprenant__email", "session__titre", "session__cours__matiere__nom", "session__cours__groupe__nom")
    autocomplete_fields = ("session", "apprenant")
    ordering = ("-created_at",)

    @admin.display(description="Cours")
    def cours(self, obj: Participation):
        s = getattr(obj, "session", None)
        return getattr(s, "cours", None) if s else None


# =============================================================================
# ADMIN PROGRESSION
# =============================================================================
@admin.register(BlocProgress)
class BlocProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "bloc", "sequence", "module", "cours", "est_termine", "completed_at", "updated_at")
    list_filter = ("est_termine", "bloc__type_bloc", "bloc__sequence__module__cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "bloc__titre", "bloc__sequence__titre")
    autocomplete_fields = ("apprenant", "bloc")
    ordering = ("-updated_at",)

    @admin.display(description="Séquence")
    def sequence(self, obj):
        return obj.bloc.sequence

    @admin.display(description="Module")
    def module(self, obj):
        return obj.bloc.sequence.module

    @admin.display(description="Cours")
    def cours(self, obj):
        return obj.bloc.sequence.module.cours


@admin.register(SequenceProgress)
class SequenceProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "sequence", "module", "cours", "est_termine", "completed_at", "updated_at")
    list_filter = ("est_termine", "sequence__module__cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "sequence__titre", "sequence__module__titre")
    autocomplete_fields = ("apprenant", "sequence")
    ordering = ("-updated_at",)

    @admin.display(description="Module")
    def module(self, obj):
        return obj.sequence.module

    @admin.display(description="Cours")
    def cours(self, obj):
        return obj.sequence.module.cours


@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "module", "cours", "est_termine", "completed_at", "updated_at")
    list_filter = ("est_termine", "module__cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "module__titre", "module__cours__titre")
    autocomplete_fields = ("apprenant", "module")
    ordering = ("-updated_at",)

    @admin.display(description="Cours")
    def cours(self, obj):
        return obj.module.cours


@admin.register(CoursProgress)
class CoursProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "cours", "est_termine", "completed_at", "updated_at")
    list_filter = ("est_termine", "cours")
    search_fields = ("apprenant__nom", "apprenant__prenom", "cours__titre", "cours__matiere__nom")
    autocomplete_fields = ("apprenant", "cours")
    ordering = ("-updated_at",)
