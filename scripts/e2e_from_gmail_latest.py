#!/usr/bin/env python3
import os
import re
import sys
import json
from pathlib import Path


def choose_invoice_attachment(atts: list[dict]) -> tuple[int, dict] | None:
    # Return (1-based index, attachment dict)
    # Preference order in filename: commercial invoice > invoice > proforma > pi
    patterns = [
        re.compile(r"commercial\s*invoice", re.I),
        re.compile(r"\binvoice\b", re.I),
        re.compile(r"proforma\s*invoice|\bproforma\b", re.I),
        re.compile(r"^pi\b|\bpi\b", re.I),
    ]
    for pat in patterns:
        for i, a in enumerate(atts, start=1):
            fn = a.get("filename") or a.get("title") or ""
            if pat.search(fn):
                return (i, a)
    if atts:
        return (1, atts[0])
    return None


def main():
    # Inputs
    task_id = os.getenv("TEST_CLICKUP_TASK", "868fed69e")
    days = int(os.getenv("GMAIL_SEARCH_DAYS", "14"))
    query = os.getenv(
        "GMAIL_SEARCH_QUERY",
        f"in:inbox newer_than:{days}d has:attachment filename:pdf",
    )

    # Load .env if present
    try:
        from dotenv import dotenv_values
        os.environ.update({k: v for k, v in dotenv_values(".env").items() if v})
    except Exception:
        pass

    # Ensure imports from src
    sys.path.insert(0, str(Path.cwd() / "src"))
    from agents_demo.main import (
        _gmail_list_attachments_impl,
        _gmail_download_attachment_impl,
        clickup_update_task_custom_fields_from_invoice_impl,
        clickup_create_subtasks_from_invoice_line_items_impl,
    )
    from agents import Agent, Runner
    from agents_demo.schemas import Invoice

    token = os.getenv("GMAIL_AUTHORIZATION")
    if not token:
        print("GMAIL_AUTHORIZATION missing in env.")
        sys.exit(1)

    print(f"Listing Gmail attachments with query: {query}")
    atts = _gmail_list_attachments_impl(token, query, max_results=50, mime_types=["application/pdf"])
    if not atts:
        print("No attachments found.")
        sys.exit(2)

    choice = choose_invoice_attachment(atts)
    if not choice:
        print("No suitable invoice-like attachment found.")
        sys.exit(3)
    idx, att = choice
    print(f"Chosen index={idx}, filename={att.get('filename')}, messageId={att.get('messageId')}")

    # Download
    out_pdf = _gmail_download_attachment_impl(
        token, att["messageId"], att["attachmentId"], filename=att.get("filename") or f"gmail_{att['attachmentId']}.pdf"
    )
    print(f"Downloaded: {out_pdf}")

    # Convert to Markdown using markitdown library
    try:
        from markitdown import MarkItDown
    except Exception as e:
        print("markitdown not installed; run: pip install 'markitdown[all]'")
        sys.exit(4)

    md = MarkItDown(enable_plugins=False)
    result = md.convert(out_pdf)
    converted_dir = Path("data/converted"); converted_dir.mkdir(parents=True, exist_ok=True)
    md_path = converted_dir / "gmail_latest_invoice.md"
    md_path.write_text(result.text_content, encoding="utf-8")
    print(f"Markdown saved to: {md_path}")

    # Extract invoice via an Agent
    model = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5-nano")
    extractor = Agent(
        name="Invoice/Quote extractor",
        instructions=(
            "You extract invoice or quote data from text. "
            "Identify invoice/quote number, dates, vendor/buyer details, currency, subtotal, tax, total, "
            "PO number, and line items. For line items, extract product/name/description, quantity, unit, unit_price, amount. "
            "Return only what is present and reasonable."
        ),
        output_type=Invoice,
        model=model,
    )

    res = Runner.run_sync(extractor, input=result.text_content)
    from dataclasses import asdict
    invoice = asdict(res.final_output)
    print("Extracted keys:", list(invoice.keys()))
    # Filter out None values for clarity when posting
    invoice_clean = {k: v for k, v in invoice.items() if v not in (None, "")}
    invoice_json = json.dumps(invoice_clean)

    # Update ClickUp fields
    print(f"Updating ClickUp task: {task_id}")
    upd = clickup_update_task_custom_fields_from_invoice_impl(
        task_id=task_id,
        invoice_json=invoice_json,
        field_map_json="",
        update_description=True,
        auto_create_missing=True,
    )
    print("Update result:", upd)

    # Create subtasks from line items
    if invoice_clean.get("line_items"):
        subres = clickup_create_subtasks_from_invoice_line_items_impl(
            task_id=task_id,
            invoice_json=json.dumps({"line_items": invoice_clean["line_items"]}),
            auto_create_missing=True,
        )
        print("Subtasks:", subres)
    else:
        print("No line_items found; skipped subtask creation.")


if __name__ == "__main__":
    main()
