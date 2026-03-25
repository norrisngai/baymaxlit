"""Google Calendar OAuth + service helpers extracted from web_app.py.

Kept intentionally minimal and optional-import friendly.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import web_db

try:
    import local_secrets  # type: ignore
except Exception:  # pragma: no cover
    local_secrets = None

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    Flow = None
    Credentials = None
    Request = None
    build = None


def load_google_client_config() -> Optional[dict[str, Any]]:
    """Loads Google OAuth client config.

    Expected env: GOOGLE_OAUTH_CLIENT_SECRETS_FILE pointing to a JSON file
    downloaded from Google Cloud Console (OAuth client ID).
    """
    raw_json = os.environ.get("GOOGLE_OAUTH_CLIENT_CONFIG_JSON")
    if raw_json:
        try:
            return json.loads(raw_json)
        except Exception:
            pass

    path = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRETS_FILE")
    if not path and local_secrets is not None:
        path = getattr(local_secrets, "GOOGLE_OAUTH_CLIENT_SECRETS_FILE", None)
    if not path:
        # Default to project-local file if present.
        path = "google_oauth_client.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def google_scopes() -> list[str]:
    # events scope lets us create/update calendar events.
    return ["https://www.googleapis.com/auth/calendar.events"]


def get_google_creds_for_user(user_id: int) -> Optional[Any]:
    if not Credentials or not Request:
        return None
    row = web_db.get_google_token(user_id=user_id)
    if not row:
        return None
    try:
        token_data = json.loads(row.get("token_json") or "{}")
    except Exception:
        token_data = {}
    creds = Credentials(**token_data)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist refreshed token.
        web_db.upsert_google_token(user_id=user_id, token_json=creds.to_json())
    return creds


def get_calendar_service(user_id: int):
    if not build:
        return None
    creds = get_google_creds_for_user(user_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)
