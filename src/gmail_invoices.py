"""
Gmail Invoices wrapper
----------------------

Developer notes:
- This module is a thin wrapper around existing Gmail helpers in this repo (see `agents_demo.main`).
- The public surface is frozen; downstream orchestration should call only the three functions below.
- Parsing/normalization of uploaded PDFs happens in the planning app; this module does not parse PDFs.

Public API:
- list_invoice_attachments(query: str, lookback_days: int) -> list[AttachmentRef]
- download_attachment(ref: AttachmentRef) -> bytes
- upload_pdf_to_planner(pdf_bytes: bytes, *, source_message_id: str | None = None) -> InsertReport

Data contracts (dict-like):
- AttachmentRef:
    message_id: str
    attachment_id: str
    filename: str
    mime_type: str
    size_bytes: int
    thread_id: str
    subject: str
    from_address: str
    received_at: str (ISO8601)

- InsertReport:
    created_order_ids: list[str|int]
    warnings: list[str]
    errors: list[str]
    source_message_id: str
    notes: str (optional)
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

# Reuse existing Gmail helpers only; do not call Gmail API directly here.
from agents_demo.main import (
    _gmail_list_messages_with_attachments_impl,  # token-based helper
    gmail_download_attachment,  # env-token helper; saves to disk and returns path
)


AttachmentRef = Dict[str, Any]
InsertReport = Dict[str, Any]


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def _append_lookback_to_query(query: str, lookback_days: int) -> str:
    q = (query or "").strip()
    tokens = q.lower().split()
    has_attachment = any(t.startswith("has:attachment") for t in tokens)
    has_newer_than = any(t.startswith("newer_than:") for t in tokens)
    if not has_attachment:
        q = f"{q} has:attachment".strip()
    if lookback_days and lookback_days > 0 and not has_newer_than:
        q = f"{q} newer_than:{int(lookback_days)}d".strip()
    return q


def _ms_to_iso8601(ms: Any) -> str:
    try:
        # Gmail internalDate is epoch ms as string
        ms_int = int(ms)
        dt = datetime.fromtimestamp(ms_int / 1000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        # Fallback to empty string if not parseable
        return ""


def list_invoice_attachments(query: str, lookback_days: int) -> List[AttachmentRef]:
    """List invoice-like Gmail attachments without downloading bytes.

    Reuses the repo's Gmail helpers (no direct Gmail API calls here).

    Args:
        query: Gmail search query (e.g., "in:inbox filename:pdf").
        lookback_days: Days to include using Gmail's newer_than filter.

    Returns:
        A list of dicts with keys: message_id, attachment_id, filename, mime_type,
        size_bytes, thread_id, subject, from_address, received_at (ISO8601).

    Notes:
        - Prefers PDFs for upload later, but returns any attachment types provided by the helper.
        - Some metadata (e.g., from_address, thread_id) may be unavailable from the
          helper; in such cases, fields are present but may be empty strings.

    Raises:
        RuntimeError: If Gmail authorization is not configured.
    """
    token = _require_env("GMAIL_AUTHORIZATION")
    q = _append_lookback_to_query(query, lookback_days)

    # Use the message-grouping helper so we can capture subjects and dates.
    msgs = _gmail_list_messages_with_attachments_impl(
        token, q, max_results=50, mime_types=None
    )

    out: List[AttachmentRef] = []
    for m in msgs:
        mid = str(m.get("messageId") or "")
        subject = str(m.get("subject") or "")
        received_at = _ms_to_iso8601(m.get("internalDate"))
        # thread_id and from_address are not exposed by the helper; leave empty.
        thread_id = ""
        from_address = ""
        for a in (m.get("attachments") or []):
            out.append(
                {
                    "message_id": mid,
                    "attachment_id": str(a.get("attachmentId") or ""),
                    "filename": str(a.get("filename") or ""),
                    "mime_type": str(a.get("mimeType") or ""),
                    "size_bytes": int(a.get("size") or 0),
                    "thread_id": thread_id,
                    "subject": subject,
                    "from_address": from_address,
                    "received_at": received_at,
                }
            )
    return out


def download_attachment(ref: AttachmentRef) -> bytes:
    """Download a specific Gmail attachment's raw bytes.

    Args:
        ref: AttachmentRef dict as returned by `list_invoice_attachments`.

    Returns:
        The raw attachment bytes.

    Behavior:
        - Reuses the repo's Gmail download helper (which saves to disk) and reads the bytes.
        - This function itself does not persist data; the helper may write a temp file.

    Raises:
        ValueError: If required identifiers are missing from `ref`.
        RuntimeError: If download fails or file cannot be read.
    """
    if not isinstance(ref, dict):
        raise ValueError("ref must be a dict AttachmentRef")
    message_id = ref.get("message_id") or ref.get("messageId")
    attachment_id = ref.get("attachment_id") or ref.get("attachmentId")
    if not message_id or not attachment_id:
        raise ValueError("AttachmentRef must include 'message_id' and 'attachment_id'")

    # Delegate to existing helper that returns a saved path; read and cleanup.
    # Use a short, stable filename hint when possible.
    preferred_name = ref.get("filename") or f"gmail_{attachment_id}"
    path = gmail_download_attachment(str(message_id), str(attachment_id), filename=preferred_name)

    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to read downloaded attachment from {path}: {e}") from e
    finally:
        try:
            # Best-effort cleanup; ignore errors.
            import os as _os

            _os.remove(path)
        except Exception:
            pass

    return data


def upload_pdf_to_planner(
    pdf_bytes: bytes, *, source_message_id: str | None = None
) -> InsertReport:
    """Upload a PDF to the planning app for ingestion as Pending Orders.

    Args:
        pdf_bytes: Raw PDF bytes to upload. Only application/pdf is eligible.
        source_message_id: Optional Gmail message id to include in the returned report.

    Returns:
        InsertReport dict with keys: created_order_ids, warnings, errors, source_message_id, notes.

    Raises:
        RuntimeError: On missing configuration or non-200 HTTP responses.
        TimeoutError: On request timeout (30s default).
        ValueError: If input bytes are empty or not a PDF header.
    """
    if not isinstance(pdf_bytes, (bytes, bytearray)) or len(pdf_bytes) == 0:
        raise ValueError("pdf_bytes must be non-empty bytes")

    # Light PDF sanity check: starts with %PDF
    try:
        if not bytes(pdf_bytes[:4]).startswith(b"%PDF"):
            raise ValueError("Only application/pdf content can be uploaded")
    except Exception:
        # If slicing/bytes() fails oddly, still enforce non-empty
        pass

    base = _require_env("PLANNER_API_BASE").rstrip("/")
    api_key = os.getenv("PLANNER_API_KEY") or ""
    url = f"{base}/orders/pending/upload-pdf"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    files = {"file": ("invoice.pdf", pdf_bytes, "application/pdf")}

    try:
        resp = requests.post(url, headers=headers, files=files, timeout=30)
    except requests.Timeout as e:
        raise TimeoutError("Upload to planning app timed out after 30s") from e
    except Exception as e:
        raise RuntimeError(f"Failed to upload PDF to planner: {e}") from e

    if resp.status_code < 200 or resp.status_code >= 300:
        # Friendly error with short body excerpt (avoid logging secrets)
        text = (resp.text or "")[:200]
        raise RuntimeError(f"Planner upload failed: HTTP {resp.status_code}: {text}")

    try:
        data = resp.json() if hasattr(resp, "json") else {}
    except Exception:
        data = {}

    # Adapt to InsertReport
    created = data.get("created_order_ids")
    if created is None:
        created = data.get("created")
    if created is None:
        created = []

    warnings = data.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]

    errors = data.get("errors") or []
    if isinstance(errors, str):
        errors = [errors]

    notes = data.get("notes") or data.get("detail") or ""

    return {
        "created_order_ids": created,
        "warnings": warnings,
        "errors": errors,
        "source_message_id": source_message_id or "",
        "notes": notes,
    }


__all__ = [
    "list_invoice_attachments",
    "download_attachment",
    "upload_pdf_to_planner",
]