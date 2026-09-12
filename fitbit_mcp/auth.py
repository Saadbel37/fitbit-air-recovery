"""OAuth2 authentication and token management for the Google Health API.

Fitbit data is now served through the Google Health API (health.googleapis.com),
authorized via Google Cloud OAuth 2.0 (Web Server flow). This module handles:
  - Building the Google authorization URL
  - Exchanging an authorization code for tokens
  - Persisting tokens to disk
  - Transparently refreshing an expired access token

Credentials come from environment variables (see .env.example).

Note on refresh tokens: while the Google Cloud OAuth consent screen is in
"Testing" status, refresh tokens expire after 7 days, so you may need to re-run
authorize.py weekly. Publishing the app removes that limit.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

# Anchor config to the project root so the server works regardless of cwd
# (MCP clients may launch it from a different working directory).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth"

# Read-only scopes covering all supported data types.
DEFAULT_SCOPES = [
    f"{_SCOPE_PREFIX}.activity_and_fitness.readonly",
    f"{_SCOPE_PREFIX}.health_metrics_and_measurements.readonly",
    f"{_SCOPE_PREFIX}.sleep.readonly",
    f"{_SCOPE_PREFIX}.nutrition.readonly",
    f"{_SCOPE_PREFIX}.profile.readonly",
    f"{_SCOPE_PREFIX}.settings.readonly",
    f"{_SCOPE_PREFIX}.ecg.readonly",
    f"{_SCOPE_PREFIX}.irn.readonly",
    f"{_SCOPE_PREFIX}.location.readonly",
]


class FitbitAuthError(Exception):
    """Raised when authentication cannot be completed."""


def _client_id() -> str:
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not cid:
        raise FitbitAuthError(
            "GOOGLE_CLIENT_ID is not set. Create a Google Cloud OAuth client "
            "(see README) and copy .env.example to .env with your credentials."
        )
    return cid


def _client_secret() -> str:
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not secret:
        raise FitbitAuthError("GOOGLE_CLIENT_SECRET is not set. See the README setup steps.")
    return secret


def _redirect_uri() -> str:
    return os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8080/callback").strip()


def _token_file() -> Path:
    p = Path(os.environ.get("FITBIT_TOKEN_FILE", ".fitbit_tokens.json"))
    return p if p.is_absolute() else PROJECT_ROOT / p


def build_authorize_url(state: str, scopes: Optional[list[str]] = None) -> str:
    """Build the Google authorization URL the user opens in a browser."""
    from urllib.parse import urlencode

    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": " ".join(scopes or DEFAULT_SCOPES),
        "access_type": "offline",  # request a refresh token
        "prompt": "consent",       # always show consent so a refresh token is returned
        "state": state,
        "include_granted_scopes": "true",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


# --- Token persistence ----------------------------------------------------

def _save_tokens(tokens: Dict[str, Any]) -> None:
    tokens = dict(tokens)
    tokens["expires_at"] = time.time() + float(tokens.get("expires_in", 0))
    path = _token_file()
    # Preserve an existing refresh_token if Google omits it on refresh.
    if "refresh_token" not in tokens and path.exists():
        try:
            old = json.loads(path.read_text())
            if old.get("refresh_token"):
                tokens["refresh_token"] = old["refresh_token"]
        except (OSError, json.JSONDecodeError):
            pass
    path.write_text(json.dumps(tokens, indent=2))
    try:
        os.chmod(path, 0o600)  # tokens are sensitive
    except OSError:
        pass


def _seed_tokens_from_env() -> None:
    """On a fresh cloud volume, seed the token file from FITBIT_TOKENS_JSON.

    Lets you authorize locally, then `fly secrets set FITBIT_TOKENS_JSON=...`.
    Subsequent refreshes are written back to the file on the persistent volume.
    """
    path = _token_file()
    raw = os.environ.get("FITBIT_TOKENS_JSON", "").strip()
    if raw and not path.exists():
        try:
            json.loads(raw)  # validate
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
            os.chmod(path, 0o600)
        except (OSError, json.JSONDecodeError):
            pass


def load_tokens() -> Optional[Dict[str, Any]]:
    path = _token_file()
    if not path.exists():
        _seed_tokens_from_env()
    if not path.exists():
        return None
    return json.loads(path.read_text())


# --- Token exchange / refresh ---------------------------------------------

async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens."""
    data = {
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "grant_type": "authorization_code",
        "redirect_uri": _redirect_uri(),
        "code": code,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=data, timeout=30.0)
    if resp.status_code != 200:
        raise FitbitAuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    tokens = resp.json()
    _save_tokens(tokens)
    return tokens


async def _refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    data = {
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=data, timeout=30.0)
    if resp.status_code != 200:
        raise FitbitAuthError(
            f"Token refresh failed ({resp.status_code}): {resp.text}. "
            "In Testing mode refresh tokens expire after 7 days — re-run authorize.py."
        )
    tokens = resp.json()
    _save_tokens(tokens)
    return tokens


async def get_access_token() -> str:
    """Return a valid access token, refreshing it if it is close to expiry."""
    tokens = load_tokens()
    if not tokens:
        raise FitbitAuthError(
            "No stored tokens found. Run:  python authorize.py  to sign in with Google first."
        )

    if time.time() >= float(tokens.get("expires_at", 0)) - 60:
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise FitbitAuthError("Stored token has no refresh_token; re-run authorize.py.")
        tokens = await _refresh_tokens(refresh_token)

    return tokens["access_token"]
