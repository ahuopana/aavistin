from datetime import date, datetime

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def report_time(value):
    """ "14 October 2026, 15:42 UTC" from a stored ISO timestamp."""
    if not value:
        return ""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    moment = timezone.localtime(moment)
    return f"{moment.day} {moment:%B %Y, %H:%M} {moment.tzname()}"


@register.filter
def report_date(value):
    """ "14 October 2026" from a stored ISO date."""
    if not value:
        return ""
    day = date.fromisoformat(value[:10]) if isinstance(value, str) else value
    return f"{day.day} {day:%B %Y}"
