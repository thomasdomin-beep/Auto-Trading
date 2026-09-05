from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import BaseModel

from mcx_atp.config import AppConfig

logger = logging.getLogger(__name__)

API_BASE = "https://a3.aliceblueonline.com/"
LOGIN_URL_TMPL = "https://ant.aliceblueonline.com/?appcode={app_code}"
GET_USER_DETAILS_PATH = "open-api/od/v1/vendor/getUserDetails"


class AliceblueAuthError(RuntimeError):
    pass


class AliceblueSession(BaseModel):
    client_id: str
    user_session: str
    saved_at: datetime


def load_session(path: Path) -> AliceblueSession | None:
    if not path.is_file():
        return None
    try:
        return AliceblueSession.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_session(path: Path, session: AliceblueSession) -> None:
    path.write_text(session.model_dump_json(), encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600: owner read/write only
    except OSError:
        pass


class _CallbackResult:
    def __init__(self) -> None:
        self.auth_code: str | None = None
        self.user_id: str | None = None
        self.error: str | None = None


def _wait_for_redirect(host: str, port: int, timeout: float) -> _CallbackResult:
    result = _CallbackResult()
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            logger.debug(format, *args)

        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            result.auth_code = (query.get("authCode") or [None])[0]
            result.user_id = (query.get("userId") or [None])[0]
            if not result.auth_code or not result.user_id:
                result.error = f"Callback missing authCode/userId (got query: {query})"
            body = (
                b"<html><body><h3>Aliceblue login complete.</h3>"
                b"<p>You can close this tab and return to the terminal.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

    server = HTTPServer((host, port), Handler)
    server.timeout = timeout
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout + 5)
    server.server_close()
    if not done.is_set():
        result.error = result.error or "Timed out waiting for Aliceblue login redirect"
    return result


def perform_login(cfg: AppConfig, timeout: float = 300.0) -> AliceblueSession:
    """One-time (per session) browser login against the Aliceblue Developer
    Portal App, following the appCode/authCode/apiSecret checksum flow.

    Opens a real browser tab; the user logs into Aliceblue there. Requires
    the App's configured Redirect URL to be
    http://{cfg.redirect_host}:{cfg.redirect_port}/ (or a path under it).
    """
    if cfg.app_code is None or cfg.api_secret is None:
        raise AliceblueAuthError(
            "MCX_ATP_APP_CODE / MCX_ATP_API_SECRET are not set. Export them as "
            "environment variables (or put them in a local .env file) before "
            "running `mcx-atp login`. Never put them in config.yaml."
        )
    app_code = cfg.app_code.get_secret_value()
    api_secret = cfg.api_secret.get_secret_value()

    login_url = LOGIN_URL_TMPL.format(app_code=app_code)
    print(f"Opening browser for Aliceblue login:\n  {login_url}")
    print(
        f"Waiting for redirect on http://{cfg.redirect_host}:{cfg.redirect_port}/ "
        f"(timeout {int(timeout)}s)..."
    )
    webbrowser.open(login_url)

    result = _wait_for_redirect(cfg.redirect_host, cfg.redirect_port, timeout)
    if result.error or not result.auth_code or not result.user_id:
        raise AliceblueAuthError(result.error or "Login redirect did not include authCode/userId")

    checksum = hashlib.sha256(
        (result.user_id + result.auth_code + api_secret).encode("utf-8")
    ).hexdigest()

    with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
        resp = client.post(GET_USER_DETAILS_PATH, json={"checkSum": checksum})
    try:
        body = resp.json()
    except ValueError as exc:
        raise AliceblueAuthError(f"Non-JSON response from getUserDetails: {resp.text[:200]}") from exc

    if resp.status_code != 200 or body.get("stat") != "Ok":
        raise AliceblueAuthError(f"Aliceblue login failed: {body.get('emsg') or body}")

    session = AliceblueSession(
        client_id=body["clientId"],
        user_session=body["userSession"],
        saved_at=datetime.now(timezone.utc),
    )
    save_session(cfg.session_file, session)
    print(f"Login OK for client {session.client_id}. Session saved to {cfg.session_file}.")
    return session
