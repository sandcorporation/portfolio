"""The blog 「기록」 (#74): post rules in services.blog, the sitemap and /blog/feed.xml."""

from datetime import timedelta
from email.utils import parsedate_to_datetime
from typing import cast
from xml.etree import ElementTree

import pytest
from django.test import Client
from django.utils import timezone

from content.models import BlogPost, Media
from services import blog, home, media
from services.errors import Conflict, NotFound, Rejected

pytestmark = pytest.mark.django_db

PARAGRAPH = {"type": "markdown", "body": "본문"}


def new(title: str = "First post", **fields: object) -> blog.PostOut:
    return blog.create_post(blog.NewPost.model_validate({"title": title, **fields}))


def published(title: str, *, ago_hours: int, tags: list[str] | None = None) -> blog.PostOut:
    post = new(title, tags=tags or [])
    blog.publish_post(post.slug)
    at = timezone.now() - timedelta(hours=ago_hours)
    BlogPost.objects.filter(slug=post.slug).update(published_at=at)
    return post


# --- slugs ---


def test_slug_comes_from_the_latin_part_of_the_title() -> None:
    assert new("Hello, Django 6!").slug == "hello-django-6"


def test_a_korean_title_gets_post_hex() -> None:
    slug = new("한글 제목만 있는 글").slug
    assert slug.startswith("post-") and len(slug) == len("post-") + 6


def test_a_taken_generated_slug_gets_a_number() -> None:
    assert [new("Same title").slug for _ in range(3)] == [
        "same-title",
        "same-title-2",
        "same-title-3",
    ]


def test_a_given_slug_that_is_taken_is_a_conflict() -> None:
    new("A", slug="mine")
    with pytest.raises(Conflict):
        new("B", slug="mine")


# --- publishing ---


def test_a_new_post_is_a_hidden_draft() -> None:
    post = new()
    assert post.status == "draft" and post.published_at is None
    assert blog.list_posts() == []
    with pytest.raises(NotFound):
        blog.get_post(post.slug)
    assert blog.get_post(post.slug, published_only=False).slug == post.slug
    assert blog.public_detail(post.slug) is None


def test_published_at_is_set_once_and_kept() -> None:
    post = new()
    first = blog.publish_post(post.slug).published_at
    assert first is not None
    assert blog.unpublish_post(post.slug).published_at == first
    assert blog.list_posts() == []
    assert blog.publish_post(post.slug).published_at == first
    assert [p.slug for p in blog.list_posts()] == [post.slug]


def test_lists_are_newest_first_with_tag_filter_and_limit() -> None:
    published("Old", ago_hours=3, tags=["django"])
    published("Mid", ago_hours=2, tags=["react"])
    published("New", ago_hours=1, tags=["django", "mysql"])
    new("Draft", tags=["django"])

    assert [p.title for p in blog.list_posts()] == ["New", "Mid", "Old"]
    assert [p.title for p in blog.list_posts(tag="django")] == ["New", "Old"]
    assert [p.title for p in blog.list_posts(limit=2)] == ["New", "Mid"]
    assert [p.title for p in blog.list_posts(published_only=False)][0] == "Draft"
    assert [c["title"] for c in home.recent_posts()] == ["New", "Mid", "Old"]
    assert blog.public_tags() == [
        {"tag": "django", "count": 2},
        {"tag": "mysql", "count": 1},
        {"tag": "react", "count": 1},
    ]


def test_a_tag_is_matched_whole() -> None:
    published("Go", ago_hours=1, tags=["golang"])
    assert blog.list_posts(tag="go") == []


def test_detail_links_the_older_and_newer_post() -> None:
    old = published("Old", ago_hours=3)
    mid = published("Mid", ago_hours=2)
    newest = published("New", ago_hours=1)

    detail = blog.public_detail(mid.slug)
    assert detail is not None
    assert detail["card"]["title"] == "Mid"
    assert detail["prev"] == {"slug": old.slug, "title": "Old"}
    assert detail["next"] == {"slug": newest.slug, "title": "New"}
    end = blog.public_detail(newest.slug)
    assert end is not None and end["next"] is None


# --- documents ---


def block_ids(post: blog.PostOut) -> list[str]:
    tabs = cast(list[dict[str, list[dict[str, str]]]], post.body["tabs"])
    return [b["id"] for b in tabs[0]["blocks"]]


