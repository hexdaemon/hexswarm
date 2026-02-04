"""DID verification helpers (stub)."""

from typing import Any, Dict, Tuple


class AuthError(Exception):
    pass


def verify_auth(auth: Dict[str, Any] | None) -> Tuple[bool, str | None]:
    """Stub auth verification.

    Returns (allowed, requester_did).

    TODO (next): Replace with Archon credential verification using Keymaster's
    standardized *agent credential schemas* (archetech/archon PR #41):
      - collaboration-partner
      - capability-attestation
      - infrastructure-authorization
      - identity-link

    Policy direction:
    - For hexswarm RPC: require a valid credential conforming to the relevant schema,
      issued by an allowlisted DID (e.g., Sat/operator DID or fleet node DID).
    """
    if not auth:
        return True, None
    did = auth.get("did") or auth.get("credential_did")
    return True, did
