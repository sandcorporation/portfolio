"""schema.org JSON-LD for the public pages (#110). Values come from the site data only: the
profile, a portfolio card, a blog post. No claim is made that the data does not state, and there
is no contactPoint (the contact details are not meant for crawlers)."""

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from content.models import SiteProfile
from services.portfolio import PortfolioCard

CONTEXT = "https://schema.org"


def home_jsonld(
    *,
    site_url: str,
    logo: str,
    description: str,
    profile: SiteProfile,
    same_as: Sequence[str],
) -> dict[str, object]:
    """Organization + WebSite + Person (the representative) as one @graph."""
    org_id = f"{site_url}/#organization"
    name = profile.business_name.strip() or "Sandcorp"
    organization: dict[str, object] = {
        "@type": "Organization",
        "@id": org_id,
        "name": name,
        "url": f"{site_url}/",
        "logo": logo,
        "sameAs": list(same_as),
    }
    graph: list[dict[str, object]] = [
        organization,
        {
            "@type": "WebSite",
            "@id": f"{site_url}/#website",
            "name": "Sandcorp",
            "url": f"{site_url}/",
            "description": description,
            "inLanguage": "ko",
            "publisher": {"@id": org_id},
        },
    ]
    representative = profile.representative.strip()
    if representative:
        graph.append(
            {
                "@type": "Person",
                "@id": f"{site_url}/#representative",
                "name": representative,
                "jobTitle": "대표",
                "worksFor": {"@id": org_id},
            }
        )
        organization["founder"] = {"@id": f"{site_url}/#representative"}
    return {"@context": CONTEXT, "@graph": graph}


def work_jsonld(
    *,
    url: str,
    card: PortfolioCard,
    service_url: str,
    image: str,
    publisher: Mapping[str, str],
) -> dict[str, object]:
    """A portfolio item as a CreativeWork: items are not all software, and the data has no
    application category or platform to state, so SoftwareApplication would claim too much."""
    data: dict[str, object] = {
        "@context": CONTEXT,
        "@type": "CreativeWork",
        "name": card["title"],
        "url": url,
        "mainEntityOfPage": url,
        "image": image,
        "inLanguage": "ko",
        "creator": dict(publisher),
        "publisher": dict(publisher),
    }
    if card["summary"]:
        data["description"] = card["summary"]
    if card["tags"]:
        data["keywords"] = ", ".join(card["tags"])
    if urlsplit(service_url).scheme in ("http", "https"):
        data["sameAs"] = service_url
    return data
