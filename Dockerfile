FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# build-essential + libldap2-dev/libsasl2-dev: python-ldap (django-auth-ldap)
# has no prebuilt wheel and compiles against these headers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libldap2-dev \
    libsasl2-dev \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime shared libraries only, matching the build-time headers above.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-2.5-0 \
    libsasl2-2 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The venv lives at /opt/venv, outside /app, on purpose: local dev
# (docker-compose.yml) bind-mounts the project root over /app for live
# code reload. A venv stored inside /app would be shadowed by whatever
# the host checkout has there — including a host-built .venv, if one
# exists, which is a different platform/interpreter than this container
# and can't just be recompiled at runtime (python-ldap needs a compiler
# and headers this stage doesn't have). Keeping the venv at /opt/venv
# means the bind mount never touches it, so it's always exactly what was
# built here — no runtime uv/gcc needed at all.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
