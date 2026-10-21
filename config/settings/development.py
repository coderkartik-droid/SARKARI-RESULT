import os

from django.core.management.utils import get_random_secret_key

from .base import *


DEBUG = True
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    get_random_secret_key(),
)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]
# Allow the standard local dev origins (localhost + 127.0.0.1) so the Google
# Identity Services popup POST and AJAX calls pass Django's CSRF origin check.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