def test_block_edits_are_validated_and_refused_with_a_block_path() -> None:
    post = new()
    post = blog.insert_block(post.slug, {"id": "p1", **PARAGRAPH})
    post = blog.insert_block(post.slug, {"id": "p2", **PARAGRAPH}, after_block_id="p1")
    assert block_ids(post) == ["p1", "p2"]

    with pytest.raises(Rejected) as refused:
        blog.replace_block(post.slug, "p1", {"type": "nope"})
    assert refused.value.errors[0].path.startswith("body.tabs[0].blocks[0]")
    assert blog.get_post(post.slug, published_only=False).body == post.body  # nothing saved

    post = blog.delete_block(post.slug, "p1")
    assert block_ids(post) == ["p2"]
    with pytest.raises(NotFound):
        blog.delete_block(post.slug, "p1")


def test_a_bad_document_is_not_created() -> None:
    with pytest.raises(Rejected):
        new(body={"tabs": [{"id": "main", "title": "t", "blocks": [{"type": "nope"}]}]})
    assert not BlogPost.objects.exists()


def test_update_changes_only_given_fields() -> None:
    post = new(summary="요약", tags=["a"])
    out = blog.update_post(post.slug, blog.PostPatch.model_validate({"title": "Renamed"}))
    assert (out.title, out.summary, out.tags, out.slug) == ("Renamed", "요약", ["a"], post.slug)


def test_media_in_a_published_post_counts_as_a_live_page() -> None:
    image = Media.objects.create(
        object_key="m/a.png",
        original_filename="a.png",
        content_type="image/png",
        size=1,
        is_public=True,
        uploaded_at=timezone.now(),
    )
    post = new(body={"tabs": [{"id": "main", "title": "t", "blocks": [
        {"id": "g", "type": "gallery", "images": [{"media_id": image.pk, "alt": "a"}]}
    ]}]})  # fmt: skip
    assert media.usage_of([image.pk])[image.pk].drafts == (f"블로그 「{post.title}」",)
    blog.publish_post(post.slug)
    assert media.usage_of([image.pk])[image.pk].pages == (f"블로그 「{post.title}」",)


def test_delete_post() -> None:
    post = new()
    blog.delete_post(post.slug)
    with pytest.raises(NotFound):
        blog.delete_post(post.slug)


# --- sitemap and feed ---


def locs(client: Client) -> list[str]:
    root = ElementTree.fromstring(client.get("/sitemap.xml").content)
    return [e.text or "" for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]


def test_sitemap_lists_the_blog_and_published_posts_only(client: Client) -> None:
    assert not any("/blog" in loc for loc in locs(client))  # no posts: no /blog either
    post = published("Live", ago_hours=1)
    new("Draft")
    assert [loc for loc in locs(client) if "/blog" in loc] == [
        "https://sandcorp.co.kr/blog",
        f"https://sandcorp.co.kr/blog/{post.slug}",
    ]


def test_feed_is_rss_of_published_posts(client: Client) -> None:
    older = published("Old <one>", ago_hours=2, tags=["django"])
    newest = published("New", ago_hours=1)
    new("Draft")

    response = client.get("/blog/feed.xml")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/rss+xml; charset=utf-8"
    assert response["Cache-Control"] == "public, max-age=300"
    channel = ElementTree.fromstring(response.content).find("channel")
    assert channel is not None
    items = channel.findall("item")
    assert [i.findtext("title") for i in items] == ["New", "Old <one>"]
    assert items[0].findtext("link") == f"https://sandcorp.co.kr/blog/{newest.slug}"
    assert items[1].findtext("guid") == f"https://sandcorp.co.kr/blog/{older.slug}"
    assert [c.text for c in items[1].findall("category")] == ["django"]
    pub = parsedate_to_datetime(items[0].findtext("pubDate") or "")
    stored = BlogPost.objects.get(slug=newest.slug).published_at
    assert stored is not None and pub == stored.replace(microsecond=0)
    assert channel.findtext("lastBuildDate") == items[0].findtext("pubDate")


def test_feed_keeps_the_newest_thirty(client: Client) -> None:
    for n in range(31):
        published(f"P{n}", ago_hours=n + 1)
    channel = ElementTree.fromstring(client.get("/blog/feed.xml").content).find("channel")
    assert channel is not None and len(channel.findall("item")) == 30
