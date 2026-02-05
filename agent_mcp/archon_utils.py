"""Archon signing + verification helpers for hexswarm.

Uses Keymaster CLI (npx @didcid/keymaster) to sign/verify JSON documents.
We keep this best-effort: if Archon isn't configured, hexswarm still works.

Environment:
- ARCHON_PASSPHRASE (required to sign/verify)
- ARCHON_GATEKEEPER_URL (optional)
- ARCHON_CONFIG_DIR (optional; defaults to ~/.config/hex/archon)

Note: keymaster sign-file produces a JSON-LD object with a proof.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


ARCHON_CONFIG_DIR = Path(os.environ.get("ARCHON_CONFIG_DIR", "~/.config/hex/archon")).expanduser()


def _keymaster_env() -> dict:
    env = os.environ.copy()
    # Ensure npx can run non-interactively
    env.setdefault("ARCHON_GATEKEEPER_URL", env.get("ARCHON_GATEKEEPER_URL", "https://archon.technology"))
    return env


def can_sign() -> bool:
    if not os.environ.get("ARCHON_PASSPHRASE"):
        return False
    wallet = ARCHON_CONFIG_DIR / "wallet.json"
    return wallet.exists()


def sign_json(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return signed JSON-LD document, or None if signing unavailable."""
    if not can_sign():
        return None

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        unsigned = td_path / "unsigned.json"
        signed = td_path / "signed.json"
        unsigned.write_text(json.dumps(obj, indent=2, default=str))

        try:
            # keymaster writes signed doc to stdout
            res = subprocess.run(
                ["npx", "@didcid/keymaster", "sign-file", str(unsigned)],
                env=_keymaster_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=30,
            )
            signed.write_text(res.stdout)
            return json.loads(signed.read_text())
        except Exception:
            return None


def verify_json(signed_obj: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Verify signed JSON doc. Returns (ok, issuer_did, error)."""
    if not os.environ.get("ARCHON_PASSPHRASE"):
        # Verification needs wallet access too (keymaster). If absent, treat as not verified.
        return False, None, "ARCHON_PASSPHRASE not set"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        signed = td_path / "signed.json"
        signed.write_text(json.dumps(signed_obj, indent=2, default=str))
        try:
            res = subprocess.run(
                ["npx", "@didcid/keymaster", "verify-file", str(signed)],
                env=_keymaster_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=30,
            )
            # issuer is typically top-level "issuer"
            issuer = signed_obj.get("issuer")
            return True, issuer, None
        except subprocess.CalledProcessError as e:
            return False, None, (e.stderr.strip() or e.stdout.strip() or "verify failed")
        except Exception as e:
            return False, None, str(e)
