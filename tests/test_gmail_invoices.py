import os
import sys
from typing import Any

import pytest


# Ensure 'src' is importable when running tests from repo root
ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def test_list_invoice_attachments_basic(monkeypatch):
    os.environ["GMAIL_AUTHORIZATION"] = "test-token"

    # Fake Gmail helper output: one message with two attachments (pdf + non-pdf)
    sample = [
        {
            "messageId": "m1",
            "subject": "Invoice ABC",
            "internalDate": "1725478294000",  # epoch ms
            "attachments": [
                {
                    "attachmentId": "a1",
                    "filename": "inv.pdf",
                    "mimeType": "application/pdf",
                    "size": 1234,
                },
                {
                    "attachmentId": "a2",
                    "filename": "image.png",
                    "mimeType": "image/png",
                    "size": 999,
                },
            ],
        }
    ]

    def fake_list_impl(token: str, q: str, max_results: int = 25, mime_types=None):
        assert token == "test-token"
        assert "has:attachment" in q
        assert "newer_than:" in q
        return sample

    monkeypatch.setattr(
        "agents_demo.main._gmail_list_messages_with_attachments_impl", fake_list_impl
    )

    from gmail_invoices import list_invoice_attachments

    out = list_invoice_attachments("in:inbox", 14)
    assert isinstance(out, list)
    assert len(out) == 2
    for item in out:
        # Required keys
        for key in [
            "message_id",
            "attachment_id",
            "filename",
            "mime_type",
            "size_bytes",
            "thread_id",
            "subject",
            "from_address",
            "received_at",
        ]:
            assert key in item
        # Types
        assert isinstance(item["message_id"], str)
        assert isinstance(item["attachment_id"], str)
        assert isinstance(item["filename"], str)
        assert isinstance(item["mime_type"], str)
        assert isinstance(item["size_bytes"], int)
        assert isinstance(item["thread_id"], str)
        assert isinstance(item["subject"], str)
        assert isinstance(item["from_address"], str)
        assert isinstance(item["received_at"], str)


def test_download_attachment_reads_bytes(monkeypatch, tmp_path):
    from gmail_invoices import download_attachment

    # Create a fake downloaded file
    p = tmp_path / "test.pdf"
    content = b"%PDF-1.7\n...bytes..."
    p.write_bytes(content)

    # Mock the helper to return the path
    def fake_download(message_id: str, attachment_id: str, filename: str | None = None) -> str:
        assert message_id == "m1"
        assert attachment_id == "a1"
        return str(p)

    monkeypatch.setattr("agents_demo.main.gmail_download_attachment", fake_download)

    ref = {
        "message_id": "m1",
        "attachment_id": "a1",
        "filename": "inv.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 10,
        "thread_id": "",
        "subject": "Invoice",
        "from_address": "",
        "received_at": "2024-09-04T00:00:00Z",
    }
    data = download_attachment(ref)
    assert data == content


def test_upload_pdf_to_planner_success(monkeypatch):
    os.environ["PLANNER_API_BASE"] = "http://planner.local"
    os.environ["PLANNER_API_KEY"] = "testkey"

    class DummyResp:
        status_code = 200

        def json(self) -> Any:
            return {
                "created_order_ids": ["123"],
                "warnings": ["minor"],
                "errors": [],
                "notes": "ok",
            }

        @property
        def text(self) -> str:
            return "{\"notes\":\"ok\"}"

    def fake_post(url, headers=None, files=None, timeout=None):
        assert url.endswith("/orders/pending/upload-pdf")
        assert headers.get("Authorization") == "Bearer testkey"
        assert files and "file" in files
        filename, body, mime = files["file"]
        assert filename == "invoice.pdf"
        assert isinstance(body, (bytes, bytearray))
        assert mime == "application/pdf"
        assert timeout == 30
        return DummyResp()

    monkeypatch.setattr("requests.post", fake_post)

    from gmail_invoices import upload_pdf_to_planner

    res = upload_pdf_to_planner(b"%PDF-1.4\n...", source_message_id="m1")
    assert res["created_order_ids"] == ["123"]
    assert res["warnings"] == ["minor"]
    assert res["errors"] == []
    assert res["source_message_id"] == "m1"
    assert res["notes"] == "ok"


def test_upload_pdf_to_planner_timeout(monkeypatch):
    import requests as _req

    os.environ["PLANNER_API_BASE"] = "http://planner.local"
    os.environ["PLANNER_API_KEY"] = "testkey"

    def fake_post(url, headers=None, files=None, timeout=None):
        raise _req.Timeout("timeout")

    monkeypatch.setattr("requests.post", fake_post)

    from gmail_invoices import upload_pdf_to_planner

    with pytest.raises(TimeoutError):
        upload_pdf_to_planner(b"%PDF-1.4\n...", source_message_id="m1")


def test_upload_pdf_to_planner_error_status(monkeypatch):
    os.environ["PLANNER_API_BASE"] = "http://planner.local"
    os.environ["PLANNER_API_KEY"] = "testkey"

    class DummyResp:
        status_code = 400

        def json(self):
            return {"error": "bad"}

        @property
        def text(self) -> str:
            return "Bad request: invalid PDF"

    def fake_post(url, headers=None, files=None, timeout=None):
        return DummyResp()

    monkeypatch.setattr("requests.post", fake_post)

    from gmail_invoices import upload_pdf_to_planner

    with pytest.raises(RuntimeError) as ei:
        upload_pdf_to_planner(b"%PDF-1.4\n...")
    assert "HTTP 400" in str(ei.value)