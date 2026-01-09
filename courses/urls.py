from django.urls import path
from .views import (
    CoursDetailAPIView, CoursListCreateAPIView, SequenceListCreateAPIView, ModuleListCreateAPIView, InscriptionCoursListCreateAPIView,
    SuiviListCreateAPIView, SessionListCreateAPIView, ParticipationListCreateAPIView
)

urlpatterns = [
     path("cours/", CoursListCreateAPIView.as_view(), name="cours-list-create"),
    path("cours/<int:pk>/", CoursDetailAPIView.as_view(), name="cours-detail"),
    path('sequences/', SequenceListCreateAPIView.as_view(), name='sequence-list-create'),
    path('modules/', ModuleListCreateAPIView.as_view(), name='module-list-create'),
    path('inscriptions-cours/', InscriptionCoursListCreateAPIView.as_view(), name='inscription-cours-list-create'),
    path('suivis/', SuiviListCreateAPIView.as_view(), name='suivi-list-create'),
    path('sessions/', SessionListCreateAPIView.as_view(), name='session-list-create'),
    path('participations/', ParticipationListCreateAPIView.as_view(), name='participation-list-create'),
]
        

