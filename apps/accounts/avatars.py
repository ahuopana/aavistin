"""Avatar storage: uploads are re-encoded, so only our own PNG ever gets served.

Uploads are opt-in (``settings.UPLOADS_ENABLED``, docs/adr/0032); without
``MEDIA_ROOT`` the profile shows initials only.
"""

import io
import re
import zlib

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PIXELS = 4096 * 4096
AVATAR_SIZE = 256
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}


class AvatarError(Exception):
    pass


def uploads_enabled():
    return settings.UPLOADS_ENABLED


def _storage_name(user):
    return f"avatars/{user.pk}.png"


def process_avatar(upload):
    """Return PNG bytes of a square AVATAR_SIZE image; raises AvatarError."""
    if upload.size > MAX_UPLOAD_BYTES:
        raise AvatarError("The image is larger than 2 MB.")
    try:
        with Image.open(upload) as image:
            if image.format not in ALLOWED_FORMATS:
                raise AvatarError("Use a PNG, JPEG, WebP or GIF image.")
            if image.width * image.height > MAX_SOURCE_PIXELS:
                raise AvatarError("The image has too many pixels.")
            image = ImageOps.exif_transpose(image.convert("RGBA"))
            image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise AvatarError("That file is not a readable image.") from exc
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)  # no EXIF or other metadata is written
    return out.getvalue()


def set_avatar(profile, upload):
    if not uploads_enabled():
        raise AvatarError("Avatar uploads are not enabled on this server.")
    data = process_avatar(upload)
    name = _storage_name(profile.user)
    if default_storage.exists(name):
        default_storage.delete(name)
    profile.avatar = default_storage.save(name, ContentFile(data))
    profile.avatar_updated_at = timezone.now()
    profile.save(update_fields=["avatar", "avatar_updated_at"])


def clear_avatar(profile):
    if profile.avatar and uploads_enabled() and default_storage.exists(profile.avatar):
        default_storage.delete(profile.avatar)
    profile.avatar = ""
    profile.avatar_updated_at = None
    profile.save(update_fields=["avatar", "avatar_updated_at"])


def initials(user):
    words = f"{user.first_name} {user.last_name}".split()
    if not words:
        words = re.split(r"[\W_]+", user.get_username())
    letters = [w[0] for w in words if w][:2]
    return "".join(letters).upper() or "?"


def hue(user):
    """Stable colour per person for the initials badge."""
    return zlib.crc32(user.get_username().encode()) % 360
