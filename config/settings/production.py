import os
from django.core.exceptions import ImproperlyConfigured

from .base import *


DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to a unique, randomly generated key of at least 50 characters."
    )

# Render injects RENDER_EXTERNAL_HOSTNAME with the service's *.onrender.com
# hostname. Trusting it automatically means the first deploy works without
# hard-coding (or guessing) the final hostname. Custom domains are added
# explicitly through DJANGO_ALLOWED_HOSTS.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS in the production environment.")

# The Render host is also a trusted CSRF origin, so admin/public POST forms
# (login, save, AI widget) pass Django's origin check over HTTPS.
if RENDER_EXTERNAL_HOSTNAME:
    _render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)

# A managed PostgreSQL database is mandatory in production. Fail loudly here
# rather than silently falling back to the local SQLite file.
if not os.environ.get("DATABASE_URL", "").strip():
    raise ImproperlyConfigured(
        "Set DATABASE_URL to the PostgreSQL connection string before using production settings."
    )

# Render terminates TLS at its proxy and forwards the original scheme in this
# header, which lets Django detect HTTPS and keep SECURE_SSL_REDIRECT working
# without a redirect loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# WhiteNoise serves the files produced by collectstatic directly from the WSGI
# app, so no separate static host is required. It is inserted right after
# SecurityMiddleware (which must stay first).
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # No manifest: compression without hashed-name lookups, so a missing
        # reference can never break the whole site.
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not os.environ.get("EMAIL_BACKEND"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
