"""What the public home page shows, read from the site profile."""

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from django.utils import timezone

from adapters.foresight import ForesightArticle, fetch_recent
from content.models import SiteProfile
from documents.validation import JSON
from services import blog, media
from services.portfolio import PortfolioCard, public_cards

RECENT_POSTS = 3
RECENT_NEWS = 5
NEWS_UTM = {"utm_source": "sandcorp", "utm_medium": "home"}
SEOUL = ZoneInfo("Asia/Seoul")

DEFAULT_DESCRIPTION = "샌드코프 포트폴리오"


class Contact(TypedDict):
    email: str
    phone: str
    address: str


class NewsItem(TypedDict):
    """One Foresight article on the home page. `when` is worked out here, not in the browser."""

    title: str
    summary: str
    category: str  # "" when the article has none
    image_url: str  # "" when it has none
    url: str  # the article, with the utm marks
    when: str  # "3시간 전"
    published_at: str  # ISO 8601


class HomeData(TypedDict):
    """Embedded in the shell as #page-data. Mirrored by frontend/src/home/types.ts."""

    tagline: str
    stack: list[str]  # the GitHub profile's stack badges: the hero's tag line
    company_intro: dict[str, JSON]
    ceo_intro: dict[str, JSON]
    contact: Contact
    portfolio: list[PortfolioCard]
    posts: list[blog.PostCard]  # newest published blog posts; empty hides the section
    news: list[NewsItem]  # newest Foresight articles; empty hides the section


def relative_time(then: datetime, now: datetime) -> str:
    """「방금 전」「5분 전」「3시간 전」「2일 전」; a week or more ago is the date (Seoul)."""
    seconds = (now - then).total_seconds()
    if seconds < 60:  # also a clock a little ahead of ours
        return "방금 전"
    if seconds < 3600:
        return f"{int(seconds // 60)}분 전"
    if seconds < 86400:
        return f"{int(seconds // 3600)}시간 전"
    if seconds < 7 * 86400:
        return f"{int(seconds // 86400)}일 전"
    return then.astimezone(SEOUL).strftime("%Y.%m.%d")


def with_utm(url: str) -> str:
    """`url` with the home page's utm marks (an existing mark of the same name is replaced)."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in NEWS_UTM]
    return urlunsplit(parts._replace(query=urlencode([*query, *NEWS_UTM.items()])))


def news_item(article: ForesightArticle, now: datetime) -> NewsItem:
    return NewsItem(
        title=article.title,
        summary=article.summary,
        category=article.category,
        image_url=article.image_url,
        url=with_utm(article.url),
        when=relative_time(article.published_at, now),
        published_at=article.published_at.isoformat(),
    )


def recent_news(limit: int = RECENT_NEWS) -> list[NewsItem]:
    """The home page's Foresight rows. Never raises: a dead news site is just no rows."""
    now = timezone.now()
    return [news_item(a, now) for a in fetch_recent(limit)]


def stack_of(github: object) -> list[str]:
    badges = github.get("stack_badges") if isinstance(github, dict) else None
    return [b for b in badges if isinstance(b, str)] if isinstance(badges, list) else []


@dataclass(frozen=True)
class HomePage:
    description: str
    data: HomeData


def home_page() -> HomePage:
    # Reading never creates the profile row; an unsaved default stands in until admin saves one.
    profile = SiteProfile.objects.filter(pk=1).first() or SiteProfile()
    return HomePage(
        description=profile.tagline or DEFAULT_DESCRIPTION,
        data=HomeData(
            tagline=profile.tagline,
            stack=stack_of(profile.github),
            company_intro=media.resolve_document(profile.company_intro),
            ceo_intro=media.resolve_document(profile.ceo_intro),
            contact=Contact(
                email=profile.contact_email,
                phone=profile.contact_phone,
                address=profile.address,
            ),
            portfolio=public_cards(),
            posts=recent_posts(),
            news=recent_news(),
        ),
    )


def recent_posts(limit: int = RECENT_POSTS) -> list[blog.PostCard]:
    """The home page's newest blog posts (published only)."""
    return blog.public_cards(limit=limit)
