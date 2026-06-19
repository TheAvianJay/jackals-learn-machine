import os
from django.http import JsonResponse

EXEMPT_PATHS = [
    "/api/auth/token/",
    "/api/auth/token/refresh/",
]

class AppSecretMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Exempt auth endpoints and all media files
        if request.path in EXEMPT_PATHS or request.path.startswith("/media/"):
            return self.get_response(request)

        secret = os.environ.get("APP_SECRET")
        incoming = request.headers.get("X-App-Secret")

        if not incoming or incoming != secret:
            return JsonResponse({"detail": "Forbidden"}, status=403)

        return self.get_response(request)