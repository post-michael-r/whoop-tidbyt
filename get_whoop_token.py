import os
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import load_dotenv

AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "read:cycles offline"


class CallbackHandler(BaseHTTPRequestHandler):
    result = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        CallbackHandler.result = {k: v[0] for k, v in params.items()}

        body = (
            b"<html><body style='font-family:sans-serif'>"
            b"<h2>Authorization received.</h2>"
            b"<p>You can close this tab and return to the terminal.</p>"
            b"</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        pass


def main():
    load_dotenv()
    client_id = os.environ.get("WHOOP_CLIENT_ID")
    client_secret = os.environ.get("WHOOP_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Missing WHOOP_CLIENT_ID or WHOOP_CLIENT_SECRET in .env")

    state = secrets.token_urlsafe(24)
    auth_url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
    })

    print()
    print("Open this URL in your browser to authorize:")
    print()
    print(f"  {auth_url}")
    print()
    print("Attempting to open it automatically...")
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        print(f"  (could not open browser automatically: {e})")

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    print()
    print("Waiting for callback on http://localhost:8080/callback ...")
    try:
        while CallbackHandler.result is None:
            server.handle_request()
    finally:
        server.server_close()

    result = CallbackHandler.result
    if "error" in result:
        sys.exit(
            f"Authorization failed: {result.get('error')} "
            f"{result.get('error_description', '')}"
        )
    if result.get("state") != state:
        sys.exit("State parameter mismatch; aborting.")
    code = result.get("code")
    if not code:
        sys.exit("No code returned in callback.")

    print()
    print("Code received. Exchanging for tokens...")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Token exchange failed: HTTP {resp.status_code}\n{resp.text}")

    tokens = resp.json()
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    if not refresh_token:
        sys.exit(f"No refresh_token in response: {tokens}")

    print()
    print("Success.")
    print()
    print(f"Access token (debug, first 20 chars): {access_token[:20]}...")
    print()
    print("Refresh token (copy this into .env as WHOOP_REFRESH_TOKEN):")
    print()
    print(f"  {refresh_token}")
    print()


if __name__ == "__main__":
    main()
