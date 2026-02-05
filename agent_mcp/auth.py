"""DID verification helpers.

Phase 1 (now): optional Archon-signed auth envelopes.
- If no auth is provided: allow (backwards compatible).
- If auth is provided and looks like a signed Keymaster document: verify it.

Phase 2 (future): enforce credential schemas (capability-attestation, etc.).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from .archon_utils import verify_json


class AuthError(Exception):
    pass


def verify_auth(auth: Dict[str, Any] | str | None) -> Tuple[bool, str | None]:
    """Verify optional auth. Returns (allowed, requester_did)."""
    if not auth:
        return True, None

    if isinstance(auth, str):
        try:
            auth = json.loads(auth)
        except Exception:
            # Unknown string format; reject.
            return False, None

    # Unsigned fallback
    if isinstance(auth, dict) and ("proof" not in auth and "issuer" not in auth):
        did = auth.get("did") or auth.get("credential_did")
        return True, did

    # Signed doc: verify
    ok, issuer, _err = verify_json(auth if isinstance(auth, dict) else {})
    if not ok:
        return False, None

    return True, issuer
