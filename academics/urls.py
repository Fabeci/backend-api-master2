from django.urls import include, path
from .views import AnneeScolaireViewSet, ClasseDetailAPIView, ClasseListCreateAPIView, DomaineEtudeViewSet, FiliereDetailAPIView, FiliereListCreateAPIView, GroupeDetailAPIView, GroupeListCreateAPIView, InscriptionDetailAPIView, InscriptionListCreateAPIView, InstitutionCreateAPIView, MatiereViewSet, SpecialiteViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'domaines-etudes', DomaineEtudeViewSet, basename='domaine')
router.register(r'matieres', MatiereViewSet, basename='matiere')
router.register(r'specialites', SpecialiteViewSet, basename='specialite')
router.register(r'annees-scolaires', AnneeScolaireViewSet, basename='annees-scolaires')

urlpatterns = [
    path('', include(router.urls)),
    path('institutions/create/', InstitutionCreateAPIView.as_view(), name='institution-create'),
    
    path('filieres/', FiliereListCreateAPIView.as_view(), name='filiere-list-create'),
    path('filieres/<int:pk>/', FiliereDetailAPIView.as_view(), name='filiere-detail'),
    
    path('groupes/', GroupeListCreateAPIView.as_view(), name='groupe-list-create'),
    path('groupes/<int:pk>/', GroupeDetailAPIView.as_view(), name='groupe-detail'),
    
    path('classes/', ClasseListCreateAPIView.as_view(), name='classe-list-create'),
    path('classes/<int:pk>/', ClasseDetailAPIView.as_view(), name='classe-detail'),
    
    path('api/inscriptions/', InscriptionListCreateAPIView.as_view(), name='inscription-list-create'),
    path('api/inscriptions/<int:pk>/', InscriptionDetailAPIView.as_view(), name='inscription-detail'),
]