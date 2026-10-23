from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html

from adapters.storage import StorageNotConfigured, get_storage
from content.models import (
    BlogPost,
    Client,
    Inquiry,
    Media,
    PdfJob,
    PortfolioItem,
    Proposal,
    ProposalEvent,
    ProposalRevision,
    SiteProfile,
)
from services import inquiries as inquiry_service
from services import media as media_service
from services import pdf as pdf_service
from services import proposals as proposal_service
from services import publishing
from services.errors import ServiceError

# ModelAdmin is generic only in django-stubs; at runtime it is not subscriptable.
if TYPE_CHECKING:
    _ProfileAdmin = admin.ModelAdmin[SiteProfile]
else:
    _ProfileAdmin = admin.ModelAdmin


@admin.register(SiteProfile)
class SiteProfileAdmin(_ProfileAdmin):
    """A singleton: the list page jumps straight to the one profile."""

    fields = (
        "tagline",
        "company_intro",
        "ceo_intro",
        "contact_email",
        "contact_phone",
        "address",
        "availability",
        "availability_updated_on",
        "github",
    )

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
    list_display = ("title", "slug", "is_public", "sort_order", "period", "status")
    list_editable = ("is_public", "sort_order")
    prepopulated_fields = {"slug": ("title",)}
    fields = (
        "title",
        "slug",
        "summary",
        "cover",
        "tags",
        "period",
        "status",
        "outcome",
        "service_url",
        "metrics_site_key",
        "is_public",
        "sort_order",
        "body",
    )


if TYPE_CHECKING:
    _PostAdmin = admin.ModelAdmin[BlogPost]
else:
    _PostAdmin = admin.ModelAdmin


@admin.register(BlogPost)
class BlogPostAdmin(_PostAdmin):
    """Posts are usually written through MCP; here the same fields, the document as JSON."""

    list_display = ("title", "status", "published_at", "tags", "slug")
    list_filter = ("status",)
    search_fields = ("title", "slug", "tags")
    prepopulated_fields = {"slug": ("title",)}
    fields = ("title", "slug", "summary", "cover", "tags", "status", "published_at", "body")


if TYPE_CHECKING:
    _MediaForm = forms.ModelForm[Media]
else:
    _MediaForm = forms.ModelForm


class MediaUploadForm(_MediaForm):
    """Add: pick a file and visibility. The server stores it through services.media.upload."""

    file = forms.FileField(
        label="파일",
        help_text=(
            "이미지(JPEG·PNG·WebP·GIF·AVIF) 20MB, 오디오(MP3·M4A·AAC·WAV·OGG·FLAC)·"
            "영상(MP4·WebM·MOV) 100MB까지. 제안서 시연 자료는 공개를 끈다."
        ),
    )

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
        "used_by",
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
        drafts = media_service.usage_of([obj.pk])[obj.pk].drafts
        media_service.delete_media(obj)
        if drafts:
            self.message_user(
                request,
                f"초안 제안서 {', '.join(drafts)}에서 이 미디어가 더 이상 제공되지 않습니다.",
                messages.WARNING,
            )

    def delete_view(
        self, request: HttpRequest, object_id: str, extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        obj = self.get_object(request, object_id)
        if obj is not None:
            usage = media_service.usage_of([obj.pk])[obj.pk]
            if usage.blocks_delete:
                self.message_user(request, usage.refusal(), messages.ERROR)
                return HttpResponseRedirect(reverse("admin:content_media_change", args=[obj.pk]))
        return super().delete_view(request, object_id, extra_context)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Media]) -> None:
        """Bulk delete goes through the service too (bucket objects included); media still in use
        stays and is named in an error."""
        for media in queryset:
            try:
                media_service.delete_media(media)
            except media_service.MediaInUse as exc:
                self.message_user(request, f"{media}: {exc.errors[0].reason}", messages.ERROR)
            except StorageNotConfigured as exc:
                self.message_user(request, f"{media}: {exc}", messages.ERROR)

    @admin.display(description="사용처")
    def used_by(self, obj: Media) -> str:
        if obj.pk is None:
            return "-"
        usage = media_service.usage_of([obj.pk])[obj.pk]
        lines = [
            ("발행 리비전", usage.revisions),
            ("초안 제안서", usage.drafts),
            ("공개 페이지", usage.pages),
        ]
        shown = [f"{name}: {', '.join(items)}" for name, items in lines if items]
        return " / ".join(shown) or "사용 안 함"

    @admin.display(description="미리보기")
    def preview(self, obj: Media) -> str:
        url = media_service.public_url(obj)
        return format_html('<img src="{}" alt="" style="max-width:320px">', url) if url else "-"


