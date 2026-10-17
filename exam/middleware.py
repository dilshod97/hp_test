import hashlib

from django.conf import settings
from django.shortcuts import render


class SafeExamBrowserMiddleware:
    """Nomzod sahifalari (/exam/) faqat Safe Exam Browser orqali ochilishini ta'minlaydi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/exam/") and not self.is_allowed(request):
            return render(request, "exam/candidate/seb_required.html", status=403)
        return self.get_response(request)

    def is_allowed(self, request):
        if settings.SEB_CONFIG_KEYS:
            received = request.headers.get("X-SafeExamBrowser-ConfigKeyHash", "").lower()
            url = request.build_absolute_uri()
            return any(
                hashlib.sha256((url + key).encode()).hexdigest() == received
                for key in settings.SEB_CONFIG_KEYS
            )
        if settings.REQUIRE_SEB:
            return "SEB" in request.headers.get("User-Agent", "")
        return True
