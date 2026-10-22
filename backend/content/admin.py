from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from adapters.storage import StorageNotConfigured, get_storage
from content.models import Media, PortfolioItem, SiteProfile
from services import media as media_service

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
        "cover",
        "tags",
        "period",
        "is_public",
        "sort_order",
        "body",
    )


if TYPE_CHECKING:
    _MediaForm = forms.ModelForm[Media]
else:
    _MediaForm = forms.ModelForm


class MediaUploadForm(_MediaForm):
    """Add: pick a file and visibility. The server stores it through services.media.upload."""

    file = forms.FileField(label="파일", help_text="JPEG·PNG·WebP·GIF·AVIF, 20MB까지.")

    class Meta:
        model = Media
        fields = ("file", "is_public")

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # Any: forwarded to ModelForm
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # the change page edits nothing; the file is only for adding
            self.fields["file"].required = False

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        upload = cleaned.get("file")
        if upload is not None:
            try:
                get_storage()
                media_service.validate_upload(upload.content_type or "", upload.size or 0)
            except (StorageNotConfigured, media_service.InvalidUpload) as exc:
                raise forms.ValidationError(str(exc)) from exc
        return cleaned


if TYPE_CHECKING:
    _MediaAdmin = admin.ModelAdmin[Media]
else:
    _MediaAdmin = admin.ModelAdmin


@admin.register(Media)
class MediaAdmin(_MediaAdmin):
    list_display = ("original_filename", "is_public", "content_type", "size", "uploaded_at")
    list_filter = ("is_public",)
    readonly_fields = (
        "preview",
        "is_public",
        "original_filename",
        "content_type",
        "size",
        "object_key",
        "uploaded_at",
        "created_at",
    )
    fields = readonly_fields
    search_fields = ("original_filename",)
    form = MediaUploadForm

    def get_fields(self, request: HttpRequest, obj: Media | None = None) -> tuple[str, ...]:
        return ("file", "is_public") if obj is None else tuple(self.fields)

    def get_readonly_fields(
        self, request: HttpRequest, obj: Media | None = None
    ) -> tuple[str, ...]:
        return () if obj is None else tuple(self.readonly_fields)

    def save_model(self, request: HttpRequest, obj: Media, form: _MediaForm, change: bool) -> None:
        if change:
            return
        upload = form.cleaned_data["file"]
        obj.pk = media_service.upload(
            upload.name or "file",
            upload.content_type,
            upload.read(),
            is_public=form.cleaned_data["is_public"],
        ).pk
        obj.refresh_from_db()

    def has_change_permission(self, request: HttpRequest, obj: Media | None = None) -> bool:
        return True

    def delete_model(self, request: HttpRequest, obj: Media) -> None:
        media_service.delete_media(obj)

    @admin.display(description="미리보기")
    def preview(self, obj: Media) -> str:
        url = media_service.public_url(obj)
        return format_html('<img src="{}" alt="" style="max-width:320px">', url) if url else "-"
