"""Values sealed with a key derived from `SECRET_KEY` (issue 231, generalised in #233).

The Fernet key is derived with HKDF-SHA256 and a purpose label, so it is never stored and each
purpose gets its own key. Changing `SECRET_KEY` makes every sealed value unreadable (`open_`
answers None); the owner enters the value again and it is sealed under the new key.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


class Box:
    def __init__(self, purpose: bytes) -> None:
        self._purpose = purpose

    def __repr__(self) -> str:
        return f"Box({self._purpose!r})"

    def _fernet(self) -> Fernet:
        secret: str = settings.SECRET_KEY
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=self._purpose).derive(
            secret.encode()
        )
        return Fernet(base64.urlsafe_b64encode(key))

    def seal(self, plain: str) -> str:
        return self._fernet().encrypt(plain.encode()).decode("ascii")

    def open_(self, sealed: str) -> str | None:
        """The plain value, or None when there is none or it was sealed under another key."""
        if not sealed:
            return None
        try:
            return self._fernet().decrypt(sealed.encode("ascii")).decode()
        except InvalidToken, ValueError:
            return None
