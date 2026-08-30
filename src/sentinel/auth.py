"""Per-merchant JWT authentication (docs/07 production design).

HS256 tokens carry a merchant id and scope; the signing secret comes
only from settings (env / .env), never code. Bearer tokens are an
alternative to the demo X-API-Key path, with one real enforcement win:
a JWT merchant may only ingest and read its own events. Admin scope
still requires the separate admin key; JWTs never grant it.

Token issuing is a CLI concern (make merchant-token MERCHANT_ID=...),
matching how a platform would mint credentials out-of-band.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt

DEFAULT_TTL_SECONDS = 24 * 3600
SCOPES = ("standard",)


@dataclass(slots=True, frozen=True)
class MerchantIdentity:
    """The verified caller when a valid bearer token is presented."""

    merchant_id: str
    scope: str
    expires_at: int


def issue_token(secret: str, merchant_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Mint an HS256 merchant token (out-of-band credential issuance)."""
    now = int(time.time())
    claims = {
        "sub": merchant_id,
        "scope": "standard",
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": "sentinel",
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def verify_token(secret: str, token: str) -> MerchantIdentity | None:
    """Verify signature, expiry, issuer, and scope; None on any failure."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="sentinel",
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    scope = str(claims.get("scope", ""))
    if scope not in SCOPES:
        return None
    return MerchantIdentity(
        merchant_id=str(claims["sub"]),
        scope=scope,
        expires_at=int(claims["exp"]),
    )


__all__ = ["MerchantIdentity", "issue_token", "verify_token"]
