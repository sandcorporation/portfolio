"""Public content edited in Django admin. Documents are block documents (see documents/)."""

import secrets
from typing import Any, ClassVar, Literal, Self

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from content.github_profile import InvalidGithubProfile, stored_github
from documents.blocks import AudioCompareBlock, CaseRefBlock, Document, GalleryBlock, VideoBlock
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

    Blocks and covers may only reference media that is complete; private media only from
    proposal documents (see `media_problems`).
    """

    is_public = models.BooleanField("공개", default=True)
    # uuid hex + extension; 255 keeps the unique index within MySQL's limit (mysql.W003).
    object_key = models.CharField("객체 키", max_length=255, unique=True)
    content_type = models.CharField("MIME", max_length=100)
    size = models.PositiveBigIntegerField("크기(바이트)")
    original_filename = models.CharField("원래 파일명", max_length=255)
    uploaded_at = models.DateTimeField("업로드 완료 시각", null=True, blank=True)
    # Pixel size of an image, read from its header (#123); null for other kinds or when unknown.
    width = models.PositiveIntegerField("가로(px)", null=True, blank=True)
    height = models.PositiveIntegerField("세로(px)", null=True, blank=True)
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


MediaKind = Literal["image", "audio", "video"]
_KINDS: dict[str, MediaKind] = {"image": "image", "audio": "audio", "video": "video"}
_KIND_NAMES: dict[MediaKind, str] = {"image": "이미지가", "audio": "오디오가", "video": "영상이"}


def media_kind(content_type: str) -> MediaKind | None:
    return _KINDS.get(content_type.split("/", 1)[0])


def _media_wanted(document: Document) -> list[tuple[str, int, MediaKind]]:
    """Every media reference in the document: (path, media id, the kind it must be)."""
    wanted: list[tuple[str, int, MediaKind]] = []
    for t, tab in enumerate(document.tabs):
        for b, block in enumerate(tab.blocks):
            at = f"tabs[{t}].blocks[{b}]"
            if isinstance(block, GalleryBlock):
                for i, image in enumerate(block.images):
                    wanted.append((f"{at}.images[{i}].media_id", image.media_id, "image"))
            elif isinstance(block, AudioCompareBlock):
                wanted.append((f"{at}.original.media_id", block.original.media_id, "audio"))
                for i, track in enumerate(block.tracks):
                    wanted.append((f"{at}.tracks[{i}].media_id", track.media_id, "audio"))
            elif isinstance(block, VideoBlock):
                wanted.append((f"{at}.media_id", block.media_id, "video"))
                if block.poster_media_id is not None:
                    wanted.append((f"{at}.poster_media_id", block.poster_media_id, "image"))
    return wanted


def media_problems(document: Document, *, allow_private: bool = False) -> list[DocumentError]:
    """Media references must point at finished media of the right kind. Private media only where
    `allow_private` (proposal documents, served behind the customer session)."""
    wanted = _media_wanted(document)
    found = {m.pk: m for m in Media.objects.filter(pk__in={mid for _, mid, _ in wanted})}
    errors: list[DocumentError] = []
    for path, media_id, kind in wanted:
        media = found.get(media_id)
        if media is None:
            errors.append(DocumentError(path, f"미디어 {media_id}가 없습니다"))
        elif not media.is_complete:
            errors.append(DocumentError(path, f"미디어 {media_id}는 업로드가 끝나지 않았습니다"))
        elif not media.is_public and not allow_private:
            errors.append(DocumentError(path, f"미디어 {media_id}는 공개 미디어가 아닙니다"))
        elif media_kind(media.content_type) != kind:
            errors.append(DocumentError(path, f"미디어 {media_id}는 {_KIND_NAMES[kind]} 아닙니다"))
    return errors


def case_ref_problems(document: Document) -> list[DocumentError]:
    """Cited portfolio items must exist (hidden ones are fine)."""
    wanted: list[tuple[str, int]] = []
    for t, tab in enumerate(document.tabs):
        for b, block in enumerate(tab.blocks):
            if isinstance(block, CaseRefBlock):
                for i, item in enumerate(block.items):
                    wanted.append((f"tabs[{t}].blocks[{b}].items[{i}].item_id", item.item_id))
    found = set(
        PortfolioItem.objects.filter(pk__in={pk for _, pk in wanted}).values_list("pk", flat=True)
    )
    return [
        DocumentError(path, f"포트폴리오 항목 {pk}가 없습니다")
        for path, pk in wanted
        if pk not in found
    ]


def stored_document(data: object, *, allow_private_media: bool = False) -> dict[str, JSON]:
    """Validate a document for storage: schema, media references, then the normalized form.

    Only proposal documents pass `allow_private_media`: their media is served behind the
    customer session or the signed preview link; every other document is public."""
    document = validate_document(data)
    errors = media_problems(document, allow_private=allow_private_media) + case_ref_problems(
        document
    )
    if errors:
        raise InvalidDocument(errors)
    # Resolved URLs are computed when serving; a stored one would go stale.
    for tab in document.tabs:
        for block in tab.blocks:
            if isinstance(block, GalleryBlock):
                for image in block.images:
                    image.url = None
            if isinstance(block, AudioCompareBlock):
                for track in [block.original, *block.tracks]:
                    track.url = None
            if isinstance(block, VideoBlock):
                block.url = block.poster_url = None
            if isinstance(block, CaseRefBlock):
                # Case content is filled when serving: drafts always read the current portfolio.
                for item in block.items:
                    item.case = None
    return normalized(document)


class SiteProfile(models.Model):
    """The single site profile: what the public home page shows."""

    DOCUMENT_FIELDS: ClassVar[tuple[str, ...]] = ("company_intro", "ceo_intro")

    tagline = models.CharField(
        "한 줄 소개",
        max_length=160,
        blank=True,
        help_text="홈 첫 화면 강조 문구(hero-claim)와 GitHub 프로필 README에 쓴다. 비우면 숨긴다.",
    )
    company_intro = models.JSONField("회사 소개 문서", default=empty_document)
    ceo_intro = models.JSONField("대표 소개 문서", default=empty_document)
    contact_email = models.EmailField("연락 이메일", blank=True)
    contact_phone = models.CharField("연락 전화", max_length=40, blank=True)
    address = models.CharField("주소", max_length=200, blank=True)
    github = models.JSONField(
        "GitHub README 데이터",
        default=dict,
        blank=True,
        help_text="personal_intro, stack_badges, public_projects, contact_note (JSON).",
    )
    availability = models.CharField(
        "가용 상태",
        max_length=60,
        blank=True,
        help_text="머리띠에 점과 함께 보인다(예: 새 프로젝트 받는 중). 비우면 숨긴다.",
    )
    availability_updated_on = models.DateField(
        "가용 상태 갱신일",
        null=True,
        blank=True,
        help_text="머리띠에 「갱신 YYYY.MM」으로 보인다. 비우고 저장하면 오늘로 채운다.",
    )
    career_started_on = models.DateField(
        "웹·앱 개발 경력 시작일",
        null=True,
        blank=True,
        help_text="홈 증거 행의 「N년차」 = 올해 − 시작 연도 + 1. 비우면 그 항목을 숨긴다.",
    )
    response_promise = models.CharField(
        "첫 회신 약속",
        max_length=40,
        blank=True,
        default="영업일 1일",
        help_text="홈 증거 행의 「첫 회신」 문구(예: 영업일 1일). 비우면 그 항목을 숨긴다.",
    )
    business_name = models.CharField(
        "상호",
        max_length=60,
        blank=True,
        default="샌드코프(Sandcorp)",
        help_text="공개 페이지 하단 사업자 정보의 상호. 비우면 그 항목을 숨긴다.",
    )
    representative = models.CharField(
        "대표",
        max_length=40,
        blank=True,
        default="김한얼",
        help_text="공개 페이지 하단 사업자 정보의 대표자. 비우면 그 항목을 숨긴다.",
    )
    business_number = models.CharField(
        "사업자등록번호",
        max_length=20,
        blank=True,
        default="752-26-01740",
        help_text="공개 페이지 하단 사업자 정보의 사업자등록번호. 비우면 그 항목을 숨긴다.",
    )
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
        self.github = stored_github(self.github)
        if self.availability and self.availability_updated_on is None:
            self.availability_updated_on = timezone.localdate()
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
        try:
            self.github = stored_github(self.github)
        except InvalidGithubProfile as exc:
            problems["github"] = [f"{path}: {reason}" for path, reason in exc.errors]
        if problems:
            raise ValidationError(problems)


class PortfolioItem(models.Model):
    """One portfolio entry. Hidden entries keep their data; only the public views skip them."""

    class Status(models.TextChoices):
        LIVE = "live", "운영 중"
        BUILDING = "building", "진행 중"
        ENDED = "ended", "서비스 종료"

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
    status = models.CharField(
        "상태",
        max_length=10,
        choices=Status,
        blank=True,
        help_text="비우면 표시하지 않는다.",
    )
    outcome = models.CharField(
        "결과 한 줄",
        max_length=160,
        blank=True,
        help_text="행 제목 아래에 요약 대신 보인다. 비우면 요약이 보인다.",
    )
    service_url = models.URLField(
        "서비스 주소",
        max_length=300,
        blank=True,
        help_text="서비스의 바깥 주소(예 https://codemit.kr). README 서비스 표에 쓴다.",
    )
    metrics_site_key = models.CharField(
        "메트릭 사이트 키",
        max_length=40,
        blank=True,
        help_text="metrics 사이트 키(codemit·daypage·foresight·sandcorp).",
    )
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
        old_slug = (
            PortfolioItem.objects.filter(pk=self.pk).values_list("slug", flat=True).first()
            if self.pk
            else None
        )
        super().save(**kwargs)
        if old_slug and old_slug != self.slug:
            # The old address keeps working: /work/<old> answers 301 to the new one (#111).
            self.slug_aliases.filter(slug=self.slug).delete()
            PortfolioSlugAlias.objects.update_or_create(slug=old_slug, defaults={"item": self})

    def check_slug(self) -> None:
        """A slug may not be another item's old address (that address redirects there)."""
        taken = PortfolioSlugAlias.objects.filter(slug=self.slug).exclude(item_id=self.pk)
        if taken.exists():
            raise ValidationError({"slug": "다른 항목의 옛 주소로 쓰이고 있습니다."})

    def check_cover(self) -> None:
        cover = self.cover
        if cover is not None and not (
            cover.is_public and cover.is_complete and media_kind(cover.content_type) == "image"
        ):
            raise ValidationError({"cover": "업로드가 끝난 공개 이미지만 쓸 수 있습니다."})

    def clean(self) -> None:
        self.check_cover()
        self.check_slug()
        try:
            self.body = stored_document(self.body)
        except InvalidDocument as exc:
            raise ValidationError({"body": [f"{e.path}: {e.reason}" for e in exc.errors]}) from exc

    def tag_list(self) -> list[str]:
        return [tag for tag in (t.strip() for t in self.tags.split(",")) if tag]


