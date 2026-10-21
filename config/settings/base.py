import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts.apps.AccountsConfig",
    "comments.apps.CommentsConfig",
    "jobs.apps.JobsConfig",
    "ai_assistant.apps.AiAssistantConfig",
    "site_management.apps.SiteManagementConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DB_ENGINE = os.environ.get("DB_ENGINE", "django.db.backends.sqlite3")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    # Preferred path: a single connection URL. On Render this is provided by
    # the managed PostgreSQL database (DATABASE_URL env var), so no host,
    # user, password or port is ever hard-coded here.
    _db_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600") or "600"),
        conn_health_checks=True,
    )
    if str(_db_config.get("ENGINE", "")).endswith("postgresql"):
        _db_options = _db_config.setdefault("OPTIONS", {})
        # Encrypt the connection to Render PostgreSQL. An explicit DB_SSLMODE
        # overrides everything; otherwise existing "?sslmode=..." parameters
        # from the URL are kept, and "require" is used as the safe default.
        # "require" encrypts the connection but does not verify the CA chain,
        # because Render's managed certificate is not guaranteed to chain to a
        # public root in every region; set DB_SSLMODE=verify-full to enforce
        # full certificate validation.
        _db_options.setdefault(
            "sslmode",
            os.environ.get("DB_SSLMODE", "").strip() or "require",
        )
    DATABASES = {"default": _db_config}
elif DB_ENGINE == "django.db.backends.sqlite3":
    # Local development fallback. Only reached when DATABASE_URL is not set.
    # The existing db.sqlite3 is used as-is and is never modified here.
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": os.environ.get("DB_NAME", ""),
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", ""),
            "PORT": os.environ.get("DB_PORT", ""),
            **(
                {"OPTIONS": {"sslmode": os.environ["DB_SSLMODE"]}}
                if os.environ.get("DB_SSLMODE")
                else {}
            ),
        }
    }

AUTH_USER_MODEL = "accounts.EmailUser"
AUTHENTICATION_BACKENDS = ["accounts.backends.UsernameOrEmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "accounts.validators.PasswordPolicyValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "collected_static"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
CMS_MAX_IMAGE_SIZE = int(os.environ.get("CMS_MAX_IMAGE_SIZE", str(5 * 1024 * 1024)))
if CMS_MAX_IMAGE_SIZE <= 0:
    raise ImproperlyConfigured("CMS_MAX_IMAGE_SIZE must be a positive number of bytes.")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "home"

# Keep staff sessions persistent across browser restarts and refresh their
# expiration while requests continue. Django still validates the user and
# session authentication hash on every request.
SESSION_COOKIE_AGE = 10 * 365 * 24 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CSRF_COOKIE_HTTPONLY = True

PORTAL_SOCIAL_LINKS = {
    "instagram": os.environ.get("PORTAL_INSTAGRAM_URL", "").strip(),
    "facebook": os.environ.get("PORTAL_FACEBOOK_URL", "").strip(),
    "youtube": os.environ.get("PORTAL_YOUTUBE_URL", "").strip(),
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "niyukti-login-throttle",
    }
}

# ==========================================
# AI PROVIDER CONFIGURATION
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"
GEMINI_MODEL_EXPLICIT = bool(os.environ.get("GEMINI_MODEL", "").strip())
GEMINI_PLACEHOLDER_KEY = "PASTE_YOUR_GEMINI_API_KEY_HERE"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
OPENAI_MODEL_EXPLICIT = bool(os.environ.get("OPENAI_MODEL", "").strip())
OPENAI_PLACEHOLDER_KEY = "PASTE_YOUR_OPENAI_API_KEY_HERE"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = (
    os.environ.get("OPENROUTER_MODEL", "").strip()
    or "nvidia/nemotron-3-ultra-550b-a55b-20260604"
)
OPENROUTER_MODEL_EXPLICIT = bool(os.environ.get("OPENROUTER_MODEL", "").strip())
OPENROUTER_PLACEHOLDER_KEY = "PASTE_YOUR_OPENROUTER_API_KEY_HERE"
GROK_API_KEY = os.environ.get("GROK_API_KEY", "").strip()
GROK_MODEL = os.environ.get("GROK_MODEL", "").strip() or "grok-4.7"
GROK_MODEL_EXPLICIT = bool(os.environ.get("GROK_MODEL", "").strip())
GROK_PLACEHOLDER_KEY = "PASTE_YOUR_GROK_API_KEY_HERE"
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
AI_ENABLED = os.environ.get("AI_ENABLED", "False").strip().lower() in ("true", "1", "yes", "t")
AI_RATE_LIMIT_PER_MINUTE = int(os.environ.get("AI_RATE_LIMIT_PER_MINUTE", "15"))
AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "30"))
AI_MAX_OUTPUT_TOKENS = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "1024"))
 
# ==========================================
# EMAIL & PASSWORD RESET CONFIGURATION
# ==========================================
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("true", "1", "yes", "t")
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False").lower() in ("true", "1", "yes", "t")
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Niyukti Portal <no-reply@localhost>",
)
PASSWORD_RESET_TIMEOUT = int(os.environ.get("PASSWORD_RESET_TIMEOUT", "86400"))

# ==========================================
# GOOGLE OAUTH & ALLAUTH CONFIGURATION
# ==========================================
# .env injection point: the client id/secret are read from GOOGLE_CLIENT_ID /
# GOOGLE_CLIENT_SECRET (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET are
# accepted as legacy aliases). Never hard-code credentials here.
_GOOGLE_CLIENT_ID = (
    os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    or os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
)
_GOOGLE_CLIENT_SECRET = (
    os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
)
GOOGLE_OAUTH_PLACEHOLDER = "YOUR_GOOGLE_CLIENT_ID_HERE"
GOOGLE_OAUTH_CLIENT_ID = _GOOGLE_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET = _GOOGLE_CLIENT_SECRET

ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
# Accept EITHER username or email in the login form (equivalent to the
# classic ACCOUNT_AUTHENTICATION_METHOD = 'username_email').
ACCOUNT_LOGIN_METHODS = {"username", "email"}
# Email is mandatory at signup (both allauth and the custom SignupForm);
# ACCOUNT_SIGNUP_FIELDS below marks email with '*' (required).
# (ACCOUNT_EMAIL_REQUIRED is deprecated in allauth 65+ — do not set it.)
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*"]
ACCOUNT_EMAIL_VERIFICATION = "none"

SOCIALACCOUNT_ADAPTER = "accounts.adapter.CustomSocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": _GOOGLE_CLIENT_ID,
                "secret": _GOOGLE_CLIENT_SECRET,
                "key": "",
            }
        ]
        if _GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET
        else [],
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
    }
}
