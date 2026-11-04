"""The proposal access code, sealed so the owner can read it again in the admin (issue 231).

The code is still checked against `Proposal.access_code_hash`; this sealed copy only lets the
staff admin show it. The Fernet key is derived from `SECRET_KEY` with HKDF-SHA256 and a purpose
label, so it is never stored and is useless anywhere else. Changing `SECRET_KEY` makes every
sealed code unreadable (`open_` answers None); a new code entered in the admin seals again.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

PURPOSE = b"portfolio.proposal-access-code"


def _fernet() -> Fernet:
    secret: str = settings.SECRET_KEY
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=PURPOSE).derive(
        secret.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def seal(code: str) -> str:
    return _fernet().encrypt(code.encode()).decode("ascii")


def open_(sealed: str) -> str | None:
    """The plain code, or None when there is none or it was sealed under another key."""
    if not sealed:
        return None
    try:
        return _fernet().decrypt(sealed.encode("ascii")).decode()
    except InvalidToken, ValueError:
        return None
