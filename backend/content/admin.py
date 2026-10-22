from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse

from content.models import PortfolioItem, SiteProfile

# ModelAdmin is generic only in django-stubs; at runtime it is not subscriptable.
if TYPE_CHECKING:
    _ProfileAdmin = admin.ModelAdmin[SiteProfile]
else:
    _ProfileAdmin = admin.ModelAdmin


@admin.register(SiteProfile)
class SiteProfileAdmin(_ProfileAdmin):
    """A singleton: the list page jumps straight to the one profile."""

    fields = ("tagline", "company_intro", "ceo_intro", "contact_email", "contact_phone", "address")

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, object] | None = None
    ) -> HttpResponse:
        profile = SiteProfile.load()
        return HttpResponseRedirect(reverse("admin:content_siteprofile_change", args=[profile.pk]))

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: SiteProfile | None = None) -> bool:
        return False


if TYPE_CHECKING:
    _ItemAdmin = admin.ModelAdmin[PortfolioItem]
else:
    _ItemAdmin = admin.ModelAdmin


@admin.register(PortfolioItem)
class PortfolioItemAdmin(_ItemAdmin):
    list_display = ("title", "slug", "is_public", "sort_order", "period")
    list_editable = ("is_public", "sort_order")
    prepopulated_fields = {"slug": ("title",)}
    fields = (
        "title",
        "slug",
        "summary",
        "cover_url",
        "tags",
        "period",
        "is_public",
        "sort_order",
        "body",
    )
