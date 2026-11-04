"""Link-preview meta and JSON-LD of the four public pages (#110)."""

import json
import re
from datetime import date, timedelta
from typing import cast

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from content.models import BlogPost, PortfolioItem, Proposal, SiteProfile
from content.models import Client as Customer
from core.public_html import HOME_DESCRIPTION
from services import publishing

pytestmark = pytest.mark.django_db

DEFAULT_IMAGE = "http://testserver/static/core/og-default.png"


def tags(html: str, key: str) -> list[str]:
    return re.findall(rf'<meta (?:property|name)="{re.escape(key)}" content="([^"]*)"', html)


def ld_blocks(html: str) -> list[dict[str, object]]:
    found = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return [cast(dict[str, object], json.loads(text)) for text in found]


def graph(html: str) -> dict[str, dict[str, object]]:
    (block,) = ld_blocks(html)
    assert block["@context"] == "https://schema.org"
    nodes = cast(list[dict[str, object]], block["@graph"])
    return {cast(str, node["@type"]): node for node in nodes}


def make_post(slug: str = "p", **fields: object) -> BlogPost:
    values: dict[str, object] = {
        "slug": slug,
        "title": f"제목 {slug}",
        "summary": f"요약 {slug}",
        "status": BlogPost.Status.PUBLISHED,
        "published_at": timezone.now() - timedelta(days=2),
    }
    return BlogPost.objects.create(**{**values, **fields})


def test_home_has_the_default_image_twitter_card_and_organization_graph(client: Client) -> None:
    SiteProfile.objects.create(pk=1, tagline="만듭니다", representative="김한얼")

    html = client.get("/").content.decode()
    nodes = graph(html)

    assert tags(html, "og:image") == [DEFAULT_IMAGE]
    assert tags(html, "og:image:alt") == ["Sandcorp 로고"]
    assert tags(html, "og:image:width") == ["1200"]
    assert tags(html, "og:image:height") == ["630"]
    assert tags(html, "twitter:card") == ["summary_large_image"]
    assert tags(html, "twitter:image") == [DEFAULT_IMAGE]
    assert tags(html, "twitter:title") == [
        "샌드코프(Sandcorp) — 웹·AI 제품을 만들고 운영하는 1인 개발사"
    ]
    assert tags(html, "twitter:description") == [HOME_DESCRIPTION]
    assert tags(html, "og:title") == [
        "샌드코프(Sandcorp) — 웹·AI 제품을 만들고 운영하는 1인 개발사"
    ]
    assert tags(html, "og:description") == [HOME_DESCRIPTION]
    assert "<title>샌드코프(Sandcorp) — 웹·AI 제품을 만들고 운영하는 1인 개발사</title>" in html
    assert nodes["WebSite"]["description"] == HOME_DESCRIPTION
    assert set(nodes) == {"Organization", "WebSite", "Person"}
    org, site, person = nodes["Organization"], nodes["WebSite"], nodes["Person"]
    assert org["name"] == "샌드코프(Sandcorp)"
    assert org["url"] == "https://sandcorp.co.kr/"
    assert org["logo"] == "http://testserver/static/core/logo.svg"
    assert org["sameAs"] == ["https://github.com/sandcorporation"]
    assert "contactPoint" not in org
    assert site["publisher"] == {"@id": org["@id"]}
    assert person["name"] == "김한얼"
    assert person["worksFor"] == {"@id": org["@id"]}


def test_home_without_a_representative_has_no_person(client: Client) -> None:
    SiteProfile.objects.create(pk=1, representative="")

    assert set(graph(client.get("/").content.decode())) == {"Organization", "WebSite"}


