import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_unknown_page_is_korean_site_404() -> None:
    for path in ("/xyz", "/work/xyz", "/blog/xyz"):
        res = Client().get(path)
        html = res.content.decode()
        assert res.status_code == 404
        assert '<html lang="ko">' in html
        assert "페이지를 찾을 수 없습니다" in html
        assert 'href="/"' in html
        assert "noindex" in html
        assert 'id="root"' not in html and "<script" not in html  # no React takeover


@override_settings(DEBUG=False)
def test_machine_paths_keep_plain_404() -> None:
    for path in ("/api/nope", "/mcp/nope", "/.well-known/nope"):
        res = Client().get(path)
        assert res.status_code == 404
        assert "페이지를 찾을 수 없습니다" not in res.content.decode()


def test_500_handler_is_static_korean() -> None:
    from django.test import RequestFactory

    from core.errors import server_error

    res = server_error(RequestFactory().get("/x"))
    html = res.content.decode()
    assert res.status_code == 500
    assert '<html lang="ko">' in html and 'href="/"' in html and "일시적인 오류" in html
