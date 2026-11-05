"""The proposal access code, sealed so the owner can read it again in the admin (issue 231).

The code is still checked against `Proposal.access_code_hash`; this sealed copy only lets the
staff admin show it. The key comes from `services/sealed_box.py` with this purpose label (keep
it: codes already sealed in production were sealed under it).
"""

from services.sealed_box import Box

PURPOSE = b"portfolio.proposal-access-code"
_box = Box(PURPOSE)


def seal(code: str) -> str:
    return _box.seal(code)


def open_(sealed: str) -> str | None:
    """The plain code, or None when there is none or it was sealed under another key."""
    return _box.open_(sealed)
