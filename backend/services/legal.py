"""The company site's privacy policy (/privacy, issue 201).

The copy lives here and only here: the shell sends it as #page-data, the server HTML
(core/templates/core/public/privacy.html) and React (frontend/src/legal/PrivacyPage.tsx) both
draw it from there. No database row, admin form or MCP tool edits it; a change is a PR.

Structure follows sandcorporation/privacy-and-terms `account/privacy/index.html`. Every line
states what this site's code does; when the code changes (a new form, a new cookie, a new
processor), change this text in the same PR and move EFFECTIVE_ON to the day it ships.
"""

from datetime import date, timedelta
from typing import Literal, TypedDict

from services import retention

# The day this text takes effect; also sitemap.xml's <lastmod>.
EFFECTIVE_ON = date(2026, 11, 4)

PATH = "/privacy"
TITLE = "개인정보처리방침"

# Same values as SiteProfile's defaults (tests/test_privacy_page.py checks).
OPERATOR_NAME = "샌드코프(Sandcorp)"
OPERATOR_REPRESENTATIVE = "김한얼"
OPERATOR_NUMBER = "752-26-01740"
CONTACT_EMAIL = "gksdjf1690@gmail.com"

YOUTUBE_TERMS_URL = "https://www.youtube.com/t/terms"
GOOGLE_PRIVACY_URL = "https://policies.google.com/privacy"
KISA_URL = "https://privacy.kisa.or.kr"


def _years(keep: timedelta) -> str:
    days = keep.days
    return f"{days // 365}년" if days % 365 == 0 else f"{days}일"


# The two periods the representative set (issue 201); services/retention.py enforces them.
INQUIRY_RETENTION = f"접수한 날부터 {_years(retention.INQUIRY_KEEP)}이 지나면 자동으로 지웁니다."
PROPOSAL_VIEW_LOG_RETENTION = (
    f"열람한 날부터 {_years(retention.PROPOSAL_VIEW_LOG_KEEP)}이 지나면 IP 주소와 브라우저 "
    "정보를 자동으로 지웁니다. 그 뒤에는 언제 열렸는지만 남습니다."
)


class Link(TypedDict):
    label: str
    href: str


class Paragraph(TypedDict):
    kind: Literal["p"]
    text: str


class Bullets(TypedDict):
    kind: Literal["ul"]
    items: list[str]


class Table(TypedDict):
    kind: Literal["table"]
    head: list[str]
    rows: list[list[str]]


class Links(TypedDict):
    kind: Literal["links"]
    items: list[Link]


Block = Paragraph | Bullets | Table | Links


class Section(TypedDict):
    id: str  # the anchor: /privacy#<id>
    title: str  # 「1. 수집하는 항목」, the number included
    blocks: list[Block]


class Policy(TypedDict):
    """#page-data["policy"] of the shell. Mirrored by frontend/src/legal/types.ts."""

    title: str
    effective_on: str  # 「2026년 11월 4일」
    summary: list[str]  # the box on top
    intro: str
    operator: str  # the one line: 상호 · 대표 · 사업자등록번호 · 문의
    sections: list[Section]


def _p(text: str) -> Paragraph:
    return {"kind": "p", "text": text}


def _ul(*items: str) -> Bullets:
    return {"kind": "ul", "items": list(items)}


def _table(head: list[str], *rows: list[str]) -> Table:
    return {"kind": "table", "head": head, "rows": list(rows)}


def _links(*items: tuple[str, str]) -> Links:
    return {"kind": "links", "items": [{"label": label, "href": href} for label, href in items]}


