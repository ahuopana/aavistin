from .navigation import is_approver_anywhere


def navigation(request):
    """Whether to show the Approvals link in the main navigation."""
    user = getattr(request, "user", None)
    return {"nav_is_approver": bool(user) and is_approver_anywhere(user)}