if TYPE_CHECKING:
    _ClientAdmin = admin.ModelAdmin[Client]
    _ProposalAdmin = admin.ModelAdmin[Proposal]
    _RevisionAdmin = admin.ModelAdmin[ProposalRevision]
    _RevisionInline = admin.TabularInline[ProposalRevision, Proposal]
    _EventInline = admin.TabularInline[ProposalEvent, Proposal]
    _EventAdmin = admin.ModelAdmin[ProposalEvent]
else:
    _ClientAdmin = admin.ModelAdmin
    _ProposalAdmin = admin.ModelAdmin
    _RevisionAdmin = admin.ModelAdmin
    _RevisionInline = admin.TabularInline
    _EventInline = admin.TabularInline
    _EventAdmin = admin.ModelAdmin


@admin.register(Client)
class ClientAdmin(_ClientAdmin):
    list_display = ("code", "name", "contact_title")
    search_fields = ("code", "name")
    fields = ("code", "name", "contact_title", "memo")

    def get_readonly_fields(
        self, request: HttpRequest, obj: Client | None = None
    ) -> tuple[str, ...]:
        return ("code",) if obj else ()  # the code is the handle proposals and tools use


class RevisionInline(_RevisionInline):
    """Revisions are frozen: listed here, opened read-only on their own page."""

    model = ProposalRevision
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("number", "doc_number", "published_at", "valid_until")
    readonly_fields = fields
    ordering = ("-number",)

    def has_add_permission(self, request: HttpRequest, obj: Proposal | None = None) -> bool:
        return False


class EventInline(_EventInline):
    """The customer's trail on this proposal, oldest first. Read-only."""

    model = ProposalEvent
    extra = 0
    can_delete = False
    verbose_name_plural = "열람 기록 (시간 순)"
    fields = ("created_at", "kind", "revision", "tab_id", "ip", "user_agent")
    readonly_fields = fields
    ordering = ("created_at", "id")

    def has_add_permission(self, request: HttpRequest, obj: Proposal | None = None) -> bool:
        return False


