"""Webhook validation and authentication, both using constant-time comparisons."""

import hashlib
import hmac
import secrets

from fastapi import Header, HTTPException

from whatsapp_ai_agent.config import get_settings


def verify_webhook_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    if not app_secret or not signature or not signature.startswith("sha256="):
        return False
    calculated = "sha256=" + hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, signature)


def pseudonymize(identifier: str, secret: str) -> str:
    if not secret:
        raise ValueError("A pseudonymization key must be configured")
    return hmac.new(secret.encode(), identifier.encode(), hashlib.sha256).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(24)


def require_admin(x_admin_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_key
    if not expected or not x_admin_api_key or not hmac.compare_digest(expected, x_admin_api_key):
        raise HTTPException(status_code=403, detail="Forbidden")
