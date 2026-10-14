from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """``mapping[key]`` or None, for lookups by a variable key in templates."""
    if not mapping:
        return None
    return mapping.get(key)
