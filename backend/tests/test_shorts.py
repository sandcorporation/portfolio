"""YouTube Shorts on the home page (issue 207): ID/URL parsing, the oEmbed title, order and
visibility, the MCP tools, admin and the home section in the server HTML."""

from typing import Any, cast

import pytest
from django.test import Client

from adapters.fake_youtube import FakeYoutube
from content.models import Short
from mcpserver.protocol import INSTRUCTIONS
from services import home, shorts
from services.errors import Conflict, NotFound, Rejected
from tests.site_auth import SiteAuth
from tests.test_blog_pages import page_data
from tests.test_mcp import McpClient
from tests.test_mcp_proposals import ok, refused
from tests.test_public_html import FRONTEND, root

pytestmark = pytest.mark.django_db

type Data = dict[str, Any]  # Any: tool results and page data are arbitrary JSON

VID = "fPqq1pIVjuo"
VID2 = "gtt0x3N0Ojc"


@pytest.mark.parametrize(
    "value",
    [
        VID,
        f"https://www.youtube.com/shorts/{VID}",
        f"https://youtube.com/shorts/{VID}?feature=share",
        f"youtube.com/shorts/{VID}",
        f"https://m.youtube.com/watch?v={VID}&t=3",
        f"https://youtu.be/{VID}?si=abc",
        f"https://www.youtube-nocookie.com/embed/{VID}",
        f"  {VID}  ",
    ],
)
def test_parse_video_takes_an_id_or_a_url(value: str) -> None:
    assert shorts.parse_video(value) == VID


@pytest.mark.parametrize(
    "value",
    [
        "short",
        f"https://evil.example/shorts/{VID}",
        "https://www.youtube.com/@sandcorporation",
        "https://www.youtube.com/watch?v=tooshort",
        f"{VID}x",
    ],
)
def test_parse_video_refuses_anything_else(value: str) -> None:
    assert shorts.parse_video(value) is None


def new(video: str = VID, **fields: Any) -> shorts.NewShort:  # Any: NewShort's fields
    return shorts.NewShort(video=video, **fields)


def test_add_takes_the_oembed_title_and_goes_in_front(youtube: FakeYoutube) -> None:
    youtube.titles = {VID: "첫 쇼츠", VID2: "둘째 쇼츠"}
    first = shorts.add_short(new(f"https://youtube.com/shorts/{VID}"))
    second = shorts.add_short(new(VID2))

    assert first.title == "첫 쇼츠" and first.youtube_id == VID
    assert second.position < first.position  # newest in front
    assert [s.youtube_id for s in shorts.list_shorts()] == [VID2, VID]
    assert youtube.calls == [VID, VID2]


def test_given_title_skips_oembed_and_a_failing_oembed_still_saves(youtube: FakeYoutube) -> None:
    shorts.add_short(new(VID, title="내 제목"))
    youtube.failing = True
    saved = shorts.add_short(new(VID2))

    assert youtube.calls == [VID2]
    assert saved.title == ""
    assert shorts.card_of(Short.objects.get(youtube_id=VID2))["title"] == "Sandcorp 쇼츠"


def test_add_refuses_a_duplicate_a_bad_video_and_an_outside_link() -> None:
    shorts.add_short(new(VID, title="t"))
    with pytest.raises(Conflict):
        shorts.add_short(new(f"https://youtu.be/{VID}"))
    with pytest.raises(Rejected, match="video"):
        shorts.add_short(new("not a video"))
    for link in ["https://evil.example/", "//evil.example/x", "tips/x"]:
        with pytest.raises(Rejected, match="link"):
            shorts.add_short(new(VID2, link=link))
    assert Short.objects.count() == 1


def test_update_changes_only_given_fields_and_delete_removes() -> None:
    shorts.add_short(new(VID, title="t", link="/tips/a"))
    out = shorts.update_short(VID, shorts.ShortPatch(is_visible=False))
    assert out.is_visible is False and out.link == "/tips/a" and out.title == "t"
    out = shorts.update_short(f"https://youtu.be/{VID}", shorts.ShortPatch(position=7, link=""))
    assert out.position == 7 and out.link == ""
    assert shorts.delete_short(VID) == VID
    with pytest.raises(NotFound):
        shorts.delete_short(VID)


def test_public_cards_are_visible_ones_by_position_at_most_four() -> None:
    ids = [f"video{n:06d}" for n in range(6)]
    for n, vid in enumerate(ids):
        shorts.add_short(new(vid, title=f"영상 {n}", position=n, is_visible=n != 1))
    cards = shorts.public_cards()
    assert [c["youtube_id"] for c in cards] == [ids[0], ids[2], ids[3], ids[4]]
    assert cards[0]["thumbnail_url"] == f"https://i.ytimg.com/vi/{ids[0]}/hqdefault.jpg"
    assert cards[0]["url"] == f"https://www.youtube.com/shorts/{ids[0]}"


