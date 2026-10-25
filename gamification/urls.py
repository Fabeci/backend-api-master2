from django.urls import path
from .views import (
    GamificationProfileView,
    XPHistoryView,
    BadgesView,
    MissionsView,
    StreakProtectView,
    StreakRepairView,
    LeaderboardView,
)

app_name = 'gamification'

urlpatterns = [
    path('gamification/profil/<int:apprenant_id>/',   GamificationProfileView.as_view(), name='profil'),
    path('gamification/xp-history/<int:apprenant_id>/', XPHistoryView.as_view(),         name='xp-history'),
    path('gamification/badges/<int:apprenant_id>/',   BadgesView.as_view(),              name='badges'),
    path('gamification/missions/<int:apprenant_id>/', MissionsView.as_view(),            name='missions'),
    path('gamification/streak/protect/',              StreakProtectView.as_view(),        name='streak-protect'),
    path('gamification/streak/repair/',               StreakRepairView.as_view(),         name='streak-repair'),
    path('gamification/leaderboard/',                 LeaderboardView.as_view(),         name='leaderboard'),
]
