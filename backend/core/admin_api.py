"""The owner's content routes under /api/admin: the same service functions the MCP tools call.

Every route needs a sandcorp-auth bearer token with scope `admin`. A refused write answers
422 `{"detail": "...", "errors": [{"path": ..., "reason": ...}]}` and saves nothing.
"""

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI, Router, Status
from pydantic import BaseModel, ConfigDict

from oauth.auth import admin_auth
from services import portfolio, profile
from services.errors import Conflict, NotFound, RateLimited, Rejected, ServiceError

router = Router(auth=admin_auth, tags=["admin"])


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slugs: list[str]


class Visibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_public: bool


@router.get("/profile", response=profile.Profile)
def read_profile(request: HttpRequest) -> profile.Profile:
    return profile.get_profile()


@router.patch("/profile", response=profile.Profile)
def patch_profile(request: HttpRequest, patch: profile.ProfilePatch) -> profile.Profile:
    return profile.update_profile(patch)


@router.get("/portfolio", response=list[portfolio.ItemSummary])
def list_portfolio(request: HttpRequest) -> list[portfolio.ItemSummary]:
    return portfolio.list_summaries()


@router.post("/portfolio", response={201: portfolio.ItemAdmin})
def create_portfolio(request: HttpRequest, new: portfolio.NewItem) -> Status[portfolio.ItemAdmin]:
    return Status(201, portfolio.create_item(new))


@router.put("/portfolio/order", response=list[portfolio.ItemSummary])
def reorder_portfolio(request: HttpRequest, order: Order) -> list[portfolio.ItemSummary]:
    return portfolio.reorder(order.slugs)


@router.get("/portfolio/{slug}", response=portfolio.ItemAdmin)
def read_portfolio(request: HttpRequest, slug: str) -> portfolio.ItemAdmin:
    return portfolio.read_item(slug)


@router.patch("/portfolio/{slug}", response=portfolio.ItemAdmin)
def patch_portfolio(
    request: HttpRequest, slug: str, patch: portfolio.ItemPatch
) -> portfolio.ItemAdmin:
    return portfolio.update_item(slug, patch)


@router.put("/portfolio/{slug}/visibility", response=portfolio.ItemAdmin)
def set_portfolio_visibility(
    request: HttpRequest, slug: str, visibility: Visibility
) -> portfolio.ItemAdmin:
    return portfolio.set_visibility(slug, visibility.is_public)


def install_service_errors(api: NinjaAPI) -> None:
    """Service failures become HTTP answers: 404, 409, 422 (with block paths), 429."""

    def handle(request: HttpRequest, exc: ServiceError | type[ServiceError]) -> HttpResponse:
        if isinstance(exc, NotFound):
            return api.create_response(request, {"detail": str(exc)}, status=404)
        if isinstance(exc, Conflict):
            return api.create_response(request, {"detail": str(exc)}, status=409)
        if isinstance(exc, RateLimited):
            return api.create_response(request, {"detail": str(exc)}, status=429)
        if isinstance(exc, Rejected):
            body = {
                "detail": "저장하지 않았습니다",
                "errors": [{"path": e.path, "reason": e.reason} for e in exc.errors],
            }
            return api.create_response(request, body, status=422)
        raise TypeError(f"not a service error: {exc!r}")

    for error in (NotFound, Conflict, RateLimited, Rejected):
        api.add_exception_handler(error, handle)
