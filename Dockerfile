FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

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


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Runtime shared libraries only, matching the build-time headers above.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-2.5-0 \
    libsasl2-2 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app /app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
