import base64
import hashlib
import json
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_FILE = str(PROJECT_ROOT / "credentials.json")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
REDIRECT_URI = "http://localhost"

# Allow http redirect for localhost (standard for installed apps)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def get_auth_url() -> tuple[str, str]:
    """Returns (auth_url, code_verifier). Store code_verifier — needed for exchange."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode()

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return auth_url, code_verifier


def exchange_code(raw: str, code_verifier: str) -> str:
    """Exchange auth code (or full redirect URL) for credentials JSON string."""
    code = _parse_code(raw)
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=code, code_verifier=code_verifier)
    return flow.credentials.to_json()


def get_service(token_json: str):
    """Build Gmail API service, refreshing token if expired.
    Returns (service, updated_token_json).
    """
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    updated_json = token_json
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        updated_json = creds.to_json()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return service, updated_json


def get_gmail_address(service) -> str:
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "")


def _parse_code(url_or_code: str) -> str:
    """Extract code from redirect URL, or return bare code as-is."""
    url_or_code = url_or_code.strip()
    if "code=" in url_or_code:
        params = parse_qs(urlparse(url_or_code).query)
        codes = params.get("code", [])
        if codes:
            return codes[0]
    return url_or_code
