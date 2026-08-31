from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("core.urls", namespace="core")),
]

# django.contrib.staticfiles serves STATICFILES_DIRS while DEBUG=True.  Only
# media needs an explicit development route.  This avoids serving stale files
# from STATIC_ROOT during normal local development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
