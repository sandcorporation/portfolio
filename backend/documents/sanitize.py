"""Allow-list sanitizer for `html` blocks.

`html` is the escape hatch for layouts the other blocks cannot express, so its content is
untrusted markup from an editor. It is cleaned once, when the document is validated for storage
(the `html` field validator), and every stored draft, preview and published snapshot carries the
cleaned text. The renderer then sets it with `dangerouslySetInnerHTML` without a second pass.

nh3 (Rust `ammonia`) parses like a browser and rebuilds the markup from an allow-list, so
mutation-XSS tricks that fool regex filters do not survive. What it removes here:

- `<script>`, `<style>` and their content, `<iframe>`, `<object>`, `<form>`, `<svg>`, `<img>`
  and every other tag not listed below (media goes through gallery/video blocks; an `<img>`
  would also let a document phone home to a third-party server when opened);
- every `on*` event attribute, and `style`, `class`, `id` and `name` (inline CSS can overlay or
  hide the page and leak through `url()`; `class`/`id` could clash with the app's own CSS and
  DOM ids; the block's content is styled by the renderer);
- URLs whose scheme is not http, https, mailto or tel (`javascript:`, `data:`, `vbscript:`),
  and relative or `#fragment` links (fragments would point into the host page).
"""

import nh3

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "col", "colgroup", "dd", "del",
    "div", "dl", "dt", "em", "figcaption", "figure", "h3", "h4", "h5", "h6", "hr", "i", "ins",
    "kbd", "li", "mark", "ol", "p", "pre", "q", "s", "section", "small", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "time", "tr", "u", "ul",
}  # fmt: skip

ALLOWED_ATTRIBUTES = {
    "*": {"title", "lang", "dir"},
    "a": {"href"},
    "ol": {"start", "reversed"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "time": {"datetime"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def sanitize_html(markup: str) -> str:
    """The markup reduced to the allow-list. Idempotent: cleaning clean output changes nothing."""
    return nh3.clean(
        markup,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        url_relative="deny",
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )
