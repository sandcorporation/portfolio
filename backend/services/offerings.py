"""The two service pages (/services/<slug>, issue 163) and the home's 「서비스」 rows.

The copy lives here and only here: the shell sends it as #page-data, the server HTML and React
both draw it from there. No database row, admin form or MCP tool edits it; a change is a PR.
Every fact quoted in `cases` comes from the linked post or portfolio item; keep it that way.
"""

from datetime import date
from typing import TypedDict

# sitemap.xml's <lastmod> for both pages: bump it when the copy below changes.
UPDATED_ON = date(2026, 10, 30)


class Item(TypedDict):
    title: str
    text: str


class Case(TypedDict):
    title: str
    href: str  # a page of this site
    kind: str  # the mono label of the row: 「기록」 or 「포트폴리오」
    note: str


class Offering(TypedDict):
    """#page-data["offering"] of the shell. Mirrored by frontend/src/services/types.ts."""

    slug: str
    name: str
    summary: str  # the home row and the meta description
    lead: str  # under the page title
    service_type: str  # JSON-LD serviceType
    audience: list[str]
    deliverables: list[Item]
    steps: list[Item]
    cases: list[Case]
    contact: str


class OfferingCard(TypedDict):
    """One home row. Mirrored by frontend/src/services/types.ts."""

    slug: str
    name: str
    summary: str


