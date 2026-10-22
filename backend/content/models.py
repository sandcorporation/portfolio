"""Public content edited in Django admin. Documents are block documents (see documents/)."""

import secrets
from typing import Any, ClassVar, Self

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from documents.blocks import Document, GalleryBlock
from documents.validation import (
    JSON,
    DocumentError,
    InvalidDocument,
    normalized,
    validate_document,
)


def empty_document() -> dict[str, JSON]:
    return {"tabs": [{"id": "main", "title": "소개", "blocks": []}]}


class Media(models.Model):
    """An uploaded file in object storage. `uploaded_at` is set once the object is confirmed there.

    Blocks and covers may only reference media that is complete (and, for now, public).
    """

    is_public = models.BooleanField("공개", default=True)
    object_key = models.CharField("객체 키", max_length=300, unique=True)
    content_type = models.CharField("MIME", max_length=100)
    size = models.PositiveBigIntegerField("크기(바이트)")
    original_filename = models.CharField("원래 파일명", max_length=255)
    uploaded_at = models.DateTimeField("업로드 완료 시각", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "미디어"
        verbose_name_plural = "미디어"
        ordering = ("-id",)

    def __str__(self) -> str:
        return self.original_filename

    @property
    def is_complete(self) -> bool:
        return self.uploaded_at is not None


def media_problems(document: Document) -> list[DocumentError]:
    """Gallery images must point at media that exists, is public and finished uploading."""
    wanted: list[tuple[str, int]] = []
    for t, tab in enumerate(document.tabs):
        for b, block in enumerate(tab.blocks):
            if isinstance(block, GalleryBlock):
                for i, image in enumerate(block.images):
                    wanted.append((f"tabs[{t}].blocks[{b}].images[{i}].media_id", image.media_id))
    found = {m.pk: m for m in Media.objects.filter(pk__in={mid for _, mid in wanted})}
    errors: list[DocumentError] = []
    for path, media_id in wanted:
        media = found.get(media_id)
        if media is None:
            errors.append(DocumentError(path, f"미디어 {media_id}가 없습니다"))
        elif not media.is_complete:
            errors.append(DocumentError(path, f"미디어 {media_id}는 업로드가 끝나지 않았습니다"))
        elif not media.is_public:
            errors.append(DocumentError(path, f"미디어 {media_id}는 공개 미디어가 아닙니다"))
    return errors


def stored_document(data: object) -> dict[str, JSON]:
    """Validate a document for storage: schema, media references, then the normalized form."""
    document = validate_document(data)
    errors = media_problems(document)
    if errors:
        raise InvalidDocument(errors)
    # Resolved URLs are computed when serving; a stored one would go stale.
    for tab in document.tabs:
        for block in tab.blocks:
            if isinstance(block, GalleryBlock):
                for image in block.images:
                    image.url = None
    return normalized(document)


class SiteProfile(models.Model):
    """The single site profile: what the public home page shows."""

    DOCUMENT_FIELDS: ClassVar[tuple[str, ...]] = ("company_intro", "ceo_intro")

    tagline = models.CharField(
        "한 줄 소개",
        max_length=160,
        blank=True,
        help_text="홈의 description·OG 설명으로 쓴다.",
    )
    company_intro = models.JSONField("회사 소개 문서", default=empty_document)
    ceo_intro = models.JSONField("대표 소개 문서", default=empty_document)
    contact_email = models.EmailField("연락 이메일", blank=True)
    contact_phone = models.CharField("연락 전화", max_length=40, blank=True)
    address = models.CharField("주소", max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "사이트 프로필"
        verbose_name_plural = "사이트 프로필"

    def __str__(self) -> str:
        return "사이트 프로필"

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        # Every writer (admin, API, MCP) stores only valid, normalized documents.
        self.pk = 1
        for name in self.DOCUMENT_FIELDS:
            setattr(self, name, stored_document(getattr(self, name)))
        super().save(**kwargs)

    @classmethod
    def load(cls) -> Self:
        profile, _ = cls.objects.get_or_create(pk=1)
        return profile

    def clean(self) -> None:
        problems: dict[str, list[str]] = {}
        for name in self.DOCUMENT_FIELDS:
            try:
                setattr(self, name, stored_document(getattr(self, name)))
            except InvalidDocument as exc:
                problems[name] = [f"{e.path}: {e.reason}" for e in exc.errors]
        if problems:
            raise ValidationError(problems)


class PortfolioItem(models.Model):
    """One portfolio entry. Hidden entries keep their data; only the public views skip them."""

    slug = models.SlugField("주소", unique=True, help_text="/work/<주소> 로 열린다.")
    title = models.CharField("제목", max_length=120)
    summary = models.CharField("요약", max_length=300, blank=True, help_text="카드와 OG 설명.")
    cover = models.ForeignKey(
        Media,
        verbose_name="대표 이미지",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"is_public": True, "uploaded_at__isnull": False},
        help_text="업로드가 끝난 공개 미디어. 비워 둘 수 있다.",
    )
    tags = models.CharField("태그", max_length=200, blank=True, help_text="쉼표로 구분.")
    period = models.CharField("기간", max_length=60, blank=True, help_text="예: 2025.03 ~ 2025.08")
    is_public = models.BooleanField("공개", default=True)
    sort_order = models.IntegerField("정렬 순서", default=0, help_text="작을수록 먼저.")
    body = models.JSONField("본문 문서", default=empty_document)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "포트폴리오 항목"
        verbose_name_plural = "포트폴리오 항목"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.title

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        self.check_cover()
        self.body = stored_document(self.body)
        self.tags = ", ".join(self.tag_list())
        super().save(**kwargs)

    def check_cover(self) -> None:
        if self.cover is not None and not (self.cover.is_public and self.cover.is_complete):
            raise ValidationError({"cover": "업로드가 끝난 공개 미디어만 쓸 수 있습니다."})

    def clean(self) -> None:
        self.check_cover()
        try:
            self.body = stored_document(self.body)
        except InvalidDocument as exc:
            raise ValidationError({"body": [f"{e.path}: {e.reason}" for e in exc.errors]}) from exc

    def tag_list(self) -> list[str]:
        return [tag for tag in (t.strip() for t in self.tags.split(",")) if tag]


CLIENT_CODE_PATTERN = r"^[A-Z]{2,6}$"


class Client(models.Model):
    """A customer proposals are written for. The code is its short, unique handle."""

    name = models.CharField("고객명", max_length=120)
    code = models.CharField(
        "고객코드",
        max_length=6,
        unique=True,
        validators=[RegexValidator(CLIENT_CODE_PATTERN, "대문자 2~6자여야 합니다.")],
        help_text="대문자 2~6자, 겹칠 수 없다. 예: NEXT",
    )
    contact_title = models.CharField(
        "담당자 호칭", max_length=80, blank=True, help_text="표지에 쓴다. 예: 홍길순 대표님"
    )
    memo = models.TextField("메모", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "고객"
        verbose_name_plural = "고객"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


def default_proposal_document() -> dict[str, JSON]:
    """A new proposal starts with the two tabs every proposal has."""
    return {
        "tabs": [
            {"id": "estimate", "title": "견적 제안", "blocks": []},
            {"id": "company", "title": "회사소개·수행사례", "blocks": []},
        ]
    }


def new_proposal_slug() -> str:
    """An unguessable URL part (128 random bits, URL-safe)."""
    return secrets.token_urlsafe(16)


class Proposal(models.Model):
    """A quote written for a client. Drafts are visible only through signed previews."""

    class Status(models.TextChoices):
        DRAFT = "draft", "초안"
        PUBLISHED = "published", "발행됨"
        REVOKED = "revoked", "회수됨"

    client = models.ForeignKey(
        Client, verbose_name="고객", on_delete=models.PROTECT, related_name="proposals"
    )
    title = models.CharField("제목", max_length=160)
    subtitle = models.CharField("부제", max_length=200, blank=True)
    slug = models.SlugField("주소", unique=True, default=new_proposal_slug, editable=False)
    document = models.JSONField("제안서 문서", default=default_proposal_document)
    quote_date = models.DateField("견적 기준일")
    valid_until = models.DateField("유효기간", null=True, blank=True, help_text="이 날까지 유효.")
    status = models.CharField("상태", max_length=12, choices=Status, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "제안서"
        verbose_name_plural = "제안서"
        ordering = ("-id",)

    def __str__(self) -> str:
        return f"{self.client.code} · {self.title}"

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        self.document = stored_document(self.document)
        super().save(**kwargs)

    def clean(self) -> None:
        try:
            self.document = stored_document(self.document)
        except InvalidDocument as exc:
            raise ValidationError(
                {"document": [f"{e.path}: {e.reason}" for e in exc.errors]}
            ) from exc


class Inquiry(models.Model):
    """A message left on the home form (or relayed by another Sandcorp site). `handled_at` is set
    once the owner has dealt with it; until then it counts as unhandled."""

    class Kind(models.TextChoices):
        INQUIRY = "문의", "문의"
        PROPOSAL = "제안", "제안"

    site = models.CharField("사이트", max_length=40, default="portfolio")
    kind = models.CharField("구분", max_length=4, choices=Kind, default=Kind.INQUIRY)
    name = models.CharField("이름", max_length=80)
    company = models.CharField("회사", max_length=120, blank=True)
    contact = models.CharField("연락처", max_length=200)
    message = models.TextField("내용")
    created_at = models.DateTimeField("접수", auto_now_add=True)
    handled_at = models.DateTimeField("처리 완료", null=True, blank=True)

    class Meta:
        verbose_name = "문의"
        verbose_name_plural = "문의"
        ordering = ("-id",)

    def __str__(self) -> str:
        return f"[{self.site}·{self.kind}] {self.name}"
