import os

from django.core.management.utils import get_random_secret_key

from .base import *


DEBUG = True
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    get_random_secret_key(),
)
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "10.0.2.2",
]

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://10.0.2.2:8000",
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
