import re
from datetime import date

import pytest
from django.core.management import call_command
from django.test import Client

from content.models import Client as Client_
from content.models import Proposal, SiteProfile
from services import publishing


def meta(html: str, name: str) -> str | None:
    found = re.search(rf'<meta name="{name}" content="([^"]*)"', html)
    return found.group(1) if found else None


def og(html: str, prop: str) -> str | None:
    found = re.search(rf'<meta property="og:{prop}" content="([^"]*)"', html)
    return found.group(1) if found else None


@pytest.mark.django_db
def test_home_shell_carries_title_description_and_og_from_the_profile(client: Client) -> None:
    profile = SiteProfile.load()
    profile.tagline = "음성·영상 처리와 사내 시스템을 만듭니다"
    profile.save()

    html = client.get("/").content.decode()

    assert "<title>Sandcorp</title>" in html
    assert meta(html, "description") == "음성·영상 처리와 사내 시스템을 만듭니다"
    assert og(html, "title") == "Sandcorp"
    assert og(html, "description") == "음성·영상 처리와 사내 시스템을 만듭니다"
    assert og(html, "url") == "http://testserver/"
    assert '<link rel="canonical" href="http://testserver/">' in html


@pytest.mark.django_db
def test_home_shell_is_indexable_and_mounts_react(client: Client) -> None:
    response = client.get("/")
    html = response.content.decode()

    assert response.status_code == 200
    assert "<title>Sandcorp</title>" in html
    assert meta(html, "robots") == "index, follow"
    assert '<div id="root"></div>' in html
    assert '<script type="module" src="/static/assets/main-abc123.js"></script>' in html
    assert '<link rel="stylesheet" href="/static/assets/main-def456.css">' in html


@pytest.mark.django_db
def test_published_proposal_shell_is_noindex_and_keeps_meta_generic(client: Client) -> None:
    call_command("createcachetable", verbosity=0)  # the code form reads the failure counter
    owner = Client_.objects.create(name="가나다상사", code="NEXT")
    Proposal.objects.create(
        client=owner, title="가나다상사 견적", slug="ganadatrade-2026", quote_date=date(2026, 10, 1)
    )
    publishing.publish("ganadatrade-2026")

    response = client.get("/p/ganadatrade-2026")
    html = response.content.decode()

    assert response.status_code == 200
    assert meta(html, "robots") == "noindex, nofollow"
    assert "<title>제안서 | Sandcorp</title>" in html
    assert "가나다상사" not in html
