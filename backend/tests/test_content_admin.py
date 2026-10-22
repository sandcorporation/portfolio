"""Owner content writes through three doors that must behave the same: the service functions,
the MCP tools (`/mcp` tools/call) and the ninja admin API (`/api/admin/...`)."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from xml.etree import ElementTree

import pytest
from django.test import Client

from adapters.fake_jwks import FakeAuthServer
from content.models import Media, PortfolioItem
from documents.validation import JSON
from services import portfolio as portfolio_service
from services import profile as profile_service
from services.errors import ServiceError
from tests.test_mcp import McpClient
from tests.test_portfolio import page_data

pytestmark = pytest.mark.django_db

type Args = dict[str, Any]  # Any: test payloads are arbitrary JSON


@dataclass
class Outcome:
    ok: bool
    data: Args = field(default_factory=dict)
    error: str = ""


def _items(rows: list[Any]) -> Args:
    return {"items": rows}


class Door(Protocol):
    """One way in. Every method returns the same Outcome shape."""

    def get_profile(self) -> Outcome: ...
    def update_profile(self, args: Args) -> Outcome: ...
    def list_portfolio(self) -> Outcome: ...
    def get_portfolio(self, slug: str) -> Outcome: ...
    def create_portfolio(self, args: Args) -> Outcome: ...
    def update_portfolio(self, slug: str, args: Args) -> Outcome: ...
    def reorder_portfolio(self, slugs: list[str]) -> Outcome: ...
    def set_visibility(self, slug: str, is_public: bool) -> Outcome: ...


class ServiceDoor:
    def run(self, call: Callable[[], Any]) -> Outcome:
        try:
            result = call()
        except ServiceError as exc:
            return Outcome(False, error=str(exc))
        if isinstance(result, list):
            return Outcome(True, _items([r.model_dump(mode="json") for r in result]))
        return Outcome(True, result.model_dump(mode="json"))

    def get_profile(self) -> Outcome:
        return self.run(profile_service.get_profile)

    def update_profile(self, args: Args) -> Outcome:
        return self.run(
            lambda: profile_service.update_profile(profile_service.ProfilePatch(**args))
        )

    def list_portfolio(self) -> Outcome:
        return self.run(portfolio_service.list_summaries)

    def get_portfolio(self, slug: str) -> Outcome:
        return self.run(lambda: portfolio_service.read_item(slug))

    def create_portfolio(self, args: Args) -> Outcome:
        return self.run(lambda: portfolio_service.create_item(portfolio_service.NewItem(**args)))

    def update_portfolio(self, slug: str, args: Args) -> Outcome:
        patch = portfolio_service.ItemPatch(**args)
        return self.run(lambda: portfolio_service.update_item(slug, patch))

    def reorder_portfolio(self, slugs: list[str]) -> Outcome:
        return self.run(lambda: portfolio_service.reorder(slugs))

    def set_visibility(self, slug: str, is_public: bool) -> Outcome:
        return self.run(lambda: portfolio_service.set_visibility(slug, is_public))


class McpDoor:
    def __init__(self, mcp: McpClient) -> None:
        self.mcp = mcp

    def call(self, name: str, args: Args) -> Outcome:
        result = self.mcp.call_tool(name, args)
        if result["isError"]:
            return Outcome(False, error=json.dumps(result["content"], ensure_ascii=False))
        data = result["structuredContent"]
        assert isinstance(data, dict)
        return Outcome(True, data)

    def get_profile(self) -> Outcome:
        return self.call("get_profile", {})

    def update_profile(self, args: Args) -> Outcome:
        return self.call("update_profile", args)

    def list_portfolio(self) -> Outcome:
        return self.call("list_portfolio", {})

    def get_portfolio(self, slug: str) -> Outcome:
        return self.call("get_portfolio", {"slug": slug})

    def create_portfolio(self, args: Args) -> Outcome:
        return self.call("create_portfolio", args)

    def update_portfolio(self, slug: str, args: Args) -> Outcome:
        return self.call("update_portfolio", {"slug": slug, **args})

    def reorder_portfolio(self, slugs: list[str]) -> Outcome:
        return self.call("reorder_portfolio", {"slugs": slugs})

    def set_visibility(self, slug: str, is_public: bool) -> Outcome:
        return self.call("set_portfolio_visibility", {"slug": slug, "is_public": is_public})


class ApiDoor:
    def __init__(self, client: Client, auth_server: FakeAuthServer) -> None:
        self.client = client
        self.headers = auth_server.bearer()

    def call(self, method: str, path: str, body: Args | None = None) -> Outcome:
        send = getattr(self.client, method)
        response = send(
            f"/api/admin{path}",
            json.dumps(body) if body is not None else None,
            content_type="application/json",
            headers=self.headers,
        )
        data = response.json()
        if response.status_code >= 400:
            return Outcome(False, error=json.dumps(data, ensure_ascii=False))
        return Outcome(True, _items(data) if isinstance(data, list) else data)

    def get_profile(self) -> Outcome:
        return self.call("get", "/profile")

    def update_profile(self, args: Args) -> Outcome:
        return self.call("patch", "/profile", args)

    def list_portfolio(self) -> Outcome:
        return self.call("get", "/portfolio")

    def get_portfolio(self, slug: str) -> Outcome:
        return self.call("get", f"/portfolio/{slug}")

    def create_portfolio(self, args: Args) -> Outcome:
        return self.call("post", "/portfolio", args)

    def update_portfolio(self, slug: str, args: Args) -> Outcome:
        return self.call("patch", f"/portfolio/{slug}", args)

    def reorder_portfolio(self, slugs: list[str]) -> Outcome:
        return self.call("put", "/portfolio/order", {"slugs": slugs})

    def set_visibility(self, slug: str, is_public: bool) -> Outcome:
        return self.call("put", f"/portfolio/{slug}/visibility", {"is_public": is_public})


@pytest.fixture(params=["service", "mcp", "api"])
def door(request: pytest.FixtureRequest, client: Client, auth_server: FakeAuthServer) -> Door:
    if request.param == "service":
        return ServiceDoor()
    if request.param == "mcp":
        return McpDoor(McpClient(client, auth_server))
    return ApiDoor(client, auth_server)


def doc(*blocks: JSON) -> Args:
    return {"tabs": [{"id": "main", "title": "소개", "blocks": list(blocks)}]}


TEXT: JSON = {"id": "intro", "type": "markdown", "body": "안녕하세요"}


def sitemap_paths(client: Client) -> list[str]:
    root = ElementTree.fromstring(client.get("/sitemap.xml").content)
    return [e.text or "" for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]


def home_slugs(client: Client) -> list[str]:
    return [card["slug"] for card in page_data(client.get("/").content.decode())["portfolio"]]


def test_created_item_is_hidden_until_published_then_shows_on_home_and_sitemap(
    door: Door, client: Client
) -> None:
    created = door.create_portfolio(
        {"slug": "ganadatrade", "title": "GanadaTrade", "tags": ["웹", " 제안 "], "body": doc(TEXT)}
    )
    assert created.ok, created.error
    assert created.data["is_public"] is False
    assert created.data["tags"] == ["웹", "제안"]
    assert created.data["url"] == "/work/ganadatrade"
    assert home_slugs(client) == []
    assert client.get("/work/ganadatrade").status_code == 404

    shown = door.set_visibility("ganadatrade", True)
    assert shown.ok and shown.data["is_public"] is True
    assert home_slugs(client) == ["ganadatrade"]
    assert "https://sandcorp.co.kr/work/ganadatrade" in sitemap_paths(client)
    assert client.get("/work/ganadatrade").status_code == 200

    hidden = door.set_visibility("ganadatrade", False)
    assert hidden.ok and hidden.data["is_public"] is False
    assert home_slugs(client) == []
    assert "https://sandcorp.co.kr/work/ganadatrade" not in sitemap_paths(client)


def test_create_public_directly_appends_after_existing_items(door: Door, client: Client) -> None:
    assert door.create_portfolio({"slug": "a", "title": "A", "is_public": True}).ok
    assert door.create_portfolio({"slug": "b", "title": "B", "is_public": True}).ok
    assert home_slugs(client) == ["a", "b"]


def test_list_shows_hidden_items_with_their_flag_and_get_returns_the_body(door: Door) -> None:
    door.create_portfolio({"slug": "a", "title": "A", "is_public": True})
    door.create_portfolio({"slug": "b", "title": "B", "body": doc(TEXT)})

    listed = door.list_portfolio().data["items"]
    assert [(row["slug"], row["is_public"]) for row in listed] == [("a", True), ("b", False)]
    assert "body" not in listed[0]

    got = door.get_portfolio("b")
    assert got.ok and got.data["body"]["tabs"][0]["blocks"][0]["body"] == "안녕하세요"
    assert not door.get_portfolio("nope").ok


def test_update_changes_only_given_fields_and_reaches_the_public_page(
    door: Door, client: Client
) -> None:
    door.create_portfolio(
        {"slug": "a", "title": "Old", "summary": "keep", "is_public": True, "body": doc(TEXT)}
    )

    updated = door.update_portfolio(
        "a", {"title": "New", "body": doc({"id": "intro", "type": "markdown", "body": "바뀜"})}
    )

    assert updated.ok, updated.error
    assert updated.data["title"] == "New"
    assert updated.data["summary"] == "keep"
    detail = page_data(client.get("/work/a").content.decode())
    assert detail["body"]["tabs"][0]["blocks"][0]["body"] == "바뀜"
    assert not door.update_portfolio("missing", {"title": "x"}).ok


def test_cover_must_be_a_finished_public_upload_and_null_removes_it(door: Door) -> None:
    from django.utils import timezone

    def media(**kw: Any) -> Media:
        return Media.objects.create(
            object_key=f"k-{Media.objects.count()}",
            content_type="image/png",
            size=1,
            original_filename="x.png",
            **kw,
        )

    good = media(uploaded_at=timezone.now())
    unfinished = media()
    private = media(uploaded_at=timezone.now(), is_public=False)

    for bad in (unfinished.pk, private.pk, 9999):
        refused = door.create_portfolio({"slug": "x", "title": "X", "cover_media_id": bad})
        assert not refused.ok and "cover_media_id" in refused.error
    assert not PortfolioItem.objects.exists()

    made = door.create_portfolio({"slug": "x", "title": "X", "cover_media_id": good.pk})
    assert made.ok and made.data["cover_media_id"] == good.pk
    assert door.update_portfolio("x", {"cover_media_id": None}).data["cover_media_id"] is None


def test_invalid_document_is_not_saved_and_names_the_block_path(door: Door) -> None:
    door.create_portfolio({"slug": "a", "title": "A", "is_public": True, "body": doc(TEXT)})
    bad = doc(TEXT, {"id": "bad", "type": "no-such-block"})

    created = door.create_portfolio({"slug": "b", "title": "B", "body": bad})
    updated = door.update_portfolio("a", {"body": bad})

    for outcome in (created, updated):
        assert not outcome.ok
        assert "tabs[0].blocks[1]" in outcome.error
    assert not PortfolioItem.objects.filter(slug="b").exists()
    stored = PortfolioItem.objects.get(slug="a").body
    assert stored["tabs"][0]["blocks"][0]["body"] == "안녕하세요"
    assert len(stored["tabs"][0]["blocks"]) == 1


def test_duplicate_slug_and_bad_tags_are_refused(door: Door) -> None:
    assert door.create_portfolio({"slug": "a", "title": "A"}).ok
    assert not door.create_portfolio({"slug": "a", "title": "again"}).ok
    comma = door.create_portfolio({"slug": "b", "title": "B", "tags": ["a,b"]})
    assert not comma.ok and "tags" in comma.error
    assert PortfolioItem.objects.count() == 1


def test_reorder_sets_the_public_order_and_needs_every_slug(door: Door, client: Client) -> None:
    for slug in ("a", "b", "c"):
        door.create_portfolio({"slug": slug, "title": slug, "is_public": slug != "b"})

    reordered = door.reorder_portfolio(["c", "b", "a"])

    assert reordered.ok, reordered.error
    assert [row["slug"] for row in reordered.data["items"]] == ["c", "b", "a"]
    assert home_slugs(client) == ["c", "a"]
    for wrong in (["a", "b"], ["a", "b", "c", "d"], ["a", "a", "b", "c"]):
        refused = door.reorder_portfolio(wrong)
        assert not refused.ok and "slugs" in refused.error
    assert [i["slug"] for i in door.list_portfolio().data["items"]] == ["c", "b", "a"]


def test_profile_update_reaches_the_home_page(door: Door, client: Client) -> None:
    before = door.get_profile()
    assert before.ok and before.data["tagline"] == ""

    updated = door.update_profile(
        {
            "tagline": "웹을 만듭니다",
            "contact_email": "hello@sandcorp.co.kr",
            "company_intro": doc({"id": "intro", "type": "markdown", "body": "회사 소개 문장"}),
        }
    )

    assert updated.ok, updated.error
    assert updated.data["tagline"] == "웹을 만듭니다"
    home = client.get("/").content.decode()
    assert '<meta name="description" content="웹을 만듭니다">' in home
    data = page_data(home)
    assert data["company_intro"]["tabs"][0]["blocks"][0]["body"] == "회사 소개 문장"
    assert data["contact"]["email"] == "hello@sandcorp.co.kr"
    # fields left out are untouched
    assert door.update_profile({"address": "서울"}).data["tagline"] == "웹을 만듭니다"


def test_invalid_profile_input_saves_nothing(door: Door) -> None:
    door.update_profile({"tagline": "before"})

    bad_doc = door.update_profile(
        {"tagline": "after", "ceo_intro": doc({"id": "bad", "type": "no-such-block"})}
    )
    bad_mail = door.update_profile({"contact_email": "not-an-email"})

    assert not bad_doc.ok and "ceo_intro.tabs[0].blocks[0]" in bad_doc.error
    assert not bad_mail.ok and "contact_email" in bad_mail.error
    assert door.get_profile().data["tagline"] == "before"


# --- who may call: the two network doors ---

ROUTES = [
    ("get", "/api/admin/profile"),
    ("patch", "/api/admin/profile"),
    ("get", "/api/admin/portfolio"),
    ("post", "/api/admin/portfolio"),
    ("put", "/api/admin/portfolio/order"),
    ("get", "/api/admin/portfolio/a"),
    ("patch", "/api/admin/portfolio/a"),
    ("put", "/api/admin/portfolio/a/visibility"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_admin_api_needs_a_token_with_admin_scope(
    client: Client, auth_server: FakeAuthServer, method: str, path: str
) -> None:
    def send(path: str, data: str, **kw: Any) -> Any:
        return client.generic(method.upper(), path, data, **kw)

    assert send(path, "{}", content_type="application/json").status_code == 401
    login_only = auth_server.bearer(scope="login")
    assert send(path, "{}", content_type="application/json", headers=login_only).status_code == 403
    stranger = auth_server.bearer(sub="someone-else")
    assert send(path, "{}", content_type="application/json", headers=stranger).status_code == 401


def test_mcp_content_tools_need_a_token_with_admin_scope(
    client: Client, auth_server: FakeAuthServer
) -> None:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_portfolio", "arguments": {"slug": "a", "title": "A"}},
        }
    )
    send = client.post
    assert send("/mcp", body, content_type="application/json").status_code == 401
    login_only = auth_server.bearer(scope="login")
    assert (
        send("/mcp", body, content_type="application/json", headers=login_only).status_code == 403
    )
    assert not PortfolioItem.objects.exists()


CONTENT_TOOLS = {
    "whoami",
    "block_schema",
    "get_profile",
    "update_profile",
    "list_portfolio",
    "get_portfolio",
    "create_portfolio",
    "update_portfolio",
    "reorder_portfolio",
    "set_portfolio_visibility",
}  # fmt: skip (the other tools are checked in test_mcp_proposals)


def test_tool_list_marks_writers_and_readers(client: Client, auth_server: FakeAuthServer) -> None:
    tools = McpClient(client, auth_server).request("tools/list")["result"]
    assert isinstance(tools, dict) and isinstance(tools["tools"], list)
    read_only = {t["name"]: t["annotations"]["readOnlyHint"] for t in tools["tools"]}  # type: ignore[index,call-overload]
    assert {k: v for k, v in read_only.items() if k in CONTENT_TOOLS} == {
        "whoami": True,
        "block_schema": True,
        "get_profile": True,
        "update_profile": False,
        "list_portfolio": True,
        "get_portfolio": True,
        "create_portfolio": False,
        "update_portfolio": False,
        "reorder_portfolio": False,
        "set_portfolio_visibility": False,
    }
