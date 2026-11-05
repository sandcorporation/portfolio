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
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RuntimeSettingsMiddleware",
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

# MySQL (OCI HeatWave in production, `make db` locally). The database is created with
# utf8mb4 / utf8mb4_0900_as_cs so slugs, client codes and usernames compare case-sensitively,
# as they did on Postgres. Django opens sessions in READ COMMITTED; keep it (the document-number
# serialisation in services/publishing.py relies on reading the latest commit after the lock).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "portfolio"),
        "USER": env("DB_USER", "portfolio"),
        "PASSWORD": env("DB_PASSWORD", "portfolio"),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "3306"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"charset": "utf8mb4"},
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_0900_as_cs"},
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
# Used by the proposal access-code limit, the inquiry limit and the tracking dedupe.
# Create the table with `manage.py createcachetable` (deploy.sh does, after migrate).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Proxies in front of Django that append to X-Forwarded-For (NPMplus = 1). Every IP rate limit
# reads it through core/clientip.py.
PROXY_HOPS = int(env("PROXY_HOPS", "1"))

# Inquiry form (issue #17). Server-to-server posts (news site) prove themselves with the shared
# secret; empty means no one can. The Discord webhook URL is secret too; empty skips alerts only.
# The names in services/runtime_settings.py::REGISTRY are only the fallback: an admin 「운영 설정」
# override wins (#233), so read them through runtime_settings.get, never settings.<name>.
INQUIRY_SHARED_SECRET = env("INQUIRY_SHARED_SECRET")
INQUIRY_RATE_LIMIT = 5  # browser submissions per IP per window
INQUIRY_RATE_WINDOW_SECONDS = 60 * 60
DISCORD_WEBHOOK_URL = env("DISCORD_WEBHOOK_URL")
DISCORD_ALERTS_WEBHOOK_URL = env("DISCORD_ALERTS_WEBHOOK_URL")

# Foresight (news.sandcorp.co.kr) public JSON for the home page's recent-articles section (#74).
# Empty turns the section off. The adapter caches 10 minutes in django_cache.
FORESIGHT_API_URL = env("FORESIGHT_API_URL", "https://news.sandcorp.co.kr/api/public/articles")
# Aggregate numbers (AI-Trend-News #77) for the home evidence row (#91). Empty switches it off.
FORESIGHT_STATS_URL = env("FORESIGHT_STATS_URL", "https://news.sandcorp.co.kr/api/public/stats")
FORESIGHT_TIMEOUT_SECONDS = 3

# YouTube oEmbed for a Short's title when it is registered (issue 207). Empty never looks titles up.
YOUTUBE_OEMBED_URL = env("YOUTUBE_OEMBED_URL", "https://www.youtube.com/oembed")
YOUTUBE_TIMEOUT_SECONDS = 3
# The channel whose new uploads become home Shorts (issue 211); empty switches the sync off.
YOUTUBE_CHANNEL_ID = env("YOUTUBE_CHANNEL_ID", "UCnaM_8rEMk751BPnEW4Jifw")
YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml"

# sandcorp-metrics (metrics.sandcorp.co.kr) visit counts (#81). METRICS_SNIPPET_URL is the counting
# script the public pages load (empty = not loaded); METRICS_API_URL the public totals the home
# page shows (empty = no numbers). The adapter caches 60 seconds in django_cache.
METRICS_SNIPPET_URL = env("METRICS_SNIPPET_URL", "")
METRICS_SITE_KEY = env("METRICS_SITE_KEY", "sandcorp")
METRICS_API_URL = env("METRICS_API_URL", "https://metrics.sandcorp.co.kr/api/stats")
METRICS_TIMEOUT_SECONDS = 3

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# Django admin lives on a hard-to-guess path in production.
# Absolute-URL base for sitemap.xml and robots.txt (they have no request host to trust).
# Search-engine ownership meta (#111): empty -> no tag.
GOOGLE_SITE_VERIFICATION = env("GOOGLE_SITE_VERIFICATION").strip()
# 네이버 서치어드바이저 소유확인 코드는 공개 코드라 기본값으로 둔다(#143). 빈 값을 주면 끈다.
NAVER_SITE_VERIFICATION = env(
    "NAVER_SITE_VERIFICATION", "4768f013dc8c37a24a2b074f7037a60af45c9455"
).strip()
SITE_URL = env("SITE_URL", "https://sandcorp.co.kr").rstrip("/")
# sandcorp-auth: the owner's username, the only `sub` this site accepts (empty -> /mcp is 503).
AUTH_OWNER_SUB = env("AUTH_OWNER_SUB").strip()
ADMIN_PATH = env("DJANGO_ADMIN_PATH", "admin/").strip("/") + "/"
# sandcorp-auth confidential client for the admin login (oauth/admin_login.py). Registered at
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
# A blog draft's preview link (/preview/blog/<token>, #147) lives as long.
BLOG_PREVIEW_MAX_AGE = PROPOSAL_PREVIEW_MAX_AGE
# A tip draft's preview link (/preview/tips/<token>, issue 203) too.
TIP_PREVIEW_MAX_AGE = BLOG_PREVIEW_MAX_AGE
# A service page's preview link (/preview/services/<token>, issue 215) too.
SERVICE_PREVIEW_MAX_AGE = BLOG_PREVIEW_MAX_AGE
# The PDF renderer opens a print page within seconds of being handed the link.
PROPOSAL_PRINT_MAX_AGE = 10 * 60
# The customer page (/p/<slug>): a right code opens a seven-day session for that proposal; five
# wrong ones from one IP block that IP for fifteen minutes, right code or not.
PROPOSAL_SESSION_MAX_AGE = 7 * 24 * 60 * 60
PROPOSAL_CODE_MAX_FAILURES = 5
PROPOSAL_CODE_BLOCK_SECONDS = 15 * 60

# Revision PDFs (#40): the worker (`manage.py pdf_worker`) hands the renderer the print page of a
# revision at PDF_PRINT_BASE_URL (web as seen from the compose network). The renderer is the
# project's own browserless container; without a token every PDF fails and the site still works.
PDF_RENDERER_URL = env("PDF_RENDERER_URL", "http://renderer:3000")
PDF_RENDERER_TOKEN = env("PDF_RENDERER_TOKEN")
PDF_PRINT_BASE_URL = env("PDF_PRINT_BASE_URL", "http://web:8000")
# browserless gives up on each step (load, print-ready wait) after this long.
PDF_RENDER_TIMEOUT_SECONDS = 60
# A job is tried this many times (failures wait 1, 2, ... minutes) before it stays failed.
PDF_JOB_MAX_ATTEMPTS = 3
# One render takes at most about 2 x timeout + 10s; a job running longer than this lost its worker.
PDF_JOB_STALE_SECONDS = 5 * 60
