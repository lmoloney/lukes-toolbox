"""JWT claim diagnostics for access tokens.

Claims decoded here are for operator visibility only. Signature and issuer
validation are Entra/Fabric's job for this local diagnostic CLI.
"""

from __future__ import annotations

import base64
import json
from typing import Any

DIAGNOSTIC_CLAIMS = (
    "aud",
    "iss",
    "tid",
    "appid",
    "azp",
    "azpacr",
    "scp",
    "upn",
    "preferred_username",
    "unique_name",
    "oid",
    "amr",
    "idtyp",
)


def decode_unverified_claims(token: str) -> dict[str, Any]:
    """Decode a JWT payload without validating it."""
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Access token is not a JWT-shaped token")

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    claims = json.loads(decoded)
    if not isinstance(claims, dict):
        raise ValueError("JWT payload was not a JSON object")
    return claims


def selected_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """Return only the non-sensitive claims useful for this diagnostic."""
    return {key: claims[key] for key in DIAGNOSTIC_CLAIMS if key in claims}
