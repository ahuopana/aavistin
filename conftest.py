import pytest


@pytest.fixture(autouse=True)
def _eager_tasks(settings):
    """Run @task-decorated functions synchronously — no worker needed in tests."""
    settings.TASKS = {
        "default": {"BACKEND": "django_tasks.backends.immediate.ImmediateBackend"},
    }


@pytest.fixture(autouse=True)
def _uploads_enabled(settings, tmp_path):
    """Uploads are opt-in in production; tests get a throwaway MEDIA_ROOT."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.UPLOADS_ENABLED = True


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """The hashed manifest storage needs `collectstatic` first; tests don't run it."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