SECTIONS: list[Section] = [
    {
        "id": "collect",
        "title": "1. 수집하는 항목",
        "blocks": [
            _table(
                ["항목", "언제", "필수 여부"],
                [
                    "이름, 연락처(답을 받을 이메일·전화번호 등), 문의 구분, 문의 내용",
                    "문의 폼을 보낼 때",
                    "필수",
                ],
                ["회사 이름", "문의 폼을 보낼 때", "선택"],
                ["문의를 받은 시각, 처리한 시각", "문의를 받고 처리할 때", "자동으로 생김"],
                [
                    "제안서 열람 기록 — 접속 IP 주소, 브라우저 정보(User-Agent), 열람·탭 이동·PDF "
                    "받기·접근 코드 입력 결과와 그 시각",
                    "접근 코드를 받은 고객이 제안서 페이지(/p/…)를 열 때",
                    "자동으로 생김",
                ],
                [
                    "방문 기록 — 본 페이지 주소, 들어온 사이트의 호스트 이름, 시각, 그날만 쓰는 "
                    "무의미한 방문자 값",
                    "홈·포트폴리오·기록·서비스 페이지와 이 문서를 볼 때",
                    "자동으로 생김",
                ],
            ),
            _p(
                "회원 가입·로그인 기능이 없어 방문자의 계정 정보는 없습니다. 주민등록번호, "
                "계좌·카드 "
                "정보는 받지 않습니다. 문의 폼을 보낼 때의 접속 IP 주소는 문의 기록에 남기지 않고, "
                "짧은 시간에 몰리는 요청을 막는 데만 잠시 씁니다(4번)."
            ),
        ],
    },
    {
        "id": "how",
        "title": "2. 어떻게 수집하는지",
        "blocks": [
            _p(
                "문의 정보는 이용자가 홈의 문의 폼에 직접 적어 보낼 때 받습니다. 샌드코프의 다른 "
                "사이트가 받은 문의도 이 사이트로 넘겨 함께 보관하며, 어느 사이트에서 온 "
                "문의인지만 "
                "더해 남기고 받는 항목은 같습니다."
            ),
            _p("제안서 열람 기록과 방문 기록은 페이지를 여는 동안 자동으로 남습니다."),
        ],
    },
    {
        "id": "purpose",
        "title": "3. 이용 목적",
        "blocks": [
            _ul(
                "문의에 답하기 — 받은 내용을 확인하고 적어 주신 연락처로 회신합니다.",
                "제안서 관리 — 고객이 제안서를 열었는지, 어느 탭을 봤는지 확인하고 운영자에게 "
                "알립니다.",
                "부정 이용 방지 — 접근 코드를 여러 번 틀리거나 요청이 몰리는 IP 주소를 잠시 "
                "막습니다.",
                "방문 통계 — 페이지별 조회 수와 방문자 수를 셉니다. 사이트에 보이는 「누적 방문」 "
                "숫자도 여기서 나옵니다.",
            ),
            _p("광고, 마케팅, 개인별 이용 행태 분석에는 쓰지 않습니다."),
        ],
    },
    {
        "id": "retention",
        "title": "4. 보유 기간",
        "blocks": [
            _ul(
                f"문의 — {INQUIRY_RETENTION}",
                f"제안서 열람 기록 — {PROPOSAL_VIEW_LOG_RETENTION}",
                "방문 기록 — 90일 뒤 지우고, 그 뒤에는 날짜별 조회 수·방문자 수 합계만 남깁니다. "
                "방문자 값을 만드는 그날의 난수는 2일 뒤 지워, 지난 방문자 값이 누구의 것인지 다시 "
                "계산할 수 없습니다.",
                "요청 제한에 쓰는 IP 주소 — 문의 폼은 1시간, 제안서 접근 코드 실패 차단은 15분(IP "
                "주소의 해시), 제안서 탭 이동 제한은 10분 뒤 사라집니다.",
                "Discord 알림(6번) — 운영자의 알림 채널에 남으며, 운영자가 지울 때까지 보관됩니다.",
            ),
            _p("법령이 따로 보관을 요구하는 경우에는 그 기간 동안 보관합니다."),
        ],
    },
    {
        "id": "third-party",
        "title": "5. 제3자 제공",
        "blocks": [_p("개인정보를 제3자에게 제공하지 않습니다.")],
    },
    {
        "id": "processors",
        "title": "6. 처리 위탁과 국외 이전",
        "blocks": [
            _p("「처리 위탁」은 개인정보를 다루는 일의 일부를 다른 회사에 맡기는 것을 말합니다."),
            _table(
                ["맡은 곳", "맡긴 일"],
                [
                    "Oracle Cloud(OCI)",
                    "사이트 서버, 데이터베이스(MySQL HeatWave), 파일 저장소(Object Storage) 운영. "
                    "서버 위치: Oracle Cloud 춘천 리전(대한민국)",
                ],
            ),
            _p(
                "문의와 제안서 열람은 운영자가 바로 알 수 있게 Discord 알림으로 보냅니다. "
                "Discord는 "
                "미국 회사라 이 알림에 담긴 정보는 국외로 옮겨집니다."
            ),
            _table(
                ["구분", "내용"],
                ["이전받는 곳", "Discord Inc.(미국), privacy@discord.com"],
                [
                    "이전하는 항목",
                    "문의: 보낸 사이트·구분·이름·회사·연락처·내용. 제안서: 고객 이름, 처음 "
                    "열람·코드 "
                    "입력 차단 때의 접속 IP 주소",
                ],
                [
                    "이전 시기와 방법",
                    "문의를 받을 때, 제안서가 처음 열리거나 코드 입력이 막힐 때 암호화된 "
                    "연결(HTTPS)로 "
                    "보냅니다",
                ],
                ["목적", "운영자에게 바로 알리기"],
                ["보유 기간", "운영자가 알림 채널에서 지울 때까지"],
            ),
            _p(
                "국외 이전을 원하지 않으면 9번의 연락처로 알려 주세요. 해당 알림을 지웁니다. 문의 "
                "폼은 알림과 함께 동작하므로, 이전 없이 문의하시려면 이메일로 보내 주세요."
            ),
        ],
    },
    {
        "id": "rights",
        "title": "7. 이용자의 권리",
        "blocks": [
            _p(
                "이용자는 언제든 자기 정보를 보고, 고치고, 지우거나 처리를 멈추게 할 수 있습니다. "
                "회원 기능이 없어 화면에서 직접 하는 방법은 없으니, 9번의 연락처로 요청해 주시면 "
                "지체 없이 처리하고 결과를 알려 드립니다."
            ),
            _p(
                "방문 기록은 누구의 것인지 알 수 없는 값으로만 남기므로, 사람별로 찾아 보여 "
                "드리거나 "
                "지울 수 없습니다."
            ),
        ],
    },
    {
        "id": "cookies",
        "title": "8. 쿠키와 안전성 확보 조치",
        "blocks": [
            _p(
                "「쿠키」는 웹사이트가 브라우저에 남기는 작은 기록입니다. 일반 방문자에게는 쿠키를 "
                "쓰지 않습니다. 방문 수도 쿠키 없이, 접속 IP 주소와 브라우저 정보를 저장하지 않고 "
                "그날만 쓰는 난수와 섞은 해시 값으로 셉니다(샌드코프가 직접 운영하는 "
                "sandcorp-metrics). 광고·추적 쿠키는 쓰지 않습니다."
            ),
            _table(
                ["쿠키", "누구에게", "하는 일", "기간"],
                [
                    "proposal_<제안서 주소>",
                    "접근 코드를 맞게 넣은 제안서 고객",
                    "그 제안서를 다시 열 때 코드를 묻지 않음",
                    "7일",
                ],
                ["sessionid", "운영자만(관리 화면 로그인)", "로그인한 상태를 유지", "2주"],
                [
                    "csrftoken",
                    "운영자만(관리 화면)",
                    "다른 사이트가 몰래 요청을 보내는 공격(CSRF)을 막음",
                    "최대 1년",
                ],
            ),
            _p(
                "제안서 쿠키는 그 제안서 주소에서만 쓰이고, 세 쿠키 모두 HTTPS로만 오갑니다. 일부 "
                "포트폴리오 페이지는 샌드코프의 다른 서비스(flow.sandcorp.co.kr) 체험 화면을 "
                "페이지 "
                "안에 띄우며, 그 화면 안에서는 그 서비스의 개인정보 문서를 따릅니다."
            ),
            _p(
                "그 밖의 보호 조치: 모든 연결은 HTTPS로 암호화합니다. 관리 화면에는 운영자만 "
                "Sandcorp "
                "계정으로 로그인합니다. 제안서 접근 코드는 원래 값이 아닌 해시만 저장합니다. "
                "데이터베이스는 매일 백업해 OCI 객체 저장소와 샌드코프가 직접 운영하는 백업 서버에 "
                "둡니다."
            ),
        ],
    },
    {
        "id": "youtube",
        "title": "9. YouTube API 서비스",
        "blocks": [
            _p(
                "샌드코프는 자사 유튜브 채널에 영상을 올리기 위해 YouTube API 서비스를 사용합니다. "
                "이 기능은 샌드코프 회사 계정에만 쓰며, 회사 계정 외 이용자의 데이터는 수집하지 "
                "않습니다. YouTube API 서비스를 쓰는 부분에는 YouTube 서비스 약관과 Google "
                "개인정보처리방침이 함께 적용됩니다."
            ),
            _links(
                ("YouTube 서비스 약관", YOUTUBE_TERMS_URL),
                ("Google 개인정보처리방침", GOOGLE_PRIVACY_URL),
            ),
        ],
    },
    {
        "id": "contact",
        "title": "10. 개인정보 보호책임자와 문의",
        "blocks": [
            _ul(
                f"개인정보 보호책임자: 대표 {OPERATOR_REPRESENTATIVE} ({CONTACT_EMAIL})",
                f"문의: {CONTACT_EMAIL}",
            ),
            _p(
                "개인정보 침해에 관한 상담은 개인정보침해신고센터(국번 없이 118, "
                "privacy.kisa.or.kr)에도 할 수 있습니다."
            ),
            _links(
                (f"메일 보내기 — {CONTACT_EMAIL}", f"mailto:{CONTACT_EMAIL}"),
                ("개인정보침해신고센터 — privacy.kisa.or.kr", KISA_URL),
            ),
        ],
    },
    {
        "id": "changes",
        "title": "11. 이 문서가 바뀔 때",
        "blocks": [
            _p(
                "내용이 바뀌면 이 문서의 시행일을 고치고 같은 주소(sandcorp.co.kr/privacy)에 다시 "
                "올립니다. 이용자의 권리에 영향을 주는 변경은 시행 전에 이 페이지에 미리 알립니다."
            ),
        ],
    },
]


