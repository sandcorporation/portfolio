"""What the public home page shows, read from the site profile."""

from dataclasses import dataclass
from typing import TypedDict

from content.models import SiteProfile
from documents.validation import JSON
from services.portfolio import PortfolioCard, public_cards

DEFAULT_DESCRIPTION = "샌드코퍼레이션 포트폴리오"


class Contact(TypedDict):
    email: str
    phone: str
    address: str


class HomeData(TypedDict):
    """Embedded in the shell as #page-data. Mirrored by frontend/src/home/types.ts."""

    company_intro: dict[str, JSON]
    ceo_intro: dict[str, JSON]
    contact: Contact
    portfolio: list[PortfolioCard]


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
            company_intro=profile.company_intro,
            ceo_intro=profile.ceo_intro,
            contact=Contact(
                email=profile.contact_email,
                phone=profile.contact_phone,
                address=profile.address,
            ),
            portfolio=public_cards(),
        ),
    )
