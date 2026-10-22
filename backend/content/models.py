"""Public content edited in Django admin. Documents are block documents (see documents/)."""

from typing import Any, ClassVar, Self

from django.core.exceptions import ValidationError
from django.db import models

from documents.validation import JSON, InvalidDocument, normalized, validate_document


def empty_document() -> dict[str, JSON]:
    return {"tabs": [{"id": "main", "title": "소개", "blocks": []}]}


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
            setattr(self, name, normalized(validate_document(getattr(self, name))))
        super().save(**kwargs)

    @classmethod
    def load(cls) -> Self:
        profile, _ = cls.objects.get_or_create(pk=1)
        return profile

    def clean(self) -> None:
        problems: dict[str, list[str]] = {}
        for name in self.DOCUMENT_FIELDS:
            try:
                setattr(self, name, normalized(validate_document(getattr(self, name))))
            except InvalidDocument as exc:
                problems[name] = [f"{e.path}: {e.reason}" for e in exc.errors]
        if problems:
            raise ValidationError(problems)


class PortfolioItem(models.Model):
    """One portfolio entry. Hidden entries keep their data; only the public views skip them."""

    slug = models.SlugField("주소", unique=True, help_text="/work/<주소> 로 열린다.")
    title = models.CharField("제목", max_length=120)
    summary = models.CharField("요약", max_length=300, blank=True, help_text="카드와 OG 설명.")
    cover_url = models.CharField(
        "대표 이미지 URL", max_length=500, blank=True, help_text="비워 둘 수 있다."
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
        self.body = normalized(validate_document(self.body))
        self.tags = ", ".join(self.tag_list())
        super().save(**kwargs)

    def clean(self) -> None:
        try:
            self.body = normalized(validate_document(self.body))
        except InvalidDocument as exc:
            raise ValidationError({"body": [f"{e.path}: {e.reason}" for e in exc.errors]}) from exc

    def tag_list(self) -> list[str]:
        return [tag for tag in (t.strip() for t in self.tags.split(",")) if tag]
