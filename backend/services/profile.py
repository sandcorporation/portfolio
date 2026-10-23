"""The site profile (what the home page shows): read and patch. Only given fields change."""

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from pydantic import BaseModel, ConfigDict, Field

from content.github_profile import GithubProfile, InvalidGithubProfile, stored_github
from content.models import SiteProfile, stored_document
from documents.validation import JSON, DocumentError, InvalidDocument
from services.errors import Rejected

DOCUMENT_FIELDS = SiteProfile.DOCUMENT_FIELDS


class Profile(BaseModel):
    tagline: str
    company_intro: dict[str, JSON]
    ceo_intro: dict[str, JSON]
    contact_email: str
    contact_phone: str
    address: str
    availability: str
    availability_updated_on: date | None
    career_started_on: date | None
    response_promise: str
    github: GithubProfile


class ProfilePatch(BaseModel):
    """Fields left out stay as they are; send `""` to clear a text field."""

    model_config = ConfigDict(extra="forbid")

    tagline: str = Field(
        default="", max_length=160, description="One-line intro (home description)."
    )
    company_intro: dict[str, object] = Field(
        default_factory=dict, description="Block document (see block_schema)."
    )
    ceo_intro: dict[str, object] = Field(
        default_factory=dict, description="Block document (see block_schema)."
    )
    contact_email: str = Field(default="", max_length=254)
    contact_phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=200)
    availability: str = Field(
        default="",
        max_length=60,
        description=(
            "Availability shown in the masthead of every public page, e.g. 새 프로젝트 받는 중. "
            '"" hides it.'
        ),
    )
    availability_updated_on: date | None = Field(
        default=None,
        description=(
            "Date (YYYY-MM-DD) of the availability, shown as 갱신 YYYY.MM. null (or left out "
            "while empty) is filled with today when availability is saved."
        ),
    )
    career_started_on: date | None = Field(
        default=None,
        description=(
            "Date (YYYY-MM-DD) the web/app career began; the home evidence row shows "
            "「N년차」 = this year - start year + 1. null hides it."
        ),
    )
    response_promise: str = Field(
        default="",
        max_length=40,
        description=(
            "First-reply promise on the home evidence row, e.g. 영업일 1일 (shown as 「1일」 "
            'with 「영업일 기준」). "" hides it.'
        ),
    )
    github: GithubProfile = Field(
        default_factory=GithubProfile,
        description=(
            "GitHub profile README data; replaces the whole object. personal_intro (markdown), "
            "stack_badges (names), public_projects ([{name, url, description, "
            "scope personal|org|both}]), contact_note."
        ),
    )


def _profile_of(row: SiteProfile) -> Profile:
    return Profile(
        tagline=row.tagline,
        company_intro=row.company_intro,
        ceo_intro=row.ceo_intro,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        address=row.address,
        availability=row.availability,
        availability_updated_on=row.availability_updated_on,
        career_started_on=row.career_started_on,
        response_promise=row.response_promise,
        github=GithubProfile.model_validate(row.github or {}),
    )


def get_profile() -> Profile:
    # Reading never creates the row; an unsaved default stands in.
    return _profile_of(SiteProfile.objects.filter(pk=1).first() or SiteProfile())


def update_profile(patch: ProfilePatch) -> Profile:
    row = SiteProfile.load()
    errors: list[DocumentError] = []
    for name in patch.model_fields_set:
        value: object = getattr(patch, name)
        if name in DOCUMENT_FIELDS:
            try:
                value = stored_document(value)
            except InvalidDocument as exc:
                errors += [DocumentError(f"{name}.{e.path}", e.reason) for e in exc.errors]
                continue
        elif name == "github":
            try:
                value = stored_github(patch.github.model_dump(mode="json"))
            except InvalidGithubProfile as exc:
                errors += [DocumentError(f"github.{path}", reason) for path, reason in exc.errors]
                continue
        elif name == "contact_email" and value:
            try:
                validate_email(str(value))
            except DjangoValidationError:
                errors.append(DocumentError(name, "이메일 형식이 아닙니다"))
                continue
        setattr(row, name, value)
    if errors:
        raise Rejected(errors)
    row.save()
    return _profile_of(row)
