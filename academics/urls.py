from django.urls import include, path
from academics import views
from academics import viewsets as vset
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'domaines-etudes', vset.DomaineEtudeViewSet, basename='domaine')
router.register(r'matieres', vset.MatiereViewSet, basename='matiere')
router.register(r'specialites', vset.SpecialiteViewSet, basename='specialite')
router.register(r'annees-scolaires', vset.AnneeScolaireViewSet, basename='annees-scolaires')

handler404 = 'academics.views.custom_404_handler'

urlpatterns = [
    path('', include(router.urls)),
    # path('institutions/create/', InstitutionCreateAPIView.as_view(), name='institution-create'),
    path('institutions/', views.InstitutionAPIView.as_view(), name='institution-list-create'),
    path('institutions/<int:pk>/', views.InstitutionAPIView.as_view(), name='institution-detail'),
    
    path('filieres/', views.FiliereListCreateAPIView.as_view(), name='filiere-list-create'),
    path('filieres/<int:pk>/', views.FiliereDetailAPIView.as_view(), name='filiere-detail'),
    
    path('groupes/', views.GroupeListCreateAPIView.as_view(), name='groupe-list-create'),
    path('groupes/<int:pk>/', views.GroupeDetailAPIView.as_view(), name='groupe-detail'),
    
    path('classes/', views.ClasseListCreateAPIView.as_view(), name='classe-list-create'),
    path('classes/<int:pk>/', views.ClasseDetailAPIView.as_view(), name='classe-detail'),
    
    path('api/inscriptions/', views.InscriptionListCreateAPIView.as_view(), name='inscription-list-create'),
    path('api/inscriptions/<int:pk>/', views.InscriptionDetailAPIView.as_view(), name='inscription-detail'),

    path("departements/", views.DepartementListCreateAPIView.as_view(), name="departement-list-create"),
    path("departements/<int:pk>/", views.DepartementDetailAPIView.as_view(), name="departement-detail"),
]