from __future__ import annotations

import os

# Settings are read at import time and these secrets have no default, so they
# must exist before any application module is imported by a test.
os.environ.setdefault("PSEUDO_ID_SECRET", "test-pseudo-id-secret")
os.environ.setdefault("CONSENT_TOKEN_SECRET", "test-consent-token-secret-with-32-bytes")
# These two have no default either, and a clean clone has no .env, so the suite
# could not even be collected without them. Every test builds its own in-memory
# engine, so this URL is never connected to; setdefault leaves a real
# environment untouched.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-sufficient-length")
os.environ.setdefault("ADMIN_LOGIN_BUCKET_KEY", "11" * 32)
