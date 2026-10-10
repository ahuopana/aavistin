from django import template

register = template.Library()


@register.filter
def choice_label(value):
    """Display form of a choice id: "hardware_with_software" -> "Hardware with software".

    Choices in packages are plain ids with no separate label, so this is
    display-only; the stored answer and the rules keep using the id.
    """
    if not isinstance(value, str) or not value:
        return value
    text = value.replace("_", " ")
    return text[0].upper() + text[1:]