def effective_on_text(day: date = EFFECTIVE_ON) -> str:
    return f"{day.year}년 {day.month}월 {day.day}일"


def policy() -> Policy:
    return {
        "title": TITLE,
        "effective_on": effective_on_text(),
        "summary": [
            "샌드코프 회사 사이트(sandcorp.co.kr)는 회원 가입이 없고, 일반 방문자에게 쿠키를 쓰지 "
            "않습니다. 개인정보를 받는 곳은 문의 폼과, 접근 코드를 받은 고객만 여는 제안서 "
            "페이지뿐입니다.",
            f"문의는 답을 드리는 데만 쓰고 접수 {_years(retention.INQUIRY_KEEP)} 뒤 지웁니다. "
            "방문 수는 IP 주소를 저장하지 않고 "
            "셉니다. 광고·마케팅에 쓰지 않으며, 누구에게도 팔거나 넘기지 않습니다.",
        ],
        "intro": (
            "이 문서는 샌드코프 회사 사이트(sandcorp.co.kr, 이하 「사이트」)가 개인정보를 어떻게 "
            "모으고 쓰는지 설명합니다. Sandcorp 계정(auth.sandcorp.co.kr)과 샌드코프의 다른 "
            "서비스는 각 서비스의 문서를 따릅니다."
        ),
        "operator": (
            f"운영자: 개인사업자 {OPERATOR_NAME} · 대표 {OPERATOR_REPRESENTATIVE} · "
            f"사업자등록번호 {OPERATOR_NUMBER} · 문의 {CONTACT_EMAIL}"
        ),
        "sections": SECTIONS,
    }