OFFERINGS: tuple[Offering, ...] = (
    Offering(
        slug="mcp-integration",
        name="사내 MCP 서버·AI 에이전트 연동 구축",
        summary=(
            "회사 안의 DB·사내 API·메신저를 Claude 같은 AI가 쓸 수 있게 MCP 서버로 만들고, "
            "로그인·권한·감사 로그까지 붙입니다."
        ),
        lead=(
            "AI가 회사 시스템을 직접 읽고 쓰려면 그 사이에 MCP 서버가 있어야 합니다. "
            "연결만 하지 않고, 누가 로그인해서 무엇을 할 수 있고 무엇을 했는지 남는 데까지 "
            "운영할 수 있게 만들어 드립니다."
        ),
        service_type="MCP 서버 구축",
        audience=[
            "사내 DB나 관리 화면에서 하던 일을 AI에게 맡기고 싶은 팀",
            "직원이 쓰는 Claude에 회사 시스템을 연결하되, 누가 무엇을 했는지 남아야 하는 회사",
            "공개 API가 없는 프로그램(메신저 등)을 AI가 다루게 하고 싶은 경우",
            "MCP 서버는 있지만 로그인과 권한이 비어 있는 경우",
        ],
        deliverables=[
            Item(
                title="MCP 서버 설계·구현",
                text=(
                    "사내 DB·API·관리 기능을 AI가 부를 수 있는 도구로 나눕니다. "
                    "읽기 도구와 바꾸는 도구를 구분합니다."
                ),
            ),
            Item(
                title="로그인과 권한",
                text=(
                    "OAuth 2.1 인가 서버를 세우거나 기존 로그인에 붙여, claude.ai 커넥터 같은 "
                    "공개 클라이언트도 로그인하게 합니다. "
                    "도구마다 쓸 수 있는 범위(스코프)를 나눕니다."
                ),
            ),
            Item(
                title="감사 로그",
                text=(
                    "어떤 도구를 누가 언제 불렀는지 남깁니다. "
                    "메시지 본문처럼 남기면 안 되는 값은 뺍니다."
                ),
            ),
            Item(
                title="남용 막기",
                text="로그인 시도, 클라이언트 등록, 토큰 발급에 횟수 제한을 둡니다.",
            ),
            Item(
                title="배포와 운영",
                text="배포, 백업, 실패 알림까지 맡거나 사내 팀이 이어받을 수 있게 문서로 넘깁니다.",
            ),
        ],
        steps=[
            Item(title="상담", text="연결할 시스템과 AI에게 맡길 일을 듣습니다."),
            Item(
                title="범위 정의",
                text="도구 목록, 권한, 남길 기록을 문서로 정하고 견적을 드립니다.",
            ),
            Item(
                title="주 단위 시연",
                text="매주 실제 AI 클라이언트에서 도구를 불러 보며 진행 상황을 보여 드립니다.",
            ),
            Item(title="납품", text="코드, 배포 설정, 운영 문서를 넘깁니다."),
            Item(title="운영 지원", text="운영 중 생기는 문제를 고치고 도구 추가를 돕습니다."),
        ],
        cases=[
            Case(
                title="claude.ai 커넥터가 내 사이트에 로그인하기",
                href="/blog/sandcorp-auth-mcp-oauth",
                kind="기록",
                note=(
                    "OAuth 2.1 인가 서버를 Django와 authlib로 일주일 동안 만들었습니다. "
                    "10분짜리 액세스 토큰과 90일짜리 리프레시 토큰, PKCE, 등록·토큰 발급 횟수 "
                    "제한을 다룹니다."
                ),
            ),
            Case(
                title="카카오톡을 Claude가 직접 다루게 만들기",
                href="/blog/kakaotalk-mcp-hyperv",
                kind="기록",
                note=(
                    "개인 계정용 공개 API가 없는 카카오톡을 Hyper-V 가상 컴퓨터에 격리하고 MCP "
                    "서버를 붙였습니다. 도구마다 스코프를 나누고 호출을 감사 로그에 남깁니다"
                    "(메시지 본문은 남기지 않음). 공개 오픈소스(MIT)를 바탕으로 기능을 늘렸습니다."
                ),
            ),
            Case(
                title="Sandcorp Flow",
                href="/work/sandcorp-flow",
                kind="포트폴리오",
                note="MCP 서버를 두어 Claude 같은 AI 도구에서 상담 챗봇의 흐름을 읽고 고칩니다.",
            ),
            Case(
                title="Sandcorp 플랫폼",
                href="/work/sandcorp-platform",
                kind="포트폴리오",
                note=(
                    "지금 보고 계신 이 사이트입니다. 원격 MCP 서버를 통해 Claude에서 제안서와 "
                    "포트폴리오를 작성·미리보기·발행합니다."
                ),
            ),
            Case(
                title="Foresight",
                href="/work/ai-trend-news",
                kind="포트폴리오",
                note=(
                    "서버에 LLM 호출 코드가 없습니다. 편집 판단은 외부의 Claude 에이전트가 "
                    "MCP 도구로 하고, 서버는 수집·저장·서빙만 맡습니다."
                ),
            ),
        ],
        contact=(
            "가격은 범위에 따라 정합니다. 연결하고 싶은 시스템과 맡기고 싶은 일을 적어 보내 "
            "주시면 영업일 1일 안에 답합니다."
        ),
    ),
    Offering(
        slug="claude-code-automation",
        name="Claude Code 기반 개발 자동화 도입",
        summary=(
            "팀 저장소에 Claude Code 작업 흐름(이슈 → 워크트리 → 시험 → PR)과 훅·스킬, "
            "시험 속도 예산, 토큰 관리를 들여 정착시킵니다."
        ),
        lead=(
            "Claude Code에게 이슈 하나를 맡기고 시험을 통과한 PR로 돌려받는 흐름을 팀 저장소에 "
            "도입합니다. 샌드코프가 실제로 쓰는 방식을 저장소에 맞춰 옮기고, 팀이 직접 돌릴 수 "
            "있을 때까지 함께합니다."
        ),
        service_type="개발 자동화 도입",
        audience=[
            "Claude Code를 쓰기 시작했지만 사람마다 쓰는 방식이 다른 팀",
            "에이전트에게 맡긴 작업의 토큰 비용이 예상보다 큰 팀",
            "시험이 느려 에이전트가 기다리는 시간이 긴 저장소",
            "에이전트가 같은 실수를 되풀이해 사람이 매번 고쳐 주는 경우",
        ],
        deliverables=[
            Item(
                title="작업 흐름",
                text=(
                    "이슈 하나를 워크트리 하나에서 구현·시험·PR까지 진행하는 흐름과, 여러 이슈를 "
                    "차례로 맡기는 조율 방식을 저장소에 맞춰 만듭니다."
                ),
            ),
            Item(
                title="저장소 지침",
                text="매 세션 읽히는 CLAUDE.md를 짧게 나누고, 필요한 문서만 찾아 읽게 합니다.",
            ),
            Item(
                title="훅과 스킬",
                text=(
                    "큰 파일 통째로 읽기처럼 되풀이되는 실수를 모델보다 먼저 막는 훅과, 팀의 "
                    "절차를 담은 스킬을 만듭니다."
                ),
            ),
            Item(
                title="시험 속도 예산",
                text=(
                    "시험 하나마다 시간 한도를 걸고, "
                    "넘으면 한도를 올리지 않고 원인을 줄이는 규칙을 들입니다."
                ),
            ),
            Item(
                title="토큰·비용 관리",
                text=(
                    "티켓마다 턴 수와 토큰을 재고, 작업 지시서를 고쳐 다음 티켓의 비용을 줄입니다."
                ),
            ),
        ],
        steps=[
            Item(
                title="상담",
                text="지금 Claude Code를 어떻게 쓰고 있는지, 어디서 막히는지 듣습니다.",
            ),
            Item(
                title="범위 정의",
                text="저장소를 읽고, 들일 흐름·훅·시험 규칙을 정해 견적을 드립니다.",
            ),
            Item(
                title="주 단위 시연",
                text="매주 팀 저장소의 실제 이슈를 이 흐름으로 처리해 PR로 보여 드립니다.",
            ),
            Item(title="납품", text="훅, 스킬, 지침 문서와 쓰는 법을 넘깁니다."),
            Item(title="운영 지원", text="팀이 직접 돌리면서 생기는 문제를 함께 고칩니다."),
        ],
        cases=[
            Case(
                title="작업자 한 명이 45M 토큰을 쓰지 않게 — dev-kit 연재 ① 토큰과 조율",
                href="/blog/devkit-1-tokens-orchestration",
                kind="기록",
                note=(
                    "한 티켓이 196턴을 돌며 45M 토큰을 썼습니다. 지시서를 고친 뒤 같은 유형의 "
                    "두 번째 티켓이 87턴·13M에서 60턴·9.5M으로 줄었고, 매 세션 실리는 "
                    "CLAUDE.md는 1,800줄에서 87줄로 나눴습니다."
                ),
            ),
            Case(
                title="E2E 6분을 1.3분으로 — dev-kit 연재 ② 시험 속도",
                href="/blog/devkit-2-test-speed",
                kind="기록",
                note=(
                    "시험 하나마다 0.5·1·3초 한도를 걸었습니다. 전체 E2E가 로컬 1.3분, CI 45초가 "
                    "되었습니다."
                ),
            ),
            Case(
                title="모델이 실수하기 전에 훅이 먼저 막는다 — dev-kit 연재 ③ 작업 환경",
                href="/blog/devkit-3-hooks-panel",
                kind="기록",
                note=(
                    "heredoc 1,224건 중 깨진 12건이 모두 7,600자 이상이었다는 기록에서 훅의 경계를 "
                    "정했고, 1,000줄·80KB를 넘는 파일을 통째로 읽으려 하면 "
                    "거부하는 훅을 만들었습니다."
                ),
            ),
        ],
        contact=(
            "가격은 저장소와 팀 규모에 따라 정합니다. 지금 쓰는 방식과 막히는 곳을 적어 보내 "
            "주시면 영업일 1일 안에 답합니다."
        ),
    ),
)

_BY_SLUG = {offering["slug"]: offering for offering in OFFERINGS}


def get(slug: str) -> Offering | None:
    return _BY_SLUG.get(slug)


def cards() -> list[OfferingCard]:
    """The home's rows, in page order."""
    return [OfferingCard(slug=o["slug"], name=o["name"], summary=o["summary"]) for o in OFFERINGS]


def path(slug: str) -> str:
    return f"/services/{slug}"
