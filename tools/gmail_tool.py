"""
Orchestrator -- gmail_tool.py

Two Orchestrator-level tools for Gmail access during troubleshooting sessions:
  search_gmail       -- search messages by Gmail query syntax, return metadata
  read_email_thread  -- read full thread content (all messages, plain text body)

Reuses OAuth credentials from the local Gmail MCP server files.
Supports two accounts:
  personal  -- your personal Gmail      (HOME/.gmail-mcp/credentials.json)
  work      -- your work Gmail          (HOME/gmail-work-home/.gmail-mcp/credentials.json)

Token refresh is automatic. If the stored access token is expired or within
60 seconds of expiry, the tool refreshes it using the stored refresh_token
and saves the new token back to the credentials file.
"""

import base64
import json
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Credential paths
# ---------------------------------------------------------------------------

_HOME = Path.home()

CRED_PATHS = {
    "personal": _HOME / ".gmail-mcp" / "credentials.json",
    "work":     _HOME / "gmail-work-home" / ".gmail-mcp" / "credentials.json",
}

OAUTH_KEYS_PATH = _HOME / ".gmail-mcp" / "gcp-oauth.keys.json"

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

MAX_BODY_CHARS = 4000


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _load_oauth_keys():
    data = json.loads(OAUTH_KEYS_PATH.read_text(encoding="utf-8"))
    installed = data.get("installed", data)
    return installed["client_id"], installed["client_secret"], installed["token_uri"]


def _load_creds(account: str) -> dict:
    return json.loads(CRED_PATHS[account].read_text(encoding="utf-8"))


def _save_creds(account: str, creds: dict):
    CRED_PATHS[account].write_text(json.dumps(creds, indent=2), encoding="utf-8")


def _refresh(account: str) -> str:
    creds = _load_creds(account)
    client_id, client_secret, token_uri = _load_oauth_keys()
    resp = httpx.post(
        token_uri,
        data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": creds["refresh_token"],
            "grant_type":    "refresh_token",
        },
        timeout=15,
        verify=False,
    )
    resp.raise_for_status()
    new = resp.json()
    creds["access_token"] = new["access_token"]
    creds["expiry_date"]  = int((time.time() + new.get("expires_in", 3600)) * 1000)
    _save_creds(account, creds)
    return creds["access_token"]


def _get_token(account: str) -> str:
    creds = _load_creds(account)
    expiry_ms = creds.get("expiry_date", 0)
    if not expiry_ms or (expiry_ms / 1000) < (time.time() + 60):
        return _refresh(account)
    return creds["access_token"]


def _gmail_get(account: str, path: str, params: dict = None) -> dict:
    """GET to Gmail API with automatic 401 token refresh."""
    token = _get_token(account)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GMAIL_BASE}{path}"
    resp = httpx.get(url, headers=headers, params=params or {}, timeout=20, verify=False)
    if resp.status_code == 401:
        token = _refresh(account)
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=20,
            verify=False,
        )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Body extraction
# ---------------------------------------------------------------------------

def _header_value(headers_list: list, name: str) -> str:
    return next(
        (h["value"] for h in headers_list if h["name"].lower() == name.lower()),
        "",
    )


def _extract_body(payload: dict) -> str:
    """Recursively extract the first plain-text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            padded = data + "=" * (-len(data) % 4)
            return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace").strip()
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_body(part)
            if text:
                return text
    return ""


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------

def search_gmail(account: str, query: str, max_results: int = 10) -> dict:
    """
    Search Gmail for messages matching query.
    Returns {message_id, thread_id, subject, from, date} for each result.

    account     : "personal" or "work"
    query       : Gmail search syntax (e.g. "AOAG disconnected after:2026/06/01")
    max_results : max messages to return (default 10)
    """
    if account not in ("personal", "work"):
        return {"error": f"Invalid account '{account}'. Use 'personal' or 'work'."}

    try:
        data = _gmail_get(account, "/messages", {"q": query, "maxResults": max_results})
        messages = data.get("messages", [])
        if not messages:
            return {"account": account, "query": query, "results": [], "count": 0}

        results = []
        for msg in messages:
            meta = _gmail_get(
                account,
                f"/messages/{msg['id']}",
                {"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            hdrs = meta.get("payload", {}).get("headers", [])
            results.append({
                "message_id": msg["id"],
                "thread_id":  meta.get("threadId", ""),
                "subject":    _header_value(hdrs, "Subject"),
                "from":       _header_value(hdrs, "From"),
                "date":       _header_value(hdrs, "Date"),
            })

        return {"account": account, "query": query, "results": results, "count": len(results)}

    except Exception as e:
        return {"error": str(e)}


def read_email_thread(account: str, thread_id: str) -> dict:
    """
    Read the full content of an email thread.
    Returns all messages with from/date/subject and plain-text body
    (truncated at 4000 chars per message).

    account   : "personal" or "work"
    thread_id : thread ID from search_gmail results
    """
    if account not in ("personal", "work"):
        return {"error": f"Invalid account '{account}'. Use 'personal' or 'work'."}

    try:
        data = _gmail_get(account, f"/threads/{thread_id}", {"format": "full"})
        raw_messages = data.get("messages", [])

        messages = []
        for msg in raw_messages:
            payload = msg.get("payload", {})
            hdrs    = payload.get("headers", [])
            body    = _extract_body(payload)
            messages.append({
                "message_id": msg["id"],
                "from":       _header_value(hdrs, "From"),
                "date":       _header_value(hdrs, "Date"),
                "subject":    _header_value(hdrs, "Subject"),
                "body":       body[:MAX_BODY_CHARS] if body else "(no plain text body)",
            })

        return {
            "account":       account,
            "thread_id":     thread_id,
            "message_count": len(messages),
            "messages":      messages,
        }

    except Exception as e:
        return {"error": str(e)}