class PortfolioSlugAlias(models.Model):
    """An old address of a portfolio item. `/work/<slug>` answers 301 to the item's current slug.

    Written by PortfolioItem.save when the slug changes; never edited by hand."""

    slug = models.SlugField("옛 주소", unique=True)
    item = models.ForeignKey(
        PortfolioItem,
        verbose_name="항목",
        on_delete=models.CASCADE,
        related_name="slug_aliases",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "포트폴리오 옛 주소"
        verbose_name_plural = "포트폴리오 옛 주소"

    def __str__(self) -> str:
        return f"{self.slug} → {self.item.slug}"


class BlogPost(models.Model):
    """A post of the blog 「기록」 (/blog/<slug>), written as a block document like portfolio items.

    Rules (slug generation, publishing) live in services/blog.py; the model only keeps the stored
    document and cover valid, the same way PortfolioItem does. A draft is never shown publicly.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "초안"
        PUBLISHED = "published", "발행"

    slug = models.SlugField("주소", max_length=80, unique=True, help_text="/blog/<주소> 로 열린다.")
    title = models.CharField("제목", max_length=120)
    summary = models.CharField("요약", max_length=300, blank=True, help_text="목록과 OG 설명.")
    tags = models.CharField("태그", max_length=200, blank=True, help_text="쉼표로 구분.")
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
    body = models.JSONField("본문 문서", default=empty_document)
    status = models.CharField("상태", max_length=10, choices=Status, default=Status.DRAFT)
    published_at = models.DateTimeField(
        "발행 시각",
        null=True,
        blank=True,
        help_text="첫 발행 때 채워지고 그 뒤 유지된다(목록 순서).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "블로그 글"
        verbose_name_plural = "블로그 글"
        ordering = ("-published_at", "-id")
        indexes = [models.Index(fields=["status", "published_at"], name="blogpost_status_pub")]

    def __str__(self) -> str:
        return self.title

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        self.check_cover()
        self.body = stored_document(self.body)
        self.tags = ", ".join(self.tag_list())
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()  # first publication; kept from then on
        super().save(**kwargs)

    def check_cover(self) -> None:
        cover = self.cover
        if cover is not None and not (
            cover.is_public and cover.is_complete and media_kind(cover.content_type) == "image"
        ):
            raise ValidationError({"cover": "업로드가 끝난 공개 이미지만 쓸 수 있습니다."})

    def clean(self) -> None:
        self.check_cover()
        try:
            self.body = stored_document(self.body)
        except InvalidDocument as exc:
            raise ValidationError({"body": [f"{e.path}: {e.reason}" for e in exc.errors]}) from exc

    def tag_list(self) -> list[str]:
        return [tag for tag in (t.strip() for t in self.tags.split(",")) if tag]

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED


class TipCategory(models.TextChoices):
    """The fixed kinds a tip is filed under (issue 203); a tip may have several. The value is
    the `/tips?category=<value>` filter, the label what readers see."""

    TESTING = "testing", "테스트"
    PERFORMANCE = "performance", "성능"
    REALTIME = "realtime", "웹소켓·실시간"
    MEMORY = "memory", "메모리"
    DEPLOY = "deploy", "배포·인프라"
    FRONTEND = "frontend", "프론트·UI"
    AUTH = "auth", "인증"
    DEBUGGING = "debugging", "디버깅"


def ordered_categories(values: object) -> list[str]:
    """Known category values, each once, in the fixed order; anything else is a ValidationError."""
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValidationError({"categories": "분류는 문자열 목록이어야 합니다."})
    unknown = sorted(set(values) - set(TipCategory.values))
    if unknown:
        raise ValidationError({"categories": f"모르는 분류: {', '.join(unknown)}"})
    return [value for value in TipCategory.values if value in values]


class Tip(models.Model):
    """A short development tip (/tips/<slug>, issue 203): problem, cause, fix and a short code
    example in one markdown body. Rules live in services/tips.py; drafts are never public. There
    is deliberately no source field: where a tip came from stays out of the site."""

    class Status(models.TextChoices):
        DRAFT = "draft", "초안"
        PUBLISHED = "published", "발행"

    slug = models.SlugField("주소", max_length=80, unique=True, help_text="/tips/<주소> 로 열린다.")
    title = models.CharField("제목", max_length=120)
    summary = models.CharField(
        "한 줄 요약", max_length=200, blank=True, help_text="목록과 OG 설명."
    )
    # A JSON list of TipCategory values in the fixed order: eight fixed choices do not earn a
    # table, and the list filters with JSON_CONTAINS (services/tips.py).
    categories = models.JSONField("분류", default=list, blank=True)
    body = models.TextField("본문(마크다운)", blank=True)
    status = models.CharField("상태", max_length=10, choices=Status, default=Status.DRAFT)
    published_at = models.DateTimeField(
        "발행 시각",
        null=True,
        blank=True,
        help_text="첫 발행 때 채워지고 그 뒤 유지된다(목록 순서).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField("갱신 시각", auto_now=True)

    class Meta:
        verbose_name = "개발 팁"
        verbose_name_plural = "개발 팁"
        ordering = ("-published_at", "-id")
        indexes = [models.Index(fields=["status", "published_at"], name="tip_status_pub")]

    def __str__(self) -> str:
        return self.title

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        self.categories = ordered_categories(self.categories)
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()  # first publication; kept from then on
        super().save(**kwargs)

    def clean(self) -> None:
        self.categories = ordered_categories(self.categories)

    def category_list(self) -> list[str]:
        return [str(value) for value in self.categories]

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED


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
    # The customer's access code, as a Django password hash; the plain code is shown once.
    # Sessions carry `access_code_issued_at`, so a reissue invalidates every one of them.
    access_code_hash = models.CharField(max_length=256, blank=True, editable=False)
    access_code_issued_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "제안서"
        verbose_name_plural = "제안서"
        ordering = ("-id",)

    def __str__(self) -> str:
        return f"{self.client.code} · {self.title}"

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        self.document = stored_document(self.document, allow_private_media=True)
        super().save(**kwargs)

    def clean(self) -> None:
        try:
            self.document = stored_document(self.document, allow_private_media=True)
        except InvalidDocument as exc:
            raise ValidationError(
                {"document": [f"{e.path}: {e.reason}" for e in exc.errors]}
            ) from exc


class ProposalRevision(models.Model):
    """What the customer saw: a frozen copy of a proposal at one publication. Never changes.

    Fields are the stored document and metadata at publish time (media URLs are resolved when
    served, like everywhere else). `doc_number` is SC-{YYYYMMDD}-{client code}-{serial}.
    """

    proposal = models.ForeignKey(
        Proposal, verbose_name="제안서", on_delete=models.PROTECT, related_name="revisions"
    )
    number = models.PositiveIntegerField("리비전")
    client = models.ForeignKey(
        Client, verbose_name="고객", on_delete=models.PROTECT, related_name="revisions"
    )
    serial = models.PositiveIntegerField("고객별 일련번호")
    doc_number = models.CharField("문서번호", max_length=40, unique=True)
    published_at = models.DateTimeField("발행")
    recipient = models.CharField("받는 분", max_length=200)
    title = models.CharField("제목", max_length=160)
    subtitle = models.CharField("부제", max_length=200, blank=True)
    quote_date = models.DateField("견적 기준일")
    valid_until = models.DateField("유효기간", null=True, blank=True)
    document = models.JSONField("제안서 문서")

    class Meta:
        verbose_name = "리비전"
        verbose_name_plural = "리비전"
        ordering = ("proposal", "-number")
        constraints = [
            models.UniqueConstraint(fields=("proposal", "number"), name="revision_number_unique"),
            models.UniqueConstraint(fields=("client", "serial"), name="revision_serial_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.doc_number} (v{self.number})"

    def save(self, **kwargs: Any) -> None:  # Any: forwarded unchanged to Model.save
        if not self._state.adding:
            raise ValueError("리비전은 바꿀 수 없습니다")
        super().save(**kwargs)


class ProposalEvent(models.Model):
    """One thing a customer did on a published proposal (#18): code tries, views, tab switches,
    PDF downloads. Append-only; the owner reads it in admin and (#24) through MCP."""

    class Kind(models.TextChoices):
        CODE_OK = "code_ok", "코드 인증 성공"
        CODE_WRONG = "code_wrong", "코드 인증 실패"
        BLOCKED = "blocked", "코드 차단"
        VIEWED = "viewed", "열람"
        TAB = "tab", "탭 전환"
        PDF = "pdf", "PDF 다운로드"

    proposal = models.ForeignKey(
        Proposal, verbose_name="제안서", on_delete=models.CASCADE, related_name="events"
    )
    revision = models.ForeignKey(
        ProposalRevision,
        verbose_name="리비전",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    kind = models.CharField("종류", max_length=12, choices=Kind)
    tab_id = models.CharField("탭", max_length=60, blank=True)
    ip = models.CharField("IP", max_length=45, blank=True)
    user_agent = models.CharField("User-Agent", max_length=255, blank=True)
    # True on the one view that was the revision's first; the unique constraint below lets
    # exactly one of two simultaneous first views win (and send the alert).
    first = models.BooleanField("리비전 첫 열람", default=False)
    created_at = models.DateTimeField("시각", default=timezone.now)

    class Meta:
        verbose_name = "열람 기록"
        verbose_name_plural = "열람 기록"
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=("proposal", "created_at"), name="event_proposal_time")]
        constraints = [
            # MySQL has no partial unique constraints, so this is a functional unique index on
            # "revision if first else NULL": NULLs never clash, so non-first rows are free.
            models.UniqueConstraint(
                models.Case(models.When(first=True, then=models.F("revision"))),
                name="event_first_view_once",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.created_at:%Y-%m-%d %H:%M}"


class Inquiry(models.Model):
    """A message left on the home form (or relayed by another Sandcorp site). `handled_at` is set
    once the owner has dealt with it; until then it counts as unhandled."""

    class Kind(models.TextChoices):
        INQUIRY = "문의", "문의"
        PROPOSAL = "제안", "제안"
        NEW = "신규 개발", "신규 개발"
        MAINTENANCE = "유지보수", "유지보수"
        OTHER = "기타", "기타"
        # The two offerings: the value is the offering's `inquiry_kind` in services/offerings.py
        # (tests/test_inquiries.py keeps them equal).
        MCP_INTEGRATION = "MCP 연동", "MCP 연동"
        CLAUDE_CODE_AUTOMATION = "Claude Code 자동화", "Claude Code 자동화"

    site = models.CharField("사이트", max_length=40, default="portfolio")
    kind = models.CharField("구분", max_length=20, choices=Kind, default=Kind.INQUIRY)
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


class PdfJob(models.Model):
    """The customer's PDF of one revision, and the background job that makes it.

    One row per revision, made in the same transaction as the revision (so the worker sees it
    only after the publication commits). The worker (`manage.py pdf_worker`) claims due jobs one
    at a time; `locked_at` is when it claimed this one. A running job whose `locked_at` is older
    than `PDF_JOB_STALE_SECONDS` belongs to a worker that died and is picked up again.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        RUNNING = "running", "처리 중"
        DONE = "done", "완료"
        FAILED = "failed", "실패"

    revision = models.OneToOneField(
        ProposalRevision, verbose_name="리비전", on_delete=models.PROTECT, related_name="pdf"
    )
    status = models.CharField(
        "PDF 상태", max_length=8, choices=Status, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField("시도 횟수", default=0)
    run_after = models.DateTimeField("다음 시도", auto_now_add=True)
    locked_at = models.DateTimeField("처리 시작", null=True, blank=True)
    finished_at = models.DateTimeField("완료", null=True, blank=True)
    error = models.TextField("마지막 오류", blank=True)
    object_key = models.CharField("PDF 객체 키", max_length=200, blank=True)
    size = models.PositiveIntegerField("크기(바이트)", null=True, blank=True)

    class Meta:
        verbose_name = "리비전 PDF"
        verbose_name_plural = "리비전 PDF"
        ordering = ("-id",)
        # claim_next's `ORDER BY run_after, id ... FOR UPDATE SKIP LOCKED`: without an index
        # InnoDB locks every due row while sorting, so a second worker would get nothing.
        indexes = [models.Index(fields=("status", "run_after", "id"), name="pdfjob_due")]

    def __str__(self) -> str:
        return f"{self.revision.doc_number} PDF ({self.get_status_display()})"
