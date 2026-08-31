import os

from django.core.wsgi import get_wsgi_application


settings_module = os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "djecommerce.settings.production"
)
allowed_modules = {
    "djecommerce.settings.development",
    "djecommerce.settings.production",
}
if settings_module not in allowed_modules:
    raise RuntimeError(f"Unsupported DJANGO_SETTINGS_MODULE: {settings_module}")

application = get_wsgi_application()
