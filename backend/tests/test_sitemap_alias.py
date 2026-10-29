"""sitemap lastmod, /work, slug aliases and verification meta (#111)."""

import re
from datetime import timedelta
from xml.etree import ElementTree

import pytest
from django.test import Client
from django.test.utils import override_settings
from django.utils import timezone

from content.models import BlogPost, PortfolioItem, PortfolioSlugAlias
from services import portfolio
from services.errors import Conflict

pytestmark = pytest.mark.django_db

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def entries(client: Client) -> dict[str, str | None]:
    root = ElementTree.fromstring(client.get("/sitemap.xml").content)
    return {
        (u.findtext(f"{NS}loc") or ""): u.findtext(f"{NS}lastmod") for u in root.iter(f"{NS}url")
    }


def item(slug: str, **fields: object) -> PortfolioItem:
    return PortfolioItem.objects.create(slug=slug, **{"title": slug.upper(), **fields})


def test_sitemap_lastmod_for_works_posts_and_home(client: Client) -> None:
    a = item("a")
    published = timezone.now() - timedelta(days=3)
    post = BlogPost.objects.create(
        slug="hello", title="t", status=BlogPost.Status.PUBLISHED, published_at=published
    )
    BlogPost.objects.create(slug="draft", title="d")
    got = entries(client)
    assert list(got) == [
        "https://sandcorp.co.kr/",
        "https://sandcorp.co.kr/work/a",
        "https://sandcorp.co.kr/blog",
        "https://sandcorp.co.kr/blog/hello",
    ]
    assert got["https://sandcorp.co.kr/work/a"] == a.updated_at.isoformat()
    assert got["https://sandcorp.co.kr/blog/hello"] == max(post.updated_at, published).isoformat()
    assert got["https://sandcorp.co.kr/"] == max(a.updated_at, post.updated_at).isoformat()


def test_work_hub_redirects_to_the_home_portfolio(client: Client) -> None:
    response = client.get("/work")
    assert response.status_code == 301
    assert response["Location"] == "/#home-portfolio"


def test_renaming_a_slug_keeps_the_old_address_as_a_301(client: Client) -> None:
    item("embed-chat", title="Sandcorp Flow")
    portfolio.update_item("embed-chat", portfolio.ItemPatch(new_slug="sandcorp-flow"))

    old = client.get("/work/embed-chat")
    assert (old.status_code, old["Location"]) == (301, "/work/sandcorp-flow")
    new = client.get("/work/sandcorp-flow")
    assert new.status_code == 200
    assert '<link rel="canonical" href="http://testserver/work/sandcorp-flow">' in (
        new.content.decode()
    )
    assert "https://sandcorp.co.kr/work/embed-chat" not in entries(client)
    assert "https://sandcorp.co.kr/work/sandcorp-flow" in entries(client)


def test_a_second_rename_redirects_every_old_address_to_the_latest(client: Client) -> None:
    item("one")
    portfolio.update_item("one", portfolio.ItemPatch(new_slug="two"))
    portfolio.update_item("two", portfolio.ItemPatch(new_slug="three"))
    assert client.get("/work/one")["Location"] == "/work/three"
    assert client.get("/work/two")["Location"] == "/work/three"
    # going back to an old name frees it from the alias list
    portfolio.update_item("three", portfolio.ItemPatch(new_slug="one"))
    assert client.get("/work/one").status_code == 200
    assert client.get("/work/three")["Location"] == "/work/one"


def test_hidden_item_old_address_and_unknown_slug_stay_404(client: Client) -> None:
    item("x", is_public=False)
    portfolio.update_item("x", portfolio.ItemPatch(new_slug="y"))
    assert client.get("/work/x").status_code == 404
    assert client.get("/work/nope").status_code == 404


def test_a_slug_in_use_or_someone_elses_old_address_is_refused() -> None:
    item("a")
    item("b")
    portfolio.update_item("a", portfolio.ItemPatch(new_slug="a2"))
    with pytest.raises(Conflict):
        portfolio.update_item("b", portfolio.ItemPatch(new_slug="a"))  # a's old address
    with pytest.raises(Conflict):
        portfolio.update_item("b", portfolio.ItemPatch(new_slug="a2"))  # live slug
    with pytest.raises(Conflict):
        portfolio.create_item(portfolio.NewItem(slug="a", title="t"))
    assert PortfolioSlugAlias.objects.count() == 1


def test_renaming_in_the_model_alone_records_the_alias(client: Client) -> None:
    """The admin form saves the model directly; it gets the redirect too."""
    found = item("old")
    found.slug = "new"
    found.save()
    assert client.get("/work/old")["Location"] == "/work/new"


def verification(html: str, name: str) -> list[str]:
    return re.findall(rf'<meta name="{name}" content="([^"]*)"', html)


def test_verification_meta_only_with_a_value(client: Client) -> None:
    html = client.get("/").content.decode()
    assert verification(html, "google-site-verification") == []

    with override_settings(GOOGLE_SITE_VERIFICATION="g-token", NAVER_SITE_VERIFICATION="n-token"):
        html = client.get("/").content.decode()
        assert verification(html, "google-site-verification") == ["g-token"]
        assert verification(html, "naver-site-verification") == ["n-token"]

    with override_settings(GOOGLE_SITE_VERIFICATION="g-token", NAVER_SITE_VERIFICATION=""):
        html = client.get("/").content.decode()
        assert verification(html, "google-site-verification") == ["g-token"]
        assert verification(html, "naver-site-verification") == []


def test_naver_verification_default_is_in_home_head_once(client: Client) -> None:
    html = client.get("/").content.decode()
    assert verification(html, "naver-site-verification") == [
        "4768f013dc8c37a24a2b074f7037a60af45c9455"
    ]


def test_mcp_update_input_accepts_new_slug() -> None:
    from mcpserver.tools import UpdateInput

    assert "new_slug" in UpdateInput.model_fields