def test_a_work_page_is_a_creative_work_with_the_cover_or_the_default_image(
    client: Client,
) -> None:
    PortfolioItem.objects.create(
        slug="voice",
        title="녹취 분석",
        summary="녹취를 분석합니다",
        tags="음성, 분석",
        service_url="https://voice.example.com/app",
    )

    html = client.get("/work/voice").content.decode()
    (ld,) = ld_blocks(html)

    assert tags(html, "og:image") == [DEFAULT_IMAGE]
    assert tags(html, "og:image:alt") == ["Sandcorp 로고"]
    assert ld["@type"] == "CreativeWork"
    assert ld["name"] == "녹취 분석"
    assert ld["description"] == "녹취를 분석합니다"
    assert ld["keywords"] == "음성, 분석"
    assert ld["url"] == "http://testserver/work/voice"
    assert ld["sameAs"] == "https://voice.example.com/app"
    assert ld["image"] == DEFAULT_IMAGE
    assert ld["creator"] == {
        "@type": "Organization",
        "name": "Sandcorp",
        "url": "https://sandcorp.co.kr",
    }
    assert not tags(html, "article:published_time")


def test_a_work_page_without_summary_or_tags_states_only_what_it_has(client: Client) -> None:
    PortfolioItem.objects.create(slug="bare", title="Bare")

    (ld,) = ld_blocks(client.get("/work/bare").content.decode())

    assert "description" not in ld
    assert "keywords" not in ld
    assert "sameAs" not in ld


def test_a_blog_post_carries_article_times_tags_and_blogposting(client: Client) -> None:
    post = make_post("mid", tags="운영, 도구")

    html = client.get("/blog/mid").content.decode()
    (ld,) = ld_blocks(html)

    assert tags(html, "og:type") == ["article"]
    assert tags(html, "article:published_time") == [post.published_at.isoformat()]  # type: ignore[union-attr]
    (modified,) = tags(html, "article:modified_time")
    assert modified >= tags(html, "article:published_time")[0]
    assert tags(html, "article:tag") == ["운영", "도구"]
    assert tags(html, "og:image") == [DEFAULT_IMAGE]
    assert tags(html, "twitter:card") == ["summary_large_image"]
    assert ld["@type"] == "BlogPosting"
    assert ld["datePublished"] == post.published_at.isoformat()  # type: ignore[union-attr]
    assert ld["dateModified"] == modified
    assert ld["image"] == DEFAULT_IMAGE


def test_the_blog_list_uses_the_default_image(client: Client) -> None:
    make_post("a")

    html = client.get("/blog").content.decode()

    assert tags(html, "og:image") == [DEFAULT_IMAGE]
    assert tags(html, "og:image:alt") == ["Sandcorp 로고"]


def test_private_pages_carry_no_preview_image_or_json_ld(client: Client) -> None:
    call_command("createcachetable", verbosity=0)
    customer = Customer.objects.create(name="고객", code="CUST")
    Proposal.objects.create(client=customer, title="비공개", slug="x", quote_date=date(2026, 10, 1))
    publishing.publish("x")

    html = client.get("/p/x").content.decode()

    assert not tags(html, "og:image")
    assert not tags(html, "twitter:image")
    assert not ld_blocks(html)


HOSTILE = '</script><script>alert(1)</script>&"'  # 38 chars: fits the profile's 40


def test_json_ld_cannot_close_its_script_tag(client: Client) -> None:
    SiteProfile.objects.create(pk=1, business_name=HOSTILE, representative=HOSTILE)
    PortfolioItem.objects.create(slug="w", title=HOSTILE, summary=HOSTILE, tags="t")
    make_post("evil", title=HOSTILE, summary=HOSTILE, tags="a</script>b")

    for path in ("/", "/work/w", "/blog/evil", "/blog"):
        html = client.get(path).content.decode()
        assert "<script>alert(1)" not in html
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        assert block
        assert "<" not in block.group(1)
        assert HOSTILE in block.group(1).encode().decode("unicode_escape") or path == "/blog"

    html = client.get("/blog/evil").content.decode()
    assert ld_blocks(html)[0]["headline"] == HOSTILE
    assert "article:tag" in html and "a</script>b" not in html


def test_the_default_image_keeps_its_fixed_size(client: Client) -> None:
    PortfolioItem.objects.create(slug="n", title="N")

    html = client.get("/work/n").content.decode()

    assert tags(html, "og:image:width") == ["1200"] and tags(html, "og:image:height") == ["630"]
