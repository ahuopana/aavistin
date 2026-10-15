"""The production security settings, exercised in a clean subprocess so the real
``config.settings`` import path (environment parsing and the fail-closed
secret-key check) is what runs."""

import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_PROBE = (
    "import json, django.conf as c;"
    "from config import settings as s;"
    "print(json.dumps({k: getattr(s, k, None) for k in "
    "['SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE','SECURE_HSTS_SECONDS',"
    "'SECURE_SSL_REDIRECT','SECURE_PROXY_SSL_HEADER','SESSION_COOKIE_AGE',"
    "'CSRF_TRUSTED_ORIGINS']}))"
)


def _load_settings(**env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DEBUG"))}
    for name in ("TRUST_X_FORWARDED_PROTO", "SESSION_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
        base.pop(name, None)
    base.update(env)
    base["DJANGO_SETTINGS_MODULE"] = "config.settings"
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(BASE_DIR)!r});{_PROBE}",
        ],
        capture_output=True,
        text=True,
        env=base,
        cwd=BASE_DIR,
    )


def test_refuses_to_start_without_a_secret_key_outside_debug():
    result = _load_settings(DEBUG="False", DJANGO_SECRET_KEY="")
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_refuses_placeholder_secret_key_outside_debug():
    result = _load_settings(DEBUG="False", DJANGO_SECRET_KEY="change-me-to-a-random-value")
    assert result.returncode != 0


def test_debug_may_use_the_default_key_and_stays_on_http():
    result = _load_settings(DEBUG="True")
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["SESSION_COOKIE_SECURE"] is False
    assert values["SECURE_HSTS_SECONDS"] == 0


def test_production_defaults_are_secure():
    result = _load_settings(DEBUG="False", DJANGO_SECRET_KEY="x" * 64)
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["CSRF_COOKIE_SECURE"] is True
    assert values["SECURE_HSTS_SECONDS"] > 0
    assert values["SESSION_COOKIE_AGE"] == 12 * 60 * 60
    # Not trusted unless the operator says a proxy sets it.
    assert values["SECURE_PROXY_SSL_HEADER"] is None


def test_forwarded_proto_is_opt_in():
    result = _load_settings(
        DEBUG="False", DJANGO_SECRET_KEY="x" * 64, TRUST_X_FORWARDED_PROTO="True"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["SECURE_PROXY_SSL_HEADER"] == [
        "HTTP_X_FORWARDED_PROTO",
        "https",
    ]
