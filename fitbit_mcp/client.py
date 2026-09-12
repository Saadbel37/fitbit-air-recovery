"""Thin async client for the Google Health API with auth + error handling."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .auth import get_access_token

API_BASE_URL = "https://health.googleapis.com/v4"


class FitbitAPIError(Exception):
    """Raised when a Google Health API request fails with an actionable message."""


def _format_http_error(e: httpx.HTTPStatusError) -> str:
    status = e.response.status_code
    body = e.response.text[:400]
    if status == 400:
        return f"Error: Bad request. Check the data_type, date range, or filter. Details: {body}"
    if status == 401:
        return "Error: Unauthorized. Your access token is invalid or expired. Re-run authorize.py."
    if status == 403:
        return (
            "Error: Forbidden. Your OAuth client may lack the required scope for this data type, "
            "the Google Health API may not be enabled, or your account isn't in the Test users list. "
            f"Details: {body}"
        )
    if status == 404:
        return "Error: Not found. No data exists for that resource, or the data type is unsupported."
    if status == 429:
        retry = e.response.headers.get("Retry-After", "a while")
        return f"Error: Rate limit exceeded. Retry after {retry} seconds."
    return f"Error: Google Health API returned status {status}. Details: {body}"


async def _request(method: str, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
    token = await get_access_token()
    url = f"{API_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    headers.update(kwargs.pop("headers", {}))
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=headers, timeout=30.0, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
    except httpx.HTTPStatusError as e:
        raise FitbitAPIError(_format_http_error(e)) from e
    except httpx.TimeoutException as e:
        raise FitbitAPIError("Error: Request timed out. Please try again.") from e
    except httpx.HTTPError as e:
        raise FitbitAPIError(f"Error: Network error: {type(e).__name__}") from e


async def health_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Authenticated GET against the Google Health API. `endpoint` begins with '/'."""
    return await _request("GET", endpoint, params=params)


async def health_post(endpoint: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Authenticated POST against the Google Health API. `endpoint` begins with '/'."""
    return await _request("POST", endpoint, json=json_body or {})
