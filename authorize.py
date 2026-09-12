#!/usr/bin/env python3
"""One-time Google Health API OAuth sign-in.

Run this once (and again if the refresh token expires — every 7 days while your
OAuth consent screen is in "Testing" mode):

    python authorize.py

It opens your browser to the Google consent page, catches the redirect on a
local web server, exchanges the code for tokens, and stores them in the file
named by FITBIT_TOKEN_FILE (default: .fitbit_tokens.json).
"""

from __future__ import annotations

import asyncio
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from fitbit_mcp.auth import (
    FitbitAuthError,
    build_authorize_url,
    exchange_code_for_tokens,
    _redirect_uri,
)

_received: dict[str, str] = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") not in ("/callback", ""):
            self.send_response(404)
            self.end_headers()
            return
        qs = parse_qs(parsed.query)
        _received["code"] = qs.get("code", [""])[0]
        _received["state"] = qs.get("state", [""])[0]
        _received["error"] = qs.get("error", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = (
            "<h2>Google Health connected ✓</h2><p>You can close this tab and return to the terminal.</p>"
            if _received["code"]
            else f"<h2>Authorization failed</h2><p>{_received['error']}</p>"
        )
        self.wfile.write(f"<html><body style='font-family:sans-serif'>{msg}</body></html>".encode())

    def log_message(self, *args):
        return


def _port_from_redirect() -> int:
    return urlparse(_redirect_uri()).port or 8080


async def main() -> None:
    state = secrets.token_urlsafe(16)
    url = build_authorize_url(state)

    server = HTTPServer(("localhost", _port_from_redirect()), _CallbackHandler)

    print("Opening your browser to authorize Google Health access...")
    print(f"If it doesn't open, visit this URL manually:\n\n{url}\n")
    import webbrowser
    webbrowser.open(url)
    print(f"Waiting for the redirect on {_redirect_uri()} ...")

    while "code" not in _received and "error" not in _received:
        server.handle_request()
    server.server_close()

    if _received.get("error"):
        raise FitbitAuthError(f"Authorization denied: {_received['error']}")
    if _received.get("state") != state:
        raise FitbitAuthError("State mismatch — possible CSRF. Aborting.")

    print("Exchanging authorization code for tokens...")
    tokens = await exchange_code_for_tokens(_received["code"])
    print("\nSuccess! Tokens saved.")
    print(f"Scopes granted: {tokens.get('scope', 'n/a')}")
    print("You can now run the MCP server:  python -m fitbit_mcp.server")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except FitbitAuthError as e:
        raise SystemExit(f"\nAuth error: {e}")
