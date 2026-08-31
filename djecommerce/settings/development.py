from decouple import config

from .base import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
INTERNAL_IPS = ["127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

STRIPE_PUBLIC_KEY = config("STRIPE_TEST_PUBLIC_KEY", default="")
STRIPE_SECRET_KEY = config("STRIPE_TEST_SECRET_KEY", default="")
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
