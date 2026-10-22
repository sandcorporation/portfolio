"""Django settings. Every deploy-specific value comes from the environment (see /.env.example)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("dev-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is not 1")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
# NPMplus terminates TLS and forwards X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# The site is served over HTTPS only; keep the admin session and CSRF cookies off plain HTTP.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "content",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.admin_ratelimit.AdminLoginRateLimitMiddleware",  # temporary (#25)
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "portfolio"),
        "USER": env("POSTGRES_USER", "portfolio"),
        "PASSWORD": env("POSTGRES_PASSWORD", "portfolio"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "15442"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Shared across gunicorn workers (a per-process cache would multiply the limit by the worker count).
# Create the table with `manage.py createcachetable` (deploy.sh does, after migrate).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Temporary admin password login limit (issue #25), next to the sandcorp-auth login until a
# follow-up to #7 removes it. See core/admin_ratelimit.py.
ADMIN_LOGIN_MAX_FAILURES = 5
ADMIN_LOGIN_WINDOW_SECONDS = 15 * 60
# Proxies in front of Django that append to X-Forwarded-For (NPMplus = 1). Every IP rate limit
# reads it through core/clientip.py. The old name still works so existing .env files keep working.
PROXY_HOPS = int(env("PROXY_HOPS", env("ADMIN_LOGIN_PROXY_HOPS", "1")))

# Inquiry form (issue #17). Server-to-server posts (news site) prove themselves with the shared
# secret; empty means no one can. The Discord webhook URL is secret too; empty skips alerts only.
INQUIRY_SHARED_SECRET = env("INQUIRY_SHARED_SECRET")
INQUIRY_RATE_LIMIT = 5  # browser submissions per IP per window
INQUIRY_RATE_WINDOW_SECONDS = 60 * 60
DISCORD_WEBHOOK_URL = env("DISCORD_WEBHOOK_URL")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# Django admin lives on a hard-to-guess path in production.
# Absolute-URL base for sitemap.xml and robots.txt (they have no request host to trust).
SITE_URL = env("SITE_URL", "https://sandcorp.co.kr").rstrip("/")
# sandcorp-auth: the owner's username, the only `sub` this site accepts (empty -> /mcp is 503).
AUTH_OWNER_SUB = env("AUTH_OWNER_SUB").strip()
ADMIN_PATH = env("DJANGO_ADMIN_PATH", "admin/").strip("/") + "/"
# sandcorp-auth confidential client for the admin login (oauth/login.py). Registered at
# sandcorp-auth with redirect URI `{SITE_URL}/{ADMIN_PATH}oauth/callback/`.
# Empty -> only the sandcorp-auth admin login is off (503); the site runs.
AUTH_CLIENT_ID = env("AUTH_CLIENT_ID").strip()
AUTH_CLIENT_SECRET = env("AUTH_CLIENT_SECRET").strip()

# Static files: whitenoise serves collectstatic output, which includes the Vite build.
STATIC_URL = "/static/"
STATIC_ROOT = Path(env("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles")))
FRONTEND_DIST = Path(env("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.is_dir() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Object storage (OCI S3-compatible API). Without these the site runs and only media is off.
STORAGE_ENDPOINT_URL = env("STORAGE_ENDPOINT_URL")
STORAGE_REGION = env("STORAGE_REGION", "ap-chuncheon-1")
STORAGE_ACCESS_KEY = env("STORAGE_ACCESS_KEY")
STORAGE_SECRET_KEY = env("STORAGE_SECRET_KEY")
STORAGE_PUBLIC_BUCKET = env("STORAGE_PUBLIC_BUCKET")
STORAGE_PRIVATE_BUCKET = env("STORAGE_PRIVATE_BUCKET")
STORAGE_PUBLIC_BASE_URL = env("STORAGE_PUBLIC_BASE_URL")

# HTML shell <-> Vite. In dev, point VITE_DEV_SERVER_URL at `pnpm dev` (http://localhost:5173);
# otherwise the shell reads the build manifest.
VITE_DEV_SERVER_URL = env("VITE_DEV_SERVER_URL").rstrip("/")
VITE_MANIFEST_PATH = FRONTEND_DIST / ".vite" / "manifest.json"
VITE_ENTRY = "src/main.tsx"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}

# Proposals: the supplier named on every cover, and how long a signed preview link lives. Thirty
# minutes covers reading a draft through; an older link is simply issued again from the admin.
SUPPLIER_NAME = env("SUPPLIER_NAME", "샌드코프")
PROPOSAL_PREVIEW_MAX_AGE = 30 * 60
# The customer page (/p/<slug>): a right code opens a seven-day session for that proposal; five
# wrong ones from one IP block that IP for fifteen minutes, right code or not.
PROPOSAL_SESSION_MAX_AGE = 7 * 24 * 60 * 60
PROPOSAL_CODE_MAX_FAILURES = 5
PROPOSAL_CODE_BLOCK_SECONDS = 15 * 60