# --- the home page ---


def test_home_without_shorts_has_no_section(client: Client) -> None:
    html = client.get("/").content.decode()
    assert page_data(html)["shorts"] == []
    assert "home-shorts" not in html


def test_home_server_html_links_to_youtube_with_lazy_thumbnails_and_no_embed(
    client: Client,
) -> None:
    shorts.add_short(new(VID, title="둘째", position=2, link="/tips/flaky"))
    shorts.add_short(new(VID2, title="첫째", position=1))
    shorts.add_short(new("hidden00000", title="숨김", is_visible=False))
    html = client.get("/").content.decode()
    body = root(html)

    cards = cast(list[Data], page_data(html)["shorts"])
    assert [c["youtube_id"] for c in cards] == [VID2, VID]
    assert body.index(f"/shorts/{VID2}") < body.index(f"/shorts/{VID}")
    assert "hidden00000" not in html
    assert 'href="https://www.youtube.com/@sandcorporation" target="_blank"' in body
    assert "유튜브에서 보기 →" in body
    assert '<h2 id="home-shorts" class="page-section-title">짧은 영상</h2>' in body
    assert shorts.SECTION_LEAD in body
    assert f'<img src="https://i.ytimg.com/vi/{VID}/hqdefault.jpg"' in body
    assert 'loading="lazy"' in body and 'width="480" height="360"' in body
    assert '<a class="short-link" href="/tips/flaky">관련 팁 →</a>' in body
    # Nothing on the first load talks to YouTube itself: no iframe, no embed host.
    assert "<iframe" not in html and "youtube-nocookie" not in html


def test_home_numbers_the_shorts_section_after_tips() -> None:
    from core.public_html import home_body

    shorts.add_short(new(VID, title="t"))
    html = str(home_body(home.home_page().data))
    assert "— Shorts</span>" in html
    assert html.index('id="home-shorts"') < html.index('id="home-inquiry"')


def test_fixed_text_matches_the_react_section() -> None:
    source = (FRONTEND / "home" / "ShortsSection.tsx").read_text(encoding="utf-8")
    for text in [
        "유튜브에서 보기 →",
        "짧은 영상",
        shorts.SECTION_LEAD,
        shorts.CHANNEL_URL,
        "youtube-nocookie.com/embed/",
        "Shorts",
    ]:
        assert text in source, text


# --- MCP ---


@pytest.fixture
def mcp(client: Client, auth_server: SiteAuth) -> McpClient:
    return McpClient(client, auth_server)


def test_short_tools_are_listed_and_explained(mcp: McpClient) -> None:
    tools = cast(Data, mcp.request("tools/list")["result"])["tools"]
    listed: dict[str, Data] = {t["name"]: t for t in tools}
    for name in ["list_shorts", "add_short", "update_short", "delete_short"]:
        assert name in listed
    assert listed["list_shorts"]["annotations"]["readOnlyHint"] is True
    assert listed["add_short"]["annotations"]["readOnlyHint"] is False
    assert "add_short" in INSTRUCTIONS


def test_mcp_add_update_list_delete(mcp: McpClient, youtube: FakeYoutube) -> None:
    youtube.titles = {VID: "oEmbed 제목"}
    made: Data = ok(mcp, "add_short", {"video": f"https://www.youtube.com/shorts/{VID}"})
    assert made["youtube_id"] == VID and made["title"] == "oEmbed 제목"

    assert "이미 등록" in refused(mcp, "add_short", {"video": VID})
    assert "link" in refused(mcp, "add_short", {"video": VID2, "link": "https://x.example"})

    changed: Data = ok(mcp, "update_short", {"video": VID, "is_visible": False, "position": 5})
    assert changed["is_visible"] is False and changed["position"] == 5
    listed: Data = ok(mcp, "list_shorts", {})
    assert [row["youtube_id"] for row in listed["items"]] == [VID]
    assert ok(mcp, "delete_short", {"video": VID}) == {"deleted": VID}
    assert "없습니다" in refused(mcp, "delete_short", {"video": VID})


# --- admin ---


def test_admin_add_takes_a_url_and_fills_the_title(
    admin_client: Client, youtube: FakeYoutube
) -> None:
    youtube.titles = {VID: "admin 제목"}
    response = admin_client.post(
        "/admin/content/short/add/",
        {
            "youtube_id": f"https://youtu.be/{VID}",
            "title": "",
            "position": "0",
            "is_visible": "on",
            "link": "",
        },
    )
    assert response.status_code == 302, response.content.decode()[:500]
    assert Short.objects.get().title == "admin 제목"
    listing = admin_client.get("/admin/content/short/").content.decode()
    assert 'name="form-0-position"' in listing and 'name="form-0-is_visible"' in listing
