from django import template

register = template.Library()


@register.filter
def labels(entries):
    """Comma-separated entry labels, for a cell's tooltip."""
    return ", ".join(e.label for e in entries)


@register.filter
def days_text(days):
    if days is None:
        return "approval date unknown"
    if days == 0:
        return "approved today"
    return f"approved {days} day{'s' if days != 1 else ''} ago"
