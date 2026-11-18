"""The ninja API. Endpoints stay thin: they validate input and call the service layer."""

from typing import Literal

from django.http import HttpRequest
from ninja import NinjaAPI, Schema, Status
from sandcorp_authkit.django import install_bearer_errors
from sandcorp_authkit.tokens import AccessToken

from core import health as checks
from core.admin_api import install_service_errors
from core.admin_api import router as admin_router
from core.inquiry_api import router as inquiry_router
from oauth.auth import admin_auth

api = NinjaAPI(title="Sandcorp portfolio API", docs_url=None)
install_bearer_errors(api)
install_service_errors(api)
api.add_router("/admin", admin_router)
api.add_router("/inquiries", inquiry_router)


class Health(Schema):
    status: str
    failed: list[str] | None = None


@api.get("/health", response={200: Health, 503: Health}, auth=None, exclude_none=True)
def health(request: HttpRequest, scope: Literal["all", "ready"] = "all") -> Status[Health]:
    """What the service leans on (core/health.py, issue 19): Gatus watches the full scope; the
    container healthcheck and the deploy wait use `?scope=ready` (database only)."""
    failed = checks.failed_checks(checks.READY_CHECKS if scope == "ready" else None)
    if failed:
        return Status(503, Health(status="error", failed=failed))
    return Status(200, Health(status="ok"))


class Whoami(Schema):
    sub: str
    client_id: str
    scopes: list[str]
    expires_at: int


@api.get("/admin/whoami", response=Whoami, auth=admin_auth)
def admin_whoami(request: HttpRequest) -> Whoami:
    """The sandcorp-auth token's identity; the admin API's bearer check in its smallest form."""
    token = request.auth  # type: ignore[attr-defined]  # set by ninja from admin_auth
    assert isinstance(token, AccessToken)
    return Whoami(
        sub=token.sub, client_id=token.client_id, scopes=sorted(token.scopes), expires_at=token.exp
    )
