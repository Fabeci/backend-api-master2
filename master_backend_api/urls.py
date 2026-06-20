"""
URL configuration for prograppApi project.
"""
from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from users import dashboard_urls

schema_view = get_schema_view(
   openapi.Info(
      title="SOMAPRO API",
      default_version='v1',
      description="Documentation interactive de l'API",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="contact@tonapi.local"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('admin/dashboard/', include(dashboard_urls)),  # Dashboards personnalisés (doit être avant admin/)
    path('admin/', admin.site.urls),
    # API v1 — préfixe versionné
    path('api/v1/', include('users.urls')),
    path('api/v1/', include('academics.urls')),
    path('api/v1/', include('locations.urls')),
    path('api/v1/', include('courses.urls_ai')),
    path('api/v1/', include('courses.urls')),
    path('api/v1/', include('collaborations.urls')),
    path('api/v1/', include('evaluations.urls')),
    path('api/v1/', include('progress.urls')),
    path('api/v1/', include('notifications.urls')),
    path('api/v1/', include('resources.urls')),
    path('api/v1/', include('analytics.urls')),
]

# ✅ Servir les fichiers media EN DÉVELOPPEMENT
# static() ne fonctionne que si DEBUG=True — on le force pour le dev local
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)