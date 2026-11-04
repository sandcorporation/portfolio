"""New Shorts from the YouTube channel feed (issue 211): parsing the feed, registering only
videos never seen, leaving existing ones alone, remembering deleted ones, the worker schedule."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any, cast

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client

from adapters import youtube as youtube_adapter
from adapters.fake_youtube import FakeYoutube, atom_feed, shorts_page
from content.models import DismissedShort, Short
from core.management.commands import pdf_worker
from mcpserver.protocol import INSTRUCTIONS
from services import shorts
from tests.site_auth import SiteAuth
from tests.test_mcp import McpClient

pytestmark = pytest.mark.django_db

A, B, C = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"
T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def feed(*entries: tuple[str, str, int]) -> bytes:
    """Entries as (id, title, hours after T0), in the order given (YouTube: newest first)."""
    return atom_feed(*[(vid, title, T0 + timedelta(hours=h)) for vid, title, h in entries])


def order() -> list[str]:
    return list(Short.objects.values_list("youtube_id", flat=True))


# --- the feed ---


def test_the_feed_is_parsed_into_id_title_and_published(youtube: FakeYoutube) -> None:
    youtube.feed = feed((B, "새 영상 &amp; 둘", 2), (A, "첫 영상", 1), ("short", "잘못된 ID", 0))
    entries = youtube_adapter.fetch_channel_feed()
    assert [(e.youtube_id, e.title, e.published) for e in entries] == [
        (B, "새 영상 & 둘", T0 + timedelta(hours=2)),
        (A, "첫 영상", T0 + timedelta(hours=1)),
    ]


@pytest.mark.parametrize(
    "body",
    [
        b"<feed><entry>",  # broken XML
        b"",
        b'{"not": "xml"}',
        b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY x "boom">]>'
        b'<feed xmlns="http://www.w3.org/2005/Atom">&x;</feed>',
        b"<rss><channel/></rss>",  # not Atom
    ],
)
def test_a_bad_feed_is_an_empty_list(youtube: FakeYoutube, body: bytes) -> None:
    youtube.feed = body
    assert youtube_adapter.fetch_channel_feed() == []
    assert shorts.sync_from_channel() == 0


def test_an_empty_or_unreachable_feed_makes_nothing(youtube: FakeYoutube) -> None:
    assert youtube_adapter.fetch_channel_feed() == []  # the fake's default feed has no entries
    youtube.failing = True
    assert shorts.sync_from_channel() == 0
    assert Short.objects.count() == 0


# --- the sync ---


def test_new_videos_come_in_visible_with_the_feed_title_newest_in_front(
    youtube: FakeYoutube,
) -> None:
    Short.objects.create(youtube_id=C, title="이미 있음", position=0)
    youtube.feed = feed((B, "둘째", 2), (A, "첫째", 1))

    assert shorts.sync_from_channel() == 2
    assert order() == [B, A, C]
    made = Short.objects.get(youtube_id=B)
    assert (made.title, made.is_visible) == ("둘째", True)
    assert youtube.calls == ["feed", f"is_short:{A}", f"is_short:{B}"]  # no oEmbed lookups


def test_existing_shorts_are_never_changed(youtube: FakeYoutube) -> None:
    Short.objects.create(
        youtube_id=A, title="내 제목", position=7, is_visible=False, link="/tips/x"
    )
    youtube.feed = feed((A, "피드 제목", 1))

    assert shorts.sync_from_channel() == 0
    short = Short.objects.get()
    assert (short.title, short.position, short.is_visible, short.link) == (
        "내 제목",
        7,
        False,
        "/tips/x",
    )
    assert youtube.calls == ["feed"]  # a known video is not looked at again


def test_running_twice_makes_no_duplicates(youtube: FakeYoutube) -> None:
    youtube.feed = feed((A, "첫째", 1), (A, "첫째 또", 1))
    assert shorts.sync_from_channel() == 1
    assert shorts.sync_from_channel() == 0
    assert order() == [A]


def test_a_race_with_another_process_is_not_an_error(
    youtube: FakeYoutube, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another worker registers the same video between our check and our insert."""
    youtube.feed = feed((A, "첫째", 1))
    real = youtube_adapter.check_is_short

    def other_process_first(youtube_id: str) -> bool:
        Short.objects.create(youtube_id=youtube_id, title="먼저", position=3)
        return real(youtube_id)

    monkeypatch.setattr(youtube_adapter, "check_is_short", other_process_first)
    assert shorts.sync_from_channel() == 0
    assert Short.objects.get().title == "먼저"


def test_a_deleted_short_does_not_come_back_until_added_by_hand(youtube: FakeYoutube) -> None:
    youtube.feed = feed((A, "첫째", 1))
    shorts.sync_from_channel()
    shorts.delete_short(A)
    assert DismissedShort.objects.get().reason == DismissedShort.Reason.DELETED

    assert shorts.sync_from_channel() == 0
    assert Short.objects.count() == 0

    shorts.add_short(shorts.NewShort(video=A, title="되살림"))
    assert not DismissedShort.objects.exists()
    shorts.delete_short(A)
    assert DismissedShort.objects.filter(youtube_id=A).exists()


def test_a_regular_video_is_skipped_once_and_a_failed_check_counts_as_a_short(
    youtube: FakeYoutube,
) -> None:
    youtube.feed = feed((A, "일반 영상", 1))
    youtube.regular = {A}
    assert shorts.sync_from_channel() == 0
    assert DismissedShort.objects.get().reason == DismissedShort.Reason.NOT_SHORT
    youtube.calls.clear()
    assert shorts.sync_from_channel() == 0
    assert youtube.calls == ["feed"]

    youtube.feed = feed((B, "판정 실패", 2))
    youtube.shorts_check_failing = True
    assert shorts.sync_from_channel() == 1
    assert order() == [B]


# --- admin ---


def test_admin_delete_dismisses_and_admin_add_takes_it_back(admin_client: Client) -> None:
    short = Short.objects.create(youtube_id=A, title="첫째")
    response = admin_client.post(f"/admin/content/short/{short.pk}/delete/", {"post": "yes"})
    assert response.status_code == 302
    assert DismissedShort.objects.filter(youtube_id=A).exists()

    other = Short.objects.create(youtube_id=B, title="둘째")
    response = admin_client.post(
        "/admin/content/short/",
        {"action": "delete_selected", "_selected_action": [other.pk], "post": "yes"},
    )
    assert response.status_code == 302
    assert set(DismissedShort.objects.values_list("youtube_id", flat=True)) == {A, B}

    response = admin_client.post(
        "/admin/content/short/add/",
        {"youtube_id": A, "title": "다시", "position": "0", "is_visible": "on", "link": ""},
    )
    assert response.status_code == 302
    assert list(DismissedShort.objects.values_list("youtube_id", flat=True)) == [B]


# --- schedule ---


def test_the_sync_runs_at_most_every_half_hour_across_processes(youtube: FakeYoutube) -> None:
    youtube.feed = feed((A, "첫째", 1))
    assert shorts.sync_if_due() == 1
    youtube.feed = feed((B, "둘째", 2))
    assert shorts.sync_if_due() is None
    cache.delete(shorts.SYNC_DUE_KEY)  # half an hour later
    assert shorts.sync_if_due() == 1


def test_the_worker_checks_on_its_own_clock_and_survives_a_failing_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs: list[int] = []
    every = pdf_worker.Every(60.0, lambda: runs.append(1))
    for now in [0.0, 30.0, 59.9, 60.0, 61.0, 125.0]:
        every.tick(now)
    assert len(runs) == 3  # 0, 60, 125
    assert [c._seconds for c in pdf_worker.checks()] == [
        pdf_worker.RETENTION_CHECK_SECONDS,
        pdf_worker.SHORTS_CHECK_SECONDS,
    ]

    def boom() -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(shorts, "sync_from_channel", boom)
    pdf_worker.sync_shorts_if_due()  # logged, not raised
    assert cache.get(shorts.SYNC_DUE_KEY) is None  # the next check retries


