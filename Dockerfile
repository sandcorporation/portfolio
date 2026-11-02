# syntax=docker/dockerfile:1
# One image: the Vite build is baked in and collected into Django's static files (served by whitenoise).
# Built off-host as linux/arm64 by Jenkins (macos, else home; jenkins-shared sandcorpDeploy), oracle only pulls; also builds on x86 for local checks.

FROM node:24-alpine AS frontend
RUN npm install -g pnpm@11.25.0
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# Renderer tests import the shared example document; `tsc` in the build type-checks them too.
COPY fixtures/ /app/fixtures/
RUN pnpm build

# Python deps. mysqlclient has no Linux wheels, so it compiles here against the MariaDB
# Connector/C headers (`default-libmysqlclient-dev`); the runtime only needs the shared library.
FROM python:3.14-slim AS pydeps
# git + openssh-client: sandcorp-authkit is a private git dependency fetched over ssh.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev git openssh-client \
 && rm -rf /var/lib/apt/lists/*
# The deploy key never enters the image: BuildKit forwards the agent (`--mount=type=ssh`) for the
# one RUN below. known_hosts lives in this build stage only; the runtime stage copies /opt/venv.
RUN mkdir -p -m 0700 /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=ssh uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim AS runtime
# libmariadb3: the client library mysqlclient links to.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmariadb3 \
 && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend
COPY --from=pydeps /opt/venv /opt/venv
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
 && useradd --uid 1000 --no-create-home app
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-2} --timeout 30 --access-logfile -"]
