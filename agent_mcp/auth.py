"""DID verification helpers (stub)."""

from typing import Any, Dict, Tuple


class AuthError(Exception):
    pass


def verify_auth(auth: Dict[str, Any] | None) -> Tuple[bool, str | None]:
    """Stub auth verification.

    Returns (allowed, requester_did). Replace with Archon DID verification later.
    """
    if not auth:
        return True, None
    did = auth.get("did") or auth.get("credential_did")
    return True, did