def test_the_command_syncs_now(youtube: FakeYoutube) -> None:
    youtube.feed = feed((A, "첫째", 1))
    out = StringIO()
    call_command("sync_shorts", stdout=out)
    assert "원천: 채널 피드, 새 쇼츠 1개" in out.getvalue()


# --- the Shorts tab as the fallback (issue 213) ---

X, Y = "xxxxxxxxxxx", "yyyyyyyyyyy"


def test_the_shorts_page_gives_ids_in_page_order_without_duplicates_or_other_shelves(
    youtube: FakeYoutube,
) -> None:
    youtube.shorts_page = shorts_page(B, A, B, C, outside=(X, Y))
    assert youtube_adapter.fetch_channel_shorts_page() == [B, A, C]


def test_the_shorts_page_is_cut_at_thirty(youtube: FakeYoutube) -> None:
    ids = [f"id{n:09d}" for n in range(40)]
    youtube.shorts_page = shorts_page(*ids)
    assert youtube_adapter.fetch_channel_shorts_page() == ids[:30]


@pytest.mark.parametrize(
    "body",
    [b"", b"<html>consent</html>", shorts_page(outside=(X,)), b'{"shortsLockupViewModel":{}}'],
)
def test_a_page_without_shorts_is_an_empty_list(youtube: FakeYoutube, body: bytes) -> None:
    youtube.shorts_page = body
    assert youtube_adapter.fetch_channel_shorts_page() == []


def test_an_unreachable_or_consent_page_is_an_empty_list(youtube: FakeYoutube) -> None:
    youtube.shorts_page_failing = True
    assert youtube_adapter.fetch_channel_shorts_page() == []


def test_a_dead_feed_falls_back_to_the_shorts_tab_newest_in_front(youtube: FakeYoutube) -> None:
    youtube.failing = False
    youtube.feed = b"<html>404</html>"
    youtube.shorts_page = shorts_page(B, A)  # newest first
    youtube.titles = {A: "첫째", B: "둘째"}
    out = StringIO()
    call_command("sync_shorts", stdout=out)
    assert "원천: 쇼츠 탭, 새 쇼츠 2개" in out.getvalue()
    assert order() == [B, A]
    assert dict(Short.objects.values_list("youtube_id", "title")) == {A: "첫째", B: "둘째"}
    assert not any(c.startswith("is_short:") for c in youtube.calls)  # the tab needs no HEAD


def test_the_shorts_tab_keeps_the_other_rules(youtube: FakeYoutube) -> None:
    Short.objects.create(youtube_id=A, title="손으로", position=5, is_visible=False)
    shorts.dismiss(C)
    youtube.feed = b""
    youtube.shorts_page = shorts_page(C, B, A)
    assert shorts.sync_from_channel() == 1  # only B is new
    assert order() == [B, A]
    assert Short.objects.get(youtube_id=A).title == "손으로"
    assert Short.objects.get(youtube_id=B).title == ""  # oEmbed has no title: left empty


def test_a_working_feed_is_used_before_the_tab(youtube: FakeYoutube) -> None:
    youtube.feed = feed((A, "피드", 1))
    youtube.shorts_page = shorts_page(B)
    assert shorts.sync_channel() == shorts.SyncResult("채널 피드", 1)
    assert "shorts_page" not in youtube.calls


def test_both_sources_down_makes_nothing_and_raises_nothing(youtube: FakeYoutube) -> None:
    youtube.failing = True
    assert shorts.sync_channel() == shorts.SyncResult("쇼츠 탭", 0)


# --- MCP wording ---


type Data = dict[str, Any]  # Any: tool results are arbitrary JSON


def test_mcp_says_shorts_come_in_by_themselves(client: Client, auth_server: SiteAuth) -> None:
    mcp = McpClient(client, auth_server)
    tools = cast(Data, mcp.request("tools/list")["result"])["tools"]
    described = {t["name"]: t["description"] for t in tools}
    assert "every 30 minutes" in INSTRUCTIONS
    assert "every 30" in described["whoami"]
    assert "before the automatic sync" in described["add_short"]
    assert "not registered again by the automatic channel sync" in described["delete_short"]
    assert "is_visible false" in described["delete_short"]
