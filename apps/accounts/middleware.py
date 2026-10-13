from .prefs import activate, deactivate, get_profile


class ProfileMiddleware:
    """Apply the signed-in user's time zone and date style for the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.profile = get_profile(request.user)
        token = activate(request.profile)
        try:
            return self.get_response(request)
        finally:
            deactivate(token)
