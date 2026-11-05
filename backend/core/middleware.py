from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from services import runtime_settings


class RuntimeSettingsMiddleware:
    """One request reads the shared runtime-settings snapshot at most once (#233)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        with runtime_settings.request_scope():
            return self.get_response(request)
