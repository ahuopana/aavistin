"""Resolving and applying a user's display preferences."""

import zoneinfo
from contextvars import ContextVar
from datetime import date, datetime

from django.conf import settings
from django.utils import dateformat, formats, timezone

from .models import DateStyle, UserProfile

ISO_DATE = "Y-m-d"
ISO_DATETIME = "Y-m-d H:i"

_current_profile: ContextVar[UserProfile | None] = ContextVar("current_profile", default=None)


def get_profile(user):
    """Return the user's profile, creating it on first use."""
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile


def time_zone_choices():
    names = sorted(zoneinfo.available_timezones() - {"localtime"})
    return [
        (n, n.replace("_", " ")) for n in names if not n.startswith(("Etc/", "posix/", "right/"))
    ]


def effective_time_zone(profile):
    name = (profile.time_zone if profile else "") or settings.TIME_ZONE
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return zoneinfo.ZoneInfo(settings.TIME_ZONE)


def effective_locale(profile):
    return (profile.locale if profile else "") or settings.LANGUAGE_CODE


def activate(profile):
    """Make `profile` current for this request: time zone and date formatting."""
    timezone.activate(effective_time_zone(profile))
    return _current_profile.set(profile)


def deactivate(token):
    timezone.deactivate()
    _current_profile.reset(token)


def format_date(value, profile=None):
    return _format(value, profile or _current_profile.get(), "SHORT_DATE_FORMAT", ISO_DATE)


def format_datetime(value, profile=None):
    return _format(value, profile or _current_profile.get(), "SHORT_DATETIME_FORMAT", ISO_DATETIME)


def _format(value, profile, locale_format, iso_format):
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value, effective_time_zone(profile))
    elif not isinstance(value, date):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        # A plain date has no time of day to show.
        locale_format = "SHORT_DATE_FORMAT"
        iso_format = ISO_DATE
    if profile is not None and profile.date_style == DateStyle.ISO:
        return dateformat.format(value, iso_format)
    fmt = formats.get_format(locale_format, lang=effective_locale(profile), use_l10n=True)
    return dateformat.format(value, fmt)
