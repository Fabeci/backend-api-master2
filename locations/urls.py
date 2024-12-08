from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaysViewSet, VilleViewSet, QuartierViewSet

router = DefaultRouter()
router.register(r'pays', PaysViewSet)
router.register(r'villes', VilleViewSet)
router.register(r'quartiers', QuartierViewSet)

urlpatterns = [
    # path('api/', include(router.urls)),
]

urlpatterns = router.urls