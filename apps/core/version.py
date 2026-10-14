"""Which Aavistin build is running, for reports and support.

A tagged release gives its tag; otherwise the short commit id. Container
images have no git checkout, so the Dockerfile bakes ``AAVISTIN_VERSION``
(from a build argument) into the environment, which wins when set.
"""

import os
import subprocess
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def aavistin_version() -> str:
    configured = os.environ.get("AAVISTIN_VERSION", "").strip()
    if configured:
        return configured
    try:
        # --tags: any tag; --always: the short commit id when no tag is reachable;
        # --exact-match is not used so a build after a tag reads "v1.2-3-gabc1234".
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
