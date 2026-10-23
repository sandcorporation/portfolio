"""Settings for pytest: the production settings with a throwaway secret key."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")

from config.settings import *  # noqa: E402, F403
from config.settings import DATABASES  # noqa: E402

# `make db` publishes the local MySQL on 15442 (the production default is 3306).
DATABASES["default"]["PORT"] = os.environ.get("DB_PORT", "15442")

# Access codes are hashed like passwords; the real hasher's work factor only slows the tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
