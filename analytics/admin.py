# courses/admin_analytics.py
# ============================================================================
# ADMIN — Analytics
# Couvre les 4 modèles de models_analytics.py :
#   BlocAnalytics           (sessions brutes)
#   BlocAnalyticsSummary    (résumé par apprenant × bloc)
#   SequenceAnalyticsSummary (résumé par apprenant × séquence)
#   ModuleAnalyticsSummary  (résumé par apprenant × module)
# ============================================================================
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Avg, Count

from .models import (
    BlocAnalytics,
    BlocAnalyticsSummary,
    SequenceAnalyticsSummary,
    ModuleAnalyticsSummary,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_duree(secondes: int) -> str:
    """Formate un nombre de secondes en "Xh Ymin" ou "Zmin" ou "Ns"."""
    if not secondes:
        return '—'
    h = secondes // 3600
    m = (secondes % 3600) // 60
    s = secondes % 60
    if h:
        return f'{h}h {m}min'
    if m:
        return f'{m}min {s}s' if s else f'{m}min'
    return f'{s}s'


def _pace_badge(ratio_pct: int) -> str:
    """Retourne un badge HTML coloré selon le ratio temps passé / estimé."""
    if not ratio_pct:
        return '—'
    if ratio_pct < 50:
        color, label = '#16a34a', 'Rapide'
    elif ratio_pct <= 130:
        color, label = '#2563eb', 'Normal'
    else:
        color, label = '#d97706', 'Lent'
    return format_html(
        '<span style="background:{};color:#fff;padding:2px 8px;'
        'border-radius:4px;font-size:11px;font-family:monospace;">'
        '{}&nbsp;{}%</span>',
        color, label, ratio_pct,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. BlocAnalytics — Sessions brutes
# ══════════════════════════════════════════════════════════════════════════════

@admin.register(BlocAnalytics)
class BlocAnalyticsAdmin(admin.ModelAdmin):
    list_display  = (
        'apprenant', 'bloc', 'cours_col', 'module_col',
        'ouvert_le', 'ferme_le', 'duree_fmt',
        'scroll_max_pct', 'complete_en_session',
    )
    list_filter   = (
        'complete_en_session',
        ('ferme_le', admin.DateFieldListFilter),
        ('ouvert_le', admin.DateFieldListFilter),
    )
    search_fields = (
        'apprenant__nom', 'apprenant__prenom',
        'bloc__titre',
        'cours__titre',
    )
    readonly_fields = ('ouvert_le', 'ferme_le')
    date_hierarchy  = 'ouvert_le'
    list_per_page   = 50
    ordering        = ('-ouvert_le',)

    # ── Colonnes calculées ─────────────────────────────────────────────────

    @admin.display(description='Durée', ordering='duree_secondes')
    def duree_fmt(self, obj):
        return _fmt_duree(obj.duree_secondes)

    @admin.display(description='Cours', ordering='cours__titre')
    def cours_col(self, obj):
        return obj.cours.titre if obj.cours else '—'

    @admin.display(description='Module', ordering='module__titre')
    def module_col(self, obj):
        return obj.module.titre if obj.module else '—'

    # ── Actions ───────────────────────────────────────────────────────────

    actions = ['recalculer_summaries']

    @admin.action(description='Recalculer les résumés pour les sessions sélectionnées')
    def recalculer_summaries(self, request, queryset):
        updated = 0
        for session in queryset.filter(ferme_le__isnull=False):
            summary, _ = BlocAnalyticsSummary.objects.get_or_create(
                apprenant=session.apprenant,
                bloc=session.bloc,
                defaults={
                    'sequence': session.sequence,
                    'module':   session.module,
                    'cours':    session.cours,
                },
            )
            summary.recalculer()
            updated += 1
        self.message_user(request, f'{updated} résumé(s) recalculé(s).')


# ══════════════════════════════════════════════════════════════════════════════
# 2. BlocAnalyticsSummary — Résumé par apprenant × bloc
# ══════════════════════════════════════════════════════════════════════════════

@admin.register(BlocAnalyticsSummary)
class BlocAnalyticsSummaryAdmin(admin.ModelAdmin):
    list_display  = (
        'apprenant', 'bloc',
        'nb_ouvertures', 'nb_completions',
        'duree_totale_fmt', 'duree_moy_fmt',
        'scroll_max_pct', 'pace_col',
        'premiere_ouverture', 'derniere_ouverture', 'date_completion',
    )
    list_filter   = (
        ('derniere_ouverture', admin.DateFieldListFilter),
        ('date_completion',    admin.DateFieldListFilter),
    )
    search_fields = (
        'apprenant__nom', 'apprenant__prenom',
        'bloc__titre',
    )
    readonly_fields = (
        'premiere_ouverture', 'derniere_ouverture', 'date_completion', 'updated_at',
    )
    list_per_page = 50
    ordering      = ('-updated_at',)

    # ── Colonnes calculées ─────────────────────────────────────────────────

    @admin.display(description='Temps total', ordering='duree_totale_sec')
    def duree_totale_fmt(self, obj):
        return _fmt_duree(obj.duree_totale_sec)

    @admin.display(description='Temps moyen', ordering='duree_moy_sec')
    def duree_moy_fmt(self, obj):
        return _fmt_duree(obj.duree_moy_sec)

    @admin.display(description='Rythme')
    def pace_col(self, obj):
        return _pace_badge(obj.ratio_temps_pct)
    pace_col.allow_tags = True  # Django < 4.0 compat — ignoré en 4.x

    # ── Actions ───────────────────────────────────────────────────────────

    actions = ['recalculer']

    @admin.action(description='Recalculer les résumés sélectionnés depuis les sessions brutes')
    def recalculer(self, request, queryset):
        for summary in queryset:
            summary.recalculer()
        self.message_user(request, f'{queryset.count()} résumé(s) recalculé(s).')


# ══════════════════════════════════════════════════════════════════════════════
# 3. SequenceAnalyticsSummary — Résumé par apprenant × séquence
# ══════════════════════════════════════════════════════════════════════════════

@admin.register(SequenceAnalyticsSummary)
class SequenceAnalyticsSummaryAdmin(admin.ModelAdmin):
    list_display  = (
        'apprenant', 'sequence', 'module_col',
        'blocs_consultes_col', 'blocs_completes_col',
        'duree_totale_fmt', 'pace_col',
        'nb_quiz_passes', 'score_moyen_quiz',
        'premiere_activite', 'derniere_activite', 'completee_le',
    )
    list_filter   = (
        ('completee_le',       admin.DateFieldListFilter),
        ('derniere_activite',  admin.DateFieldListFilter),
    )
    search_fields = (
        'apprenant__nom', 'apprenant__prenom',
        'sequence__titre',
    )
    readonly_fields = (
        'premiere_activite', 'derniere_activite', 'completee_le', 'updated_at',
    )
    list_per_page = 50
    ordering      = ('-updated_at',)

    @admin.display(description='Module', ordering='module__titre')
    def module_col(self, obj):
        return obj.module.titre if obj.module else '—'

    @admin.display(description='Blocs vus')
    def blocs_consultes_col(self, obj):
        return f'{obj.nb_blocs_consultes} / {obj.nb_blocs_total}'

    @admin.display(description='Blocs terminés')
    def blocs_completes_col(self, obj):
        return f'{obj.nb_blocs_completes} / {obj.nb_blocs_total}'

    @admin.display(description='Temps total', ordering='duree_totale_sec')
    def duree_totale_fmt(self, obj):
        return _fmt_duree(obj.duree_totale_sec)

    @admin.display(description='Rythme')
    def pace_col(self, obj):
        return _pace_badge(obj.ratio_temps_pct)


# ══════════════════════════════════════════════════════════════════════════════
# 4. ModuleAnalyticsSummary — Résumé par apprenant × module
# ══════════════════════════════════════════════════════════════════════════════

@admin.register(ModuleAnalyticsSummary)
class ModuleAnalyticsSummaryAdmin(admin.ModelAdmin):
    list_display  = (
        'apprenant', 'module', 'cours_col',
        'sequences_col', 'blocs_col',
        'duree_totale_fmt', 'pace_col',
        'score_moyen_quiz',
        'premiere_activite', 'derniere_activite', 'complete_le',
    )
    list_filter   = (
        ('complete_le',        admin.DateFieldListFilter),
        ('derniere_activite',  admin.DateFieldListFilter),
    )
    search_fields = (
        'apprenant__nom', 'apprenant__prenom',
        'module__titre',
        'cours__titre',
    )
    readonly_fields = (
        'premiere_activite', 'derniere_activite', 'complete_le', 'updated_at',
    )
    list_per_page = 50
    ordering      = ('-updated_at',)

    @admin.display(description='Cours', ordering='cours__titre')
    def cours_col(self, obj):
        return obj.cours.titre if obj.cours else '—'

    @admin.display(description='Séquences')
    def sequences_col(self, obj):
        return f'{obj.nb_sequences_consultees} / {obj.nb_sequences_total}'

    @admin.display(description='Blocs terminés')
    def blocs_col(self, obj):
        return f'{obj.nb_blocs_completes} / {obj.nb_blocs_total}'

    @admin.display(description='Temps total', ordering='duree_totale_sec')
    def duree_totale_fmt(self, obj):
        return _fmt_duree(obj.duree_totale_sec)

    @admin.display(description='Rythme')
    def pace_col(self, obj):
        return _pace_badge(obj.ratio_temps_pct)