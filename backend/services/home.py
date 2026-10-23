"""What the public home page shows, read from the site profile."""

from dataclasses import dataclass
from typing import TypedDict

from content.models import SiteProfile
from documents.validation import JSON
from services import blog, media
from services.portfolio import PortfolioCard, public_cards

RECENT_POSTS = 3

DEFAULT_DESCRIPTION = "샌드코프 포트폴리오"


class Contact(TypedDict):
    email: str
    phone: str
    address: str


class HomeData(TypedDict):
    """Embedded in the shell as #page-data. Mirrored by frontend/src/home/types.ts."""

    tagline: str
    stack: list[str]  # the GitHub profile's stack badges: the hero's tag line
    company_intro: dict[str, JSON]
    ceo_intro: dict[str, JSON]
    contact: Contact
    portfolio: list[PortfolioCard]


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
        ),
    )


def recent_posts(limit: int = RECENT_POSTS) -> list[blog.PostCard]:
    """The home page's newest blog posts (published only); #75 shows them."""
    return blog.public_cards(limit=limit)
