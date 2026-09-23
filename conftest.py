import pytest


@pytest.fixture(autouse=True)
def _eager_tasks(settings):
    """Run @task-decorated functions synchronously — no worker needed in tests."""
    settings.TASKS = {
        "default": {"BACKEND": "django_tasks.backends.immediate.ImmediateBackend"},
    }
