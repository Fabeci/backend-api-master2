from django.urls import include, path
from academics import views
from academics import viewsets as vset
from academics.import_inscriptions_etab_views import (
    InscriptionEtabImportAnalyseAPIView,
    InscriptionEtabImportCreateAPIView,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'domaines-etudes', vset.DomaineEtudeViewSet, basename='domaine')
router.register(r'matieres', vset.MatiereViewSet, basename='matiere')
router.register(r'specialites', vset.SpecialiteViewSet, basename='specialite')
router.register(r'annees-scolaires', vset.AnneeScolaireViewSet, basename='annees-scolaires')
router.register(r'affectations', vset.AffectationEnseignementViewSet, basename='affectation')
router.register(r'semestres', vset.SemestreViewSet, basename='semestre')
router.register(r'ues', vset.UEViewSet, basename='ue')

handler404 = 'academics.views.custom_404_handler'

urlpatterns = [
    path('', include(router.urls)),

    # ✅ LMD — bulletin
    path('bulletins/<int:apprenant_id>/<int:annee_id>/', views.BulletinAPIView.as_view(), name='bulletin'),
    path('bulletins/<int:apprenant_id>/<int:annee_id>/export/', views.BulletinExportAPIView.as_view(), name='bulletin-export'),
    path('bulletins/<int:apprenant_id>/<int:annee_id>/export/pdf/', views.BulletinPDFAPIView.as_view(), name='bulletin-pdf'),

    path('institutions/', views.InstitutionAPIView.as_view(), name='institution-list-create'),
    path('institutions/<int:pk>/', views.InstitutionAPIView.as_view(), name='institution-detail'),
    path('institutions/<int:pk>/upload-logo/', views.InstitutionLogoUploadAPIView.as_view(), name='institution-upload-logo'),

    path('filieres/', views.FiliereListCreateAPIView.as_view(), name='filiere-list-create'),
    path('filieres/<int:pk>/', views.FiliereDetailAPIView.as_view(), name='filiere-detail'),

    path('groupes/', views.GroupeListCreateAPIView.as_view(), name='groupe-list-create'),
    path('groupes/<int:pk>/', views.GroupeDetailAPIView.as_view(), name='groupe-detail'),

    path('classes/', views.ClasseListCreateAPIView.as_view(), name='classe-list-create'),
    path('classes/<int:pk>/', views.ClasseDetailAPIView.as_view(), name='classe-detail'),

    # ✅ Retiré le doublon api/ → devient /api/inscriptions/
    path('inscriptions-etab/', views.InscriptionListCreateAPIView.as_view(), name='inscription-list-create'),
    # Import d'inscriptions à l'établissement / année courante
    path('inscriptions-etab/importer/analyser/', InscriptionEtabImportAnalyseAPIView.as_view(), name='inscriptions-etab-import-analyser'),
    path('inscriptions-etab/importer/', InscriptionEtabImportCreateAPIView.as_view(), name='inscriptions-etab-import-create'),
    path('inscriptions-etab/<int:pk>/', views.InscriptionDetailAPIView.as_view(), name='inscription-detail'),

    path('departements/', views.DepartementListCreateAPIView.as_view(), name='departement-list-create'),
    path('departements/<int:pk>/', views.DepartementDetailAPIView.as_view(), name='departement-detail'),
]