from django.contrib import admin
from .models import (
    Badge, UserBadge, UserLevel, XPTransaction,
    Streak, Mission, UserMission,
)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'nom', 'categorie', 'rarete', 'xp_bonus', 'est_actif')
    list_filter   = ('categorie', 'rarete', 'est_actif')
    search_fields = ('code', 'nom')


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display  = ('apprenant', 'badge', 'obtained_at', 'est_affiche')
    list_filter   = ('badge__categorie', 'est_affiche')
    raw_id_fields = ('apprenant', 'badge')


@admin.register(UserLevel)
class UserLevelAdmin(admin.ModelAdmin):
    list_display  = ('apprenant', 'niveau', 'titre', 'xp_total', 'xp_semaine', 'updated_at')
    list_filter   = ('niveau',)
    raw_id_fields = ('apprenant',)
    readonly_fields = ('titre', 'pct_vers_prochain', 'xp_pour_prochain_niveau')


@admin.register(XPTransaction)
class XPTransactionAdmin(admin.ModelAdmin):
    list_display  = ('apprenant', 'source', 'xp', 'multiplicateur', 'created_at')
    list_filter   = ('source',)
    raw_id_fields = ('apprenant',)
    date_hierarchy = 'created_at'


@admin.register(Streak)
class StreakAdmin(admin.ModelAdmin):
    list_display  = ('apprenant', 'streak_actuel', 'streak_max', 'multiplicateur',
                     'protections_dispo', 'peut_reparer', 'derniere_activite')
    raw_id_fields = ('apprenant',)
    readonly_fields = ('multiplicateur',)


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display  = ('titre', 'type_mission', 'difficulte', 'action', 'quantite',
                     'xp_recompense', 'est_active')
    list_filter   = ('type_mission', 'difficulte', 'est_active')
    search_fields = ('titre', 'action')


@admin.register(UserMission)
class UserMissionAdmin(admin.ModelAdmin):
    list_display  = ('apprenant', 'mission', 'statut', 'progression', 'cible',
                     'assignee_le', 'expire_le', 'completee_le')
    list_filter   = ('statut', 'mission__type_mission')
    raw_id_fields = ('apprenant', 'mission')
    date_hierarchy = 'assignee_le'
