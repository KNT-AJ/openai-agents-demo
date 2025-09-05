#!/usr/bin/env python3
"""Update ClickUp task from a markdown file."""
import os
import sys
import json
from pathlib import Path

# Load .env if present
try:
    from dotenv import dotenv_values
    os.environ.update({k: v for k, v in dotenv_values(".env").items() if v})
except Exception:
    pass

# Ensure imports from src
sys.path.insert(0, str(Path.cwd() / "src"))
from agents_demo.main import (
    extract_invoice_from_markdown,
    clickup_update_task_custom_fields_from_invoice_impl,
    clickup_create_subtasks_from_invoice_line_items_impl,
)

def main():
    if len(sys.argv) < 3:
        print("Usage: python e2e_update_clickup_from_md.py <markdown_file> <clickup_task_id>")
        sys.exit(1)
    
    md_file = sys.argv[1]
    task_id = sys.argv[2]
    
    if not Path(md_file).exists():
        print(f"File not found: {md_file}")
        sys.exit(1)
    
    print(f"Extracting invoice from: {md_file}")
    invoice_json = extract_invoice_from_markdown(md_file)
    
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
    invoice = json.loads(invoice_json)
    if invoice.get("line_items"):
        subres = clickup_create_subtasks_from_invoice_line_items_impl(
            task_id=task_id,
            invoice_json=json.dumps({"line_items": invoice["line_items"]}),
            auto_create_missing=True,
        )
        print("Subtasks:", subres)
    else:
        print("No line_items found; skipped subtask creation.")

if __name__ == "__main__":
    main()