@admin.register(Proposal)
class ProposalAdmin(_ProposalAdmin):
    list_display = ("title", "client", "status", "latest_doc_number", "quote_date", "preview_link")
    list_filter = ("status", "client")
    search_fields = ("title", "client__name", "client__code")
    fields = (
        "client",
        "title",
        "subtitle",
        "quote_date",
        "valid_until",
        "status",
        "slug",
        "preview_link",
        "document",
    )
    readonly_fields = ("status", "slug", "preview_link")
    inlines = (RevisionInline, EventInline)
    actions = (
        "publish",
        "publish_with_code",
        "reissue_code",
        "reissue_with_code",
        "revoke",
        "duplicate",
    )

    def get_readonly_fields(
        self, request: HttpRequest, obj: Proposal | None = None
    ) -> tuple[str, ...]:
        if obj is not None and obj.status == Proposal.Status.REVOKED:
            return self.fields  # revoked for good; duplicate it to keep working
        return tuple(self.readonly_fields)

    def get_urls(self) -> list[URLPattern]:
        # Before the model admin's own `<id>/` catch-all.
        mine = path(
            "<int:object_id>/preview/",
            self.admin_site.admin_view(self.preview),
            name="content_proposal_preview",
        )
        return [mine, *super().get_urls()]

    def preview(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """Issue a fresh signed link and go there, so a stale admin page never holds a dead one."""
        found = Proposal.objects.filter(pk=object_id).first()
        if found is None:
            raise Http404
        return HttpResponseRedirect(proposal_service.issue_preview_url(found.slug).url)

    @admin.display(description="미리보기")
    def preview_link(self, obj: Proposal) -> str:
        if obj.pk is None:
            return "-"
        url = reverse("admin:content_proposal_preview", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">미리보기</a>', url)

    @admin.display(description="최신 문서번호")
    def latest_doc_number(self, obj: Proposal) -> str:
        latest = publishing.latest_revision(obj)
        return f"{latest.doc_number} (v{latest.number})" if latest else "-"

    def _codes_page(
        self,
        request: HttpRequest,
        title: str,
        done: list[str],
        failed: list[str],
        codes: list[dict[str, str]],
    ) -> HttpResponse:
        """Render the result in this response itself. A message would be stored (cookie or
        session) until the next page, and the plain codes must not be kept anywhere."""
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "done": done,
            "failed": failed,
            "codes": codes,
            "back_url": reverse("admin:content_proposal_changelist"),
        }
        response = TemplateResponse(request, "admin/proposal_access_codes.html", context)
        response["Cache-Control"] = "no-store"
        return response

    @admin.action(description="발행 (새 리비전)")
    def publish(self, request: HttpRequest, queryset: QuerySet[Proposal]) -> HttpResponse:
        done: list[str] = []
        failed: list[str] = []
        codes: list[dict[str, str]] = []
        for p in queryset:
            try:
                result = publishing.publish(p.slug)
            except ServiceError as exc:
                failed.append(f"{p.title}: {exc}")
                continue
            r = result.revision
            done.append(f"{p.title}: v{r.number} {r.doc_number} 발행")
            if result.access_code:
                codes.append({"title": p.title, "url": f"/p/{p.slug}", "code": result.access_code})
        return self._codes_page(request, "발행", done, failed, codes)

    @admin.action(description="접근 코드 재발급 (기존 세션 끊김)")
    def reissue_code(self, request: HttpRequest, queryset: QuerySet[Proposal]) -> HttpResponse:
        done: list[str] = []
        failed: list[str] = []
        codes: list[dict[str, str]] = []
        for p in queryset:
            try:
                issued = publishing.reissue_access_code(p.slug)
            except ServiceError as exc:
                failed.append(f"{p.title}: {exc}")
                continue
            done.append(f"{p.title}: 접근 코드를 새로 만들었습니다")
            codes.append({"title": p.title, "url": f"/p/{p.slug}", "code": issued.access_code})
        return self._codes_page(request, "접근 코드 재발급", done, failed, codes)

    def _ask_codes(
        self, request: HttpRequest, queryset: QuerySet[Proposal], action: str, title: str
    ) -> HttpResponse:
        """The step before: one optional code field per selected proposal (empty = generated)."""
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "action": action,
            "proposals": list(queryset),
            "back_url": reverse("admin:content_proposal_changelist"),
        }
        response = TemplateResponse(request, "admin/proposal_choose_codes.html", context)
        response["Cache-Control"] = "no-store"
        return response

    @admin.action(description="발행 (접근 코드 직접 정하기)")
    def publish_with_code(self, request: HttpRequest, queryset: QuerySet[Proposal]) -> HttpResponse:
        if "apply" not in request.POST:
            return self._ask_codes(
                request, queryset, "publish_with_code", "발행 — 접근 코드 정하기"
            )
        done: list[str] = []
        failed: list[str] = []
        codes: list[dict[str, str]] = []
        for p in queryset:
            try:
                result = publishing.publish(p.slug, request.POST.get(f"code_{p.pk}", ""))
            except ServiceError as exc:
                failed.append(f"{p.title}: {exc}")
                continue
            r = result.revision
            done.append(f"{p.title}: v{r.number} {r.doc_number} 발행")
            if result.access_code:
                codes.append({"title": p.title, "url": f"/p/{p.slug}", "code": result.access_code})
        return self._codes_page(request, "발행", done, failed, codes)

    @admin.action(description="접근 코드 재발급 (직접 정하기, 기존 세션 끊김)")
    def reissue_with_code(self, request: HttpRequest, queryset: QuerySet[Proposal]) -> HttpResponse:
        if "apply" not in request.POST:
            return self._ask_codes(
                request, queryset, "reissue_with_code", "접근 코드 재발급 — 코드 정하기"
            )
        done: list[str] = []
        failed: list[str] = []
        codes: list[dict[str, str]] = []
        for p in queryset:
            try:
                issued = publishing.reissue_access_code(
                    p.slug, request.POST.get(f"code_{p.pk}", "")
                )
            except ServiceError as exc:
                failed.append(f"{p.title}: {exc}")
                continue
            done.append(f"{p.title}: 접근 코드를 새로 만들었습니다")
            codes.append({"title": p.title, "url": f"/p/{p.slug}", "code": issued.access_code})
        return self._codes_page(request, "접근 코드 재발급", done, failed, codes)

    @admin.action(description="회수 (고객 주소를 닫는다, 되돌릴 수 없음)")
    def revoke(self, request: HttpRequest, queryset: QuerySet[Proposal]) -> None:
        for p in queryset:
            try:
                publishing.revoke(p.slug)
            except ServiceError as exc:
                self.message_user(request, f"{p.title}: {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{p.title}: 회수했습니다")

    @admin.action(description="복제 (새 주소의 초안으로)")
    def duplicate(self, request: HttpRequest, queryset: QuerySet[Proposal]) -> None:
        for source in queryset:
            try:
                proposal_service.duplicate_proposal(source.slug)
            except ServiceError as exc:
                self.message_user(request, str(exc), messages.ERROR)
                return
        self.message_user(request, f"{queryset.count()}건을 초안으로 복제했습니다.")


