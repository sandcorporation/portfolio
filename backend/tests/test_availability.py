"""The masthead's availability (#88): the profile fields and what every public page carries."""

from datetime import date

import pytest
from django.test import Client
from django.utils import timezone

from content.models import SiteProfile
from services.home import availability_of
from tests.test_blog_pages import page_data, post
from tests.test_portfolio import make

pytestmark = pytest.mark.django_db


def set_profile(**fields: object) -> None:
    row = SiteProfile.load()
    for name, value in fields.items():
        setattr(row, name, value)
    row.save()


def test_a_date_is_filled_with_today_when_availability_is_saved_without_one() -> None:
    set_profile(availability="새 프로젝트 받는 중")

    assert SiteProfile.load().availability_updated_on == timezone.localdate()


def test_a_given_date_is_kept_and_no_text_means_no_date() -> None:
    set_profile(availability="새 프로젝트 받는 중", availability_updated_on=date(2026, 3, 9))
    assert SiteProfile.load().availability_updated_on == date(2026, 3, 9)

    set_profile(availability="", availability_updated_on=None)
    assert SiteProfile.load().availability_updated_on is None


def test_the_month_is_year_dot_two_digit_month() -> None:
    row = SiteProfile(
        availability=" 새 프로젝트 받는 중 ", availability_updated_on=date(2026, 3, 9)
    )

    assert availability_of(row) == {"text": "새 프로젝트 받는 중", "updated": "2026.03"}


def test_blank_text_is_no_availability_even_with_a_date() -> None:
    assert (
        availability_of(SiteProfile(availability="  ", availability_updated_on=date.today()))
        is None
    )


def test_every_public_page_carries_it_in_the_shell_data(client: Client) -> None:
    set_profile(availability="새 프로젝트 받는 중", availability_updated_on=date(2026, 10, 23))
    make("demo", 1)
    post("hello")
    expected = {"text": "새 프로젝트 받는 중", "updated": "2026.10"}

    for path in ["/", "/work/demo", "/blog", "/blog/hello"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert page_data(response.content.decode())["availability"] == expected, path


def test_without_it_every_public_page_says_none(client: Client) -> None:
    make("demo", 1)
    post("hello")

    for path in ["/", "/work/demo", "/blog", "/blog/hello"]:
        assert page_data(client.get(path).content.decode())["availability"] is None, path


def test_the_profile_row_is_not_created_by_reading(client: Client) -> None:
    client.get("/")
    client.get("/blog")

    assert not SiteProfile.objects.exists()
