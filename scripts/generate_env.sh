#!/bin/sh
# Bootstraps .env for local development, with a random DJANGO_SECRET_KEY.
# Run by each app service's command in docker-compose.yml before it
# starts. Safe to re-run: leaves an existing .env untouched, so it never
# overwrites values a developer has since customised. Uses a lock
# directory because web/worker/scheduler all run this concurrently on
# `docker compose up`.
set -eu

cd "$(dirname "$0")/.."

if [ -f .env ]; then
    echo ".env already exists, leaving it untouched."
    exit 0
fi

lock_dir=.env.lock
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

i=0
while ! mkdir "$lock_dir" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 50 ]; then
        echo "Timed out waiting for the .env generation lock." >&2
        exit 1
    fi
    sleep 0.2
done

if [ -f .env ]; then
    echo ".env already exists, leaving it untouched."
    exit 0
fi

tmp=$(mktemp .env.XXXXXX)
cp .env.example "$tmp"
secret_key=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${secret_key}|" "$tmp"
mv "$tmp" .env
echo "Generated .env with a random local DJANGO_SECRET_KEY."
