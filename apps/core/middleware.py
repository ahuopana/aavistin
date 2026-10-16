from django.conf import settings
from django.http import HttpResponse


class RequestSizeLimitMiddleware:
    """Reject requests whose declared body exceeds ``MAX_REQUEST_BYTES`` with 413,
    before Django reads or spools the body (docs/adr/0049). Reverse proxies should
    enforce the same cap (nginx ``client_max_body_size``)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = settings.MAX_REQUEST_BYTES
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if limit and length > limit:
            return HttpResponse("Request body too large.", status=413, content_type="text/plain")
        return self.get_response(request)
