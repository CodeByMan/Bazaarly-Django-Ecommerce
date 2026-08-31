from decouple import Csv, config

from .base import *  # noqa: F403


DEBUG = False

SECRET_KEY = config("SECRET_KEY")
if len(SECRET_KEY) < 50 or SECRET_KEY == "unsafe-development-key-change-me":
    raise RuntimeError("Production SECRET_KEY must be a unique value of at least 50 characters.")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())
if not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS is required in production.")

CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
if not CSRF_TRUSTED_ORIGINS:
    raise RuntimeError("CSRF_TRUSTED_ORIGINS is required in production.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

# This portfolio prototype intentionally accepts Stripe test credentials only.
STRIPE_PUBLIC_KEY = config("STRIPE_TEST_PUBLIC_KEY")
STRIPE_SECRET_KEY = config("STRIPE_TEST_SECRET_KEY")
if not STRIPE_PUBLIC_KEY.startswith("pk_test_") or not STRIPE_SECRET_KEY.startswith("sk_test_"):
    raise RuntimeError("Only Stripe test-mode keys are accepted.")

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
