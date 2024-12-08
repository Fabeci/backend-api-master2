from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    ActivateUserAPIView,
    LogoutAPIView,
    PasswordResetAPIView,
    PasswordResetConfirmAPIView,
    SuperAdminListCreateAPIView,
    ParentListCreateAPIView,
    FormateurListCreateAPIView,
    ResponsableAcademiqueListCreateAPIView,
    AdminListCreateAPIView,  # Déjà définis
    ApprenantListCreateAPIView,
    UserLoginAPIView,
)

urlpatterns = [
    path('login/', UserLoginAPIView.as_view(), name='user-login'),
    path('logout/', LogoutAPIView.as_view(), name='logout'),
    path('admins/', AdminListCreateAPIView.as_view(), name='admin-list-create'),
    path('apprenants/', ApprenantListCreateAPIView.as_view(), name='apprenant-list-create'),
    path('superadmins/', SuperAdminListCreateAPIView.as_view(), name='superadmin-list-create'),
    path('parents/', ParentListCreateAPIView.as_view(), name='parent-list-create'),
    path('formateurs/', FormateurListCreateAPIView.as_view(), name='formateur-list-create'),
    path('responsables-academiques/', ResponsableAcademiqueListCreateAPIView.as_view(), name='responsable-list-create'),
    path('activate/<uidb64>/<token>/', ActivateUserAPIView.as_view(), name='activate_user'),
    path('password-reset/', PasswordResetAPIView.as_view(), name='password_reset'),
    path(
        'password-reset-confirm/<uidb64>/<token>/', PasswordResetConfirmAPIView.as_view(), name='password_reset_confirm',
    ),
]
