"""Filters for the public pages' server HTML (core/templates/core/public/, #109)."""

from collections.abc import Mapping

from django import template
from django.utils.safestring import SafeString

from core import public_html
from documents.validation import JSON

register = template.Library()


@register.filter
def document(value: Mapping[str, JSON], prefix: str) -> SafeString:
    """`{{ data.body|document:"work-" }}`: the block document with its contents."""
    return public_html.document_html(value, prefix)


@register.filter
def document_no_toc(value: Mapping[str, JSON], prefix: str) -> SafeString:
    return public_html.document_html(value, prefix, toc=False)


@register.filter
def post_date(value: str) -> str:
    return public_html.post_date(value)


@register.filter
def bare_url(value: str) -> str:
    return public_html.bare_url(value)


@register.filter
def external_attrs(href: str) -> SafeString:
    """New-tab attributes for another host's address, else `rel="noopener"` only."""
    if public_html.is_external(href):
        return public_html._external_attrs(href)
    return SafeString(' rel="noopener"')


@register.filter
def blog_href(tag: str, page: int = 1) -> str:
    return public_html.blog_index_href(tag, page)


@register.filter
def number(value: int) -> str:
    """1234 -> 1,234 (Intl.NumberFormat("ko-KR"))."""
    return f"{value:,}"
