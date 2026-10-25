from django.urls import path
from . import admin_dashboard

urlpatterns = [
    path('', admin_dashboard.DashboardIndexView.as_view(), name='dashboard-index'),
    path('superadmin/', admin_dashboard.SuperAdminDashboardView.as_view(), name='dashboard-superadmin'),
    path('admin/', admin_dashboard.AdminDashboardView.as_view(), name='dashboard-admin'),
    path('formateur/', admin_dashboard.FormateurDashboardView.as_view(), name='dashboard-formateur'),
    path('parent/', admin_dashboard.ParentDashboardView.as_view(), name='dashboard-parent'),
    path('responsable/', admin_dashboard.ResponsableDashboardView.as_view(), name='dashboard-responsable'),
    path('apprenant/', admin_dashboard.ApprenantDashboardView.as_view(), name='dashboard-apprenant'),
]
