"""The footer's business details (#104): the profile fields and what every public page carries."""

import pytest
from django.test import Client

from content.models import SiteProfile
from services.home import business_of, site_business
from tests.test_blog_pages import page_data, post
from tests.test_portfolio import make

pytestmark = pytest.mark.django_db

PATHS = ["/", "/work/demo", "/blog", "/blog/hello"]
DEFAULT = {
    "name": "샌드코프(Sandcorp)",
    "representative": "김한얼",
    "number": "752-26-01740",
    "address": "",
}


def seed() -> None:
    make("demo", 1)
    post("hello")


def test_every_public_page_carries_the_defaults_without_a_saved_profile(client: Client) -> None:
    seed()

    for path in PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert page_data(response.content.decode())["business"] == DEFAULT, path
    assert not SiteProfile.objects.exists()


def test_the_address_comes_from_the_profile_and_blank_items_are_left_empty(
    client: Client,
) -> None:
    seed()
    row = SiteProfile.load()
    row.address = " 서울 어딘가 1 "
    row.representative = ""
    row.save()

    for path in PATHS:
        business = page_data(client.get(path).content.decode())["business"]
        assert business == {**DEFAULT, "representative": "", "address": "서울 어딘가 1"}, path


def test_all_blank_is_none() -> None:
    row = SiteProfile(business_name="", representative="", business_number="", address="")

    assert business_of(row) is None
    SiteProfile.load().delete()
    assert site_business() is not None


def test_the_home_has_no_contact_section(client: Client) -> None:
    html = client.get("/").content.decode()

    assert "home-contact" not in html


def test_mcp_profile_round_trips_the_fields() -> None:
    from services.profile import ProfilePatch, get_profile, update_profile

    assert get_profile().business_number == "752-26-01740"
    saved = update_profile(ProfilePatch(business_name="새 상호", business_number=""))
    assert (saved.business_name, saved.business_number, saved.representative) == (
        "새 상호",
        "",
        "김한얼",
    )