@admin.register(ProposalRevision)
class ProposalRevisionAdmin(_RevisionAdmin):
    """Read-only: a revision is what the customer was sent."""

    list_display = ("doc_number", "proposal", "number", "published_at", "valid_until", "pdf_state")
    list_filter = ("client", "pdf__status")
    actions = ("retry_pdf",)
    search_fields = ("doc_number", "proposal__title")
    fields = (
        "proposal",
        "number",
        "doc_number",
        "published_at",
        "recipient",
        "title",
        "subtitle",
        "quote_date",
        "valid_until",
        "pdf_state",
        "pdf_detail",
        "document",
    )
    readonly_fields = fields

    @admin.display(description="PDF")
    def pdf_state(self, obj: ProposalRevision) -> str:
        job = PdfJob.objects.filter(revision=obj).first()
        return job.get_status_display() if job else "없음"

    @admin.display(description="PDF 내용")
    def pdf_detail(self, obj: ProposalRevision) -> str:
        job = PdfJob.objects.filter(revision=obj).first()
        if job is None:
            return "PDF 작업이 없습니다(이전 발행). 「PDF 다시 만들기」로 만듭니다."
        if job.status == PdfJob.Status.DONE:
            try:
                url = pdf_service.download_url(job, storage=get_storage())
            except StorageNotConfigured:
                return f"완료 ({job.size or 0:,} 바이트) — 저장소 설정이 없어 내려받을 수 없음"
            return format_html(
                '<a href="{}">{}</a> ({} 바이트)',
                url,
                pdf_service.download_name(obj),
                f"{job.size or 0:,}",
            )
        return f"{job.get_status_display()} · 시도 {job.attempts}회" + (
            f" · 오류: {job.error}" if job.error else ""
        )

    @admin.action(description="PDF 다시 만들기")
    def retry_pdf(self, request: HttpRequest, queryset: QuerySet[ProposalRevision]) -> None:
        done = 0
        for revision in queryset:
            try:
                pdf_service.retry(revision)
            except ServiceError as e:
                self.message_user(request, f"{revision.doc_number}: {e}", messages.WARNING)
            else:
                done += 1
        if done:
            self.message_user(
                request, f"PDF {done}건을 다시 만들도록 맡겼습니다. 워커가 곧 처리합니다."
            )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: ProposalRevision | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: ProposalRevision | None = None
    ) -> bool:
        return False


if TYPE_CHECKING:
    _InquiryAdmin = admin.ModelAdmin[Inquiry]
else:
    _InquiryAdmin = admin.ModelAdmin


class HandledFilter(admin.SimpleListFilter):
    title = "처리 상태"
    parameter_name = "handled"

    def lookups(
        self, request: HttpRequest, model_admin: "admin.ModelAdmin[Inquiry]"
    ) -> list[tuple[str, str]]:
        return [("no", "미처리"), ("yes", "처리 완료")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Inquiry]) -> QuerySet[Inquiry]:
        if self.value() == "no":
            return queryset.filter(handled_at__isnull=True)
        if self.value() == "yes":
            return queryset.filter(handled_at__isnull=False)
        return queryset


@admin.register(Inquiry)
class InquiryAdmin(_InquiryAdmin):
    list_display = ("created_at", "site", "kind", "name", "company", "contact", "handled_at")
    list_filter = (HandledFilter, "site", "kind")
    search_fields = ("name", "company", "contact", "message")
    readonly_fields = ("site", "kind", "name", "company", "contact", "message", "created_at")
    fields = (*readonly_fields, "handled_at")
    actions = ("mark_done",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.action(description="처리 완료로 표시")
    def mark_done(self, request: HttpRequest, queryset: QuerySet[Inquiry]) -> None:
        ids = list(queryset.values_list("pk", flat=True))
        for inquiry_id in ids:
            inquiry_service.mark_handled(inquiry_id)
        self.message_user(request, f"{len(ids)}건을 처리 완료로 표시했습니다.", messages.SUCCESS)


@admin.register(ProposalEvent)
class ProposalEventAdmin(_EventAdmin):
    """All customers' events, newest first. Read-only."""

    list_display = ("created_at", "proposal", "kind", "revision", "tab_id", "ip")
    list_filter = ("kind", "proposal__client")
    search_fields = ("proposal__title", "proposal__client__name", "ip")
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    fields = ("created_at", "proposal", "revision", "kind", "tab_id", "ip", "user_agent", "first")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: ProposalEvent | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: ProposalEvent | None = None) -> bool:
        return False
