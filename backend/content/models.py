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
