def profile(request):
    """Expose the profile so base.html can render the saved theme server-side."""
    return {"profile": getattr(request, "profile", None)}
