# parametres/urls.py
from django.urls import path
from .views import (
    ParametresPlateformeView,
    ParametresInstitutionView,
    PreferencesUtilisateurView,
    IntegrationsStatusAPIView,
    ContactMessageAPIView,
)

urlpatterns = [
    path('contact/', ContactMessageAPIView.as_view(), name='contact'),
    path('settings/global/',      ParametresPlateformeView.as_view(),    name='settings-global'),
    path('settings/institution/', ParametresInstitutionView.as_view(),   name='settings-institution'),
    path('settings/preferences/', PreferencesUtilisateurView.as_view(),  name='settings-preferences'),
    path('settings/integrations/', IntegrationsStatusAPIView.as_view(),  name='settings-integrations'),
]
