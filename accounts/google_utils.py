"""
Utilities for the "Continue with Google" (Google Identity Services) flow.

The browser receives a JWT ID token from Google One Tap / the GIS button.
That token MUST be verified server-side before it can be trusted.

Two layers of parsing are provided:

1. `decode_jwt_payload`  – base64 decode ONLY. Unsafe for auth decisions on
   its own, but fine for quick client-side display of profile fields.
2. `verify_google_id_token` – full verification against Google's public
   certs (signature, audience, expiry, issuer). This is what the backend
   endpoint uses before logging anyone in.
"""

import base64
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def google_email_is_verified(value):
    return value is True or (
        isinstance(value, str) and value.strip().casefold() == "true"
    )


def decode_jwt_payload(token):
    """
    Decode the payload of a JWT *without* verifying the signature.

    Returns a dict, or {} when the token is malformed. Useful only for
    previewing name/email/picture — never trust the result for auth.
    """
    try:
        payload_b64 = token.split(".")[1]
        # Restore the base64url padding stripped by the JWT format.
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, IndexError, json.JSONDecodeError, TypeError):
        return {}


def verify_google_id_token(token):
    """
    Verify a Google-issued ID token and return its claims, or None.

    Uses Google's tokeninfo endpoint, which checks:
      - the signature against Google's public keys,
      - `aud` matches OUR client id,
      - `exp` (not expired),
      - `iss` is Google.

    SECURITY: this is the function to call in the backend view that receives
    the credential from the browser. Never trust decode_jwt_payload alone.
    """
    if not token:
        return None

    try:
        response = requests.post(
            GOOGLE_TOKENINFO_URL,
            data={"id_token": token},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning("Google tokeninfo request failed: %s", exc)
        return None

    if response.status_code != 200:
        logger.info("Google rejected the ID token (HTTP %s).", response.status_code)
        return None

    try:
        claims = response.json()
    except ValueError:
        logger.warning("Google tokeninfo returned an invalid response.")
        return None
    if not isinstance(claims, dict):
        logger.warning("Google tokeninfo returned an invalid response.")
        return None

    # Audience must be OUR OAuth client id (prevents token substitution).
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    if claims.get("aud") != client_id:
        logger.info("ID token audience mismatch.")
        return None

    # Issuer must be Google.
    if claims.get("iss") not in GOOGLE_ISSUERS:
        logger.info("ID token issuer mismatch.")
        return None

    return claims
