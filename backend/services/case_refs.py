"""`case-ref` blocks: fill each cited portfolio item's content into the document.

A draft stores only references. Drafts and previews are filled with the current portfolio each
time they are served (`expand`); publishing freezes the same expansion into the revision
(`services.publishing.snapshot_document`), so the revision never reads the portfolio again.
Hidden items are cited like any other. An item that no longer exists is dropped from the copy.
"""

import copy

from content.models import PortfolioItem
from documents.validation import JSON
from services.portfolio import card_of


def expand(document: dict[str, JSON]) -> dict[str, JSON]:
    """A copy of a stored document with every `case-ref` item's `case` set from the current
    portfolio. Items whose portfolio item is gone are removed."""
    out = copy.deepcopy(document)
    blocks = [
        block
        for tab in _list(out.get("tabs"))
        for block in _list(_dict(tab).get("blocks"))
        if _dict(block).get("type") == "case-ref"
    ]
    ids = {
        item_id
        for block in blocks
        for item in _list(_dict(block).get("items"))
        if isinstance(item_id := _dict(item).get("item_id"), int)
    }
    found = {i.pk: i for i in PortfolioItem.objects.filter(pk__in=ids).select_related("cover")}
    for block in blocks:
        entry = _dict(block)
        kept: list[JSON] = []
        for item in _list(entry.get("items")):
            ref = _dict(item)
            item_id = ref.get("item_id")
            row = found.get(item_id) if isinstance(item_id, int) else None
            if row is None:
                continue
            card = card_of(row)
            ref["case"] = {
                "slug": card["slug"],
                "title": card["title"],
                "summary": card["summary"],
                "period": card["period"],
                "tags": list(card["tags"]),
                "cover_url": card["cover_url"],
            }
            kept.append(ref)
        entry["items"] = kept
    return out


def _list(value: JSON) -> list[JSON]:
    return value if isinstance(value, list) else []


def _dict(value: JSON) -> dict[str, JSON]:
    return value if isinstance(value, dict) else {}
