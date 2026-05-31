import os
from django.http import JsonResponse

EXEMPT_PATHS = ["/api/auth/token/", "/api/auth/token/refresh/"]

class AppSecretMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Don't read the secret here — env may not be loaded yet

    def __call__(self, request):
        if request.path in EXEMPT_PATHS:
            return self.get_response(request)

        secret = os.environ.get("APP_SECRET")  # 👈 read it here instead
        incoming = request.headers.get("X-App-Secret")

        if not incoming or incoming != secret:
            return JsonResponse({"detail": "Forbidden"}, status=403)

        return self.get_response(request)