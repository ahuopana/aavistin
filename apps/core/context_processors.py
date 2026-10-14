from apps.products.services import COMPLIANCE_HINT

from .navigation import is_approver_anywhere


def navigation(request):
    """Whether to show the Approvals link in the main navigation, and what
    the Compliance ratio measures (shown wherever the ratio is)."""
    user = getattr(request, "user", None)
    return {
        "nav_is_approver": bool(user) and is_approver_anywhere(user),
        "compliance_hint": COMPLIANCE_HINT,
    }
