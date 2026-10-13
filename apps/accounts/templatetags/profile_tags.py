from django import template
from django.urls import reverse

from .. import avatars, prefs

register = template.Library()


@register.filter
def userdate(value):
    """A date in the viewer's locale or ISO style (docs/adr/0033)."""
    return prefs.format_date(value)


@register.filter
def userdatetime(value):
    """A date and time in the viewer's time zone, locale and date style."""
    return prefs.format_datetime(value)


@register.inclusion_tag("accounts/_avatar.html")
def avatar(user, size=32):
    profile = prefs.get_profile(user) if user.is_authenticated else None
    url = ""
    if profile and profile.avatar and avatars.uploads_enabled():
        stamp = int(profile.avatar_updated_at.timestamp()) if profile.avatar_updated_at else 0
        url = f"{reverse('accounts:avatar', args=[user.pk])}?v={stamp}"
    return {
        "url": url,
        "initials": avatars.initials(user),
        "hue": avatars.hue(user),
        "size": size,
        "name": user.get_full_name() or user.get_username(),
    }
