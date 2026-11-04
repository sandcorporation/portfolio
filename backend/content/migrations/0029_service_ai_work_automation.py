# ruff: noqa: E501  -- the copy is kept as one string per field
"""The fourth service, Claude·ChatGPT 업무 자동화 (issue 223), put in the way 0025 put the first three.

A slug that is already there is left alone (running it twice is harmless); the images (cover,
figure, card) stay empty. Reverse deletes only this slug's row.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

type Row = dict[str, object]

SERVICE: Row = {
    "slug": "ai-work-automation",
    "name": "Claude·ChatGPT 업무 자동화 구축",
    "summary": "메일·문의 분류와 요약, 보고서 초안, 시트 정리처럼 매일 손으로 하는 반복 업무를 Claude·ChatGPT가 정해진 때에 처리하고, 사람은 검토만 하도록 만듭니다.",
    "inquiry_kind": "AI 업무 자동화",
    "service_type": "AI 업무 자동화 구축",
    "lead": "매일 손으로 하는 반복 업무(메일·문의 분류와 요약, 보고서·기사 초안, 시트 정리, 채점·분류)를 Claude·ChatGPT가 정해진 시간에 처리하고 사람은 검토만 하도록 만듭니다. 샌드코프가 뉴스 편집과 채점에 실제로 쓰는 방식을 맡기실 업무에 맞춰 옮깁니다.",
    "audience": [
        "매일 같은 문서를 읽고 요약·분류하는 데 시간을 쓰는 팀",
        "ChatGPT 창에 복사·붙여넣기를 되풀이하며 일하는 업무",
        "AI가 낸 결과를 사람이 확인한 뒤에 내보내고 싶은 경우",
        "API 비용이 얼마나 들지 몰라 도입을 망설이는 경우",
    ],
    "deliverables": [
        {
            "title": "업무 흐름 정리",
            "text": "업무를 단계로 나눠 어디까지 AI가 하고 어디서 사람이 확인할지 정합니다.",
        },
        {
            "title": "API 연동과 프롬프트",
            "text": "Claude·ChatGPT API를 업무에 연결하고, 결과를 정해진 형식으로 받도록 프롬프트와 출력 검사를 만듭니다.",
        },
        {
            "title": "예약 실행·트리거",
            "text": "정해진 시간, 새 메일, 시트에 추가된 행, 웹훅을 계기로 작업이 저절로 돌게 합니다.",
        },
        {
            "title": "사람 검토와 실패 알림",
            "text": "AI 결과를 바로 내보내지 않고 검토 단계를 두며, 실패하거나 결과가 이상하면 알림을 보냅니다.",
        },
        {
            "title": "비용 한도·호출 기록",
            "text": "호출마다 기록을 남기고 하루·월 비용 한도를 걸어 예상 밖 지출을 막습니다.",
        },
    ],
    "steps": [
        {"title": "상담", "text": "매일 손으로 하는 업무와 그 결과물이 어디로 가는지 듣습니다."},
        {
            "title": "업무 하나로 시범",
            "text": "업무 하나를 골라 자동화하고 실제 데이터로 돌려 결과와 비용을 함께 봅니다.",
        },
        {"title": "확장", "text": "시범에서 확인한 방식으로 다른 업무를 차례로 붙입니다."},
        {
            "title": "인계",
            "text": "설정·프롬프트·운영법을 문서로 넘기고 직접 고치는 법을 알려 드립니다.",
        },
        {"title": "운영 지원", "text": "쓰면서 생기는 문제와 프롬프트 조정을 함께 고칩니다."},
    ],
    "cases": [
        {
            "title": "Foresight",
            "href": "/work/ai-trend-news",
            "kind": "포트폴리오",
            "note": "AI·IT 뉴스를 1시간마다 모으고, 하루 세 번 Claude가 편집자로서 중복을 묶어 한국어 제목·요약·분야를 붙여 게시합니다.",
        },
        {
            "title": "Codemit",
            "href": "/work/codemit",
            "kind": "포트폴리오",
            "note": "강사가 올린 체크리스트로 참여자의 제출물을 LLM이 항목별로 채점하고 근거를 남깁니다. 프로그래머스 데브코스 수업에서 쓰고 있습니다.",
        },
        {
            "title": "Sandcorp 플랫폼",
            "href": "/work/sandcorp-platform",
            "kind": "포트폴리오",
            "note": "이 사이트의 기록과 개발 팁은 Claude가 초안을 써서 MCP로 올리고, 미리보기로 확인한 뒤 발행합니다.",
        },
    ],
    "contact": "가격은 업무 범위와 처리량에 따라 정합니다. 자동화하고 싶은 업무와 지금 처리하는 방식을 적어 보내 주시면 영업일 1일 안에 답합니다.",
    "is_visible": True,
    "is_published": True,
    "position": 3,
}


def seed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    service = apps.get_model("content", "Service")
    if not service.objects.filter(slug=SERVICE["slug"]).exists():
        service.objects.create(**SERVICE)


def unseed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    apps.get_model("content", "Service").objects.filter(slug=SERVICE["slug"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0027_service_card"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
