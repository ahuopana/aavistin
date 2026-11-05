from django import template

register = template.Library()


@register.filter
def labels(entries):
    """Comma-separated entry labels, for a cell's tooltip. Entries rolled up
    across products carry ``product_name`` and are prefixed with it."""
    return ", ".join(
        f"{e.product_name}: {e.label}" if getattr(e, "product_name", None) else e.label
        for e in entries
    )


@register.filter
def days_text(days):
    if days is None:
        return "approval date unknown"
    if days == 0:
        return "approved today"
    return f"approved {days} day{'s' if days != 1 else ''} ago"
