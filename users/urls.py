from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter
from .views import (
    ChangePasswordAPIView,
    LogoutAPIView,
    PasswordResetAPIView,
    PasswordResetConfirmAPIView,
    RegisterAPIView,
    ResendCodeAPIView,
    UserLoginAPIView,
    VerifyEmailAPIView,
    AdminViewSet,
    ParentViewSet,
    ApprenantViewSet,
    FormateurViewSet,
    ResponsableAcademiqueViewSet,
)


from core.rbac_api import RolesListView, RolePermissionsView, RoleFeaturesView
from .search_views import GlobalSearchAPIView
from .import_users_views import (
    UtilisateurImportAnalyseAPIView,
    UtilisateurImportCreateAPIView,
)


router = DefaultRouter()

router.register(r'admins', AdminViewSet, basename='admins')
router.register(r'parents', ParentViewSet, basename='parents')
router.register(r'apprenants', ApprenantViewSet, basename='apprenants')
router.register(r'formateurs', FormateurViewSet, basename='formateurs')
router.register(r'responsables-academiques', ResponsableAcademiqueViewSet, basename='responsables-academiques')

urlpatterns = [
    path('login/', UserLoginAPIView.as_view(), name='user-login'),

    # Nouveau flow unifié
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('verify-email/', VerifyEmailAPIView.as_view(), name='verify_email'),
    path('resend-code/', ResendCodeAPIView.as_view(), name='resend_code'),
    path('logout/', LogoutAPIView.as_view(), name='logout'),
    path('change-password/', ChangePasswordAPIView.as_view(), name='change-password'),


    # ✅ Password reset
    path('password-reset/',                              PasswordResetAPIView.as_view(),        name='password_reset'),
    path('password-reset/confirm/',                      PasswordResetConfirmAPIView.as_view(), name='password_reset_confirm'),
    # ✅ Route alternative avec uid/token dans l'URL (optionnel)
    path('password-reset/confirm/<str:uidb64>/<str:token>/', PasswordResetConfirmAPIView.as_view(), name='password_reset_confirm_url'),


    # ── Recherche globale ────────────────────────────────────────────────────
    path('search/', GlobalSearchAPIView.as_view(), name='global-search'),

    # ── RBAC : rôles & permissions ───────────────────────────────────────────
    path('rbac/roles/', RolesListView.as_view(), name='rbac-roles'),
    path('rbac/roles/<str:role>/permissions/', RolePermissionsView.as_view(), name='rbac-role-permissions'),
    path('rbac/roles/<str:role>/features/', RoleFeaturesView.as_view(), name='rbac-role-features'),

    # ── Import utilisateurs (formateurs / responsables) ──────────────────────
    path('utilisateurs/importer/analyser/', UtilisateurImportAnalyseAPIView.as_view(), name='utilisateurs-import-analyser'),
    path('utilisateurs/importer/', UtilisateurImportCreateAPIView.as_view(), name='utilisateurs-import-create'),

    path('', include(router.urls)),
]
