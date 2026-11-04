"""What the public home page shows, read from the site profile."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from django.utils import timezone

from adapters.foresight import ForesightArticle, ForesightStats, fetch_recent
from adapters.foresight import fetch_stats as fetch_foresight_stats
from adapters.metrics import Stats, fetch_stats
from content.models import SiteProfile
from documents.validation import JSON
from services import blog, media, offerings, shorts, tips
from services.portfolio import PortfolioCard, card_of, public_items

RECENT_POSTS = 3
RECENT_NEWS = 5
TIP_POOL = 12  # newest published tips sent down; the browser picks three of them (issue 204)
NEWS_UTM = {"utm_source": "sandcorp", "utm_medium": "home"}
SEOUL = ZoneInfo("Asia/Seoul")

DEFAULT_DESCRIPTION = "샌드코프 포트폴리오"


class Contact(TypedDict):
    email: str
    phone: str
    address: str


class Business(TypedDict):
    """The public footer's business details; an empty string leaves that item out."""

    name: str
    representative: str
    number: str
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


class SiteVisits(TypedDict):
    """The masthead's counts over all four sites (sandcorp-metrics' `total`)."""

    live: int  # people on a site right now
    today: int  # visitors today
    total: int  # visitors since the count began


class Availability(TypedDict):
    """The masthead's 「● 새 프로젝트 받는 중 · 갱신 2026.10」; `updated` is "" without a date."""

    text: str
    updated: str  # YYYY.MM


class EvidenceItem(TypedDict):
    """One big number of the evidence row under the hero (#91). `value` is already formatted."""

    key: str  # "services" | "foresight" | "visitors" | "reply" | "career"
    value: str  # "4", "1,234", "1일"
    unit: str  # small text after the value ("건/일", "년차"), "" when none
    label: str  # the mono label


class HomeData(TypedDict):
    """Embedded in the shell as #page-data. Mirrored by frontend/src/home/types.ts."""

    tagline: str
    stack: list[str]  # the GitHub profile's stack badges: the hero's tag line
    company_intro: dict[str, JSON]
    contact: Contact
    portfolio: list[PortfolioCard]
    posts: list[blog.PostCard]  # newest published blog posts; empty hides the section
    tips: list[tips.TipCard]  # newest published tips (pool); the server HTML draws the first three
    shorts: list[shorts.ShortCard]  # visible YouTube Shorts by position, at most four; empty hides
    news: list[NewsItem]  # newest Foresight articles; empty hides the section
    visits: SiteVisits | None  # None (metrics off or down) leaves the masthead's counts out
    availability: Availability | None  # None (empty profile field) leaves it out
    business: Business | None  # None (all empty) leaves the footer line out
    evidence: list[EvidenceItem]  # the row under the hero; empty hides it (fewer than 2 items)
    services: list[offerings.OfferingCard]  # the 「서비스」 rows (issue 163); empty hides them


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


def site_visits(stats: Stats | None) -> SiteVisits | None:
    if stats is None:
        return None
    t = stats.total
    return SiteVisits(live=t.live_visitors, today=t.today_visitors, total=t.total_visitors)


def availability_of(profile: SiteProfile) -> Availability | None:
    text = profile.availability.strip()
    if not text:
        return None
    day = profile.availability_updated_on
    return Availability(text=text, updated=day.strftime("%Y.%m") if day else "")


def business_of(profile: SiteProfile) -> Business | None:
    business = Business(
        name=profile.business_name.strip(),
        representative=profile.representative.strip(),
        number=profile.business_number.strip(),
        address=profile.address.strip(),
    )
    return business if any(business.values()) else None


def site_business() -> Business | None:
    """The footer's business details for any public page (reading never creates the row)."""
    return business_of(SiteProfile.objects.filter(pk=1).first() or SiteProfile())


def site_availability() -> Availability | None:
    """The masthead's availability for any public page (reading never creates the row)."""
    return availability_of(SiteProfile.objects.filter(pk=1).first() or SiteProfile())


MIN_EVIDENCE = 2
REPLY_PREFIX = "영업일"


def career_years(started_on: date | None, today: date) -> int | None:
    """「N년차」 = this year - start year + 1; None without a start (or one in the future)."""
    if started_on is None or started_on.year > today.year:
        return None
    return today.year - started_on.year + 1


def evidence_of(
    profile: SiteProfile,
    portfolio: list[PortfolioCard],
    foresight: ForesightStats | None,
    today: date,
    visits: Stats | None = None,
) -> list[EvidenceItem]:
    """The hero's evidence row. An item with nothing to show is left out; fewer than two items
    leave the whole row out (one lonely number proves nothing). 「전체 방문자 · 누적」 is
    `visits.total.total_visitors` — sandcorp-metrics' own total over every site registered
    there (the same number as the masthead's 「누적 방문」); 0 or no answer leaves it out."""
    items: list[EvidenceItem] = []
    live = sum(1 for card in portfolio if card["status"] == "live")
    if live > 0:
        items.append(
            EvidenceItem(key="services", value=f"{live:,}", unit="", label="운영 중인 서비스")
        )
    if foresight is not None:
        per_day = round(foresight.articles_per_day_7d)
        items.append(
            EvidenceItem(
                key="foresight",
                value=f"{per_day:,}",
                unit="건/일",
                label="Foresight 자동 편집 기사",
            )
        )
    if visits is not None and visits.total.total_visitors > 0:
        items.append(
            EvidenceItem(
                key="visitors",
                value=f"{visits.total.total_visitors:,}",
                unit="명",
                label="전체 방문자 · 누적",
            )
        )
    promise = profile.response_promise.strip()
    if promise:
        # 「영업일 1일」 reads as the big 「1일」 with 「영업일 기준」 as its label.
        rest = promise.removeprefix(REPLY_PREFIX).strip()
        if promise.startswith(REPLY_PREFIX) and rest:
            items.append(
                EvidenceItem(key="reply", value=rest, unit="", label="첫 회신 · 영업일 기준")
            )
        else:
            items.append(EvidenceItem(key="reply", value=promise, unit="", label="첫 회신"))
    years = career_years(profile.career_started_on, today)
    if years is not None:
        items.append(
            EvidenceItem(key="career", value=f"{years:,}", unit="년차", label="웹·앱 개발 경력")
        )
    return items if len(items) >= MIN_EVIDENCE else []


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
    stats = fetch_stats()  # one read for both the masthead and the rows (cached 60 s anyway)
    portfolio = [card_of(item, stats) for item in public_items()]
    return HomePage(
        description=profile.tagline or DEFAULT_DESCRIPTION,
        data=HomeData(
            tagline=profile.tagline,
            stack=stack_of(profile.github),
            company_intro=media.resolve_document(profile.company_intro),
            contact=Contact(
                email=profile.contact_email,
                phone=profile.contact_phone,
                address=profile.address,
            ),
            portfolio=portfolio,
            posts=recent_posts(),
            tips=tips.public_cards(limit=TIP_POOL),
            shorts=shorts.public_cards(),
            news=recent_news(),
            visits=site_visits(stats),
            availability=availability_of(profile),
            business=business_of(profile),
            evidence=evidence_of(
                profile, portfolio, fetch_foresight_stats(), timezone.localdate(), stats
            ),
            services=offerings.cards(),
        ),
    )


def recent_posts(limit: int = RECENT_POSTS) -> list[blog.PostCard]:
    """The home page's newest blog posts (published only)."""
    return blog.public_cards(limit=limit)
