"""The `SiteProfile.github` field: what the generated GitHub READMEs add to the site data."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from documents.validation import JSON


def http_url(value: str) -> str:
    """Accept only an absolute http(s) address (or "" where the caller allows blank)."""
    if value and not (value.startswith(("https://", "http://")) and " " not in value):
        raise ValueError("http(s):// 로 시작하는 주소여야 합니다")
    return value


class PublicProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=300)
    scope: Literal["personal", "org", "both"] = Field(
        description="Which README lists it: personal (farrar142), org (sandcorporation) or both."
    )

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return http_url(value)


class GithubProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal_intro: str = Field(
        default="",
        max_length=2000,
        description="Markdown under the personal README greeting (2-4 bullet lines).",
    )
    stack_badges: list[str] = Field(
        default_factory=list,
        max_length=40,
        description="Tech names, e.g. ['Python', 'Django']; unknown names get a plain grey badge.",
    )
    public_projects: list[PublicProject] = Field(default_factory=list, max_length=20)
    contact_note: str = Field(default="", max_length=300, description="One line of contact info.")

    @field_validator("stack_badges")
    @classmethod
    def _badges(cls, value: list[str]) -> list[str]:
        names = [name.strip() for name in value]
        if any(not name or len(name) > 40 for name in names):
            raise ValueError("배지 이름은 1~40자여야 합니다")
        return names


class InvalidGithubProfile(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(f"{path}: {reason}" for path, reason in errors))
        self.errors = errors


def stored_github(data: object) -> dict[str, JSON]:
    """Validate and return the normalized form to store. Raises InvalidGithubProfile."""
    try:
        parsed = GithubProfile.model_validate(data)
    except ValidationError as exc:
        raise InvalidGithubProfile(
            [(".".join(str(p) for p in e["loc"]), e["msg"]) for e in exc.errors()]
        ) from None
    dumped: dict[str, JSON] = parsed.model_dump(mode="json")
    return dumped
