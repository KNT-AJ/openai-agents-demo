#!/usr/bin/env python3
"""Sync Gmail inbox to ClickUp list."""
import os
import sys
from pathlib import Path

# Load .env if present
try:
    from dotenv import dotenv_values
    os.environ.update({k: v for k, v in dotenv_values(".env").items() if v})
except Exception:
    pass

# Ensure imports from src
sys.path.insert(0, str(Path.cwd() / "src"))
from agents_demo.main import gmail_ingest_inbox_to_clickup_list_impl

def main():
    if len(sys.argv) < 2:
        print("Usage: python sync_gmail_inbox_to_clickup_list.py <clickup_list_id> [gmail_query] [max_messages]")
        sys.exit(1)
    
    list_id = sys.argv[1]
    gmail_query = sys.argv[2] if len(sys.argv) > 2 else "in:inbox newer_than:14d has:attachment"
    max_messages = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    
    print(f"Syncing Gmail to ClickUp list: {list_id}")
    print(f"Gmail query: {gmail_query}")
    print(f"Max messages: {max_messages}")
    
    result = gmail_ingest_inbox_to_clickup_list_impl(
        list_id=list_id,
        gmail_query=gmail_query,
        max_messages=max_messages,
        pdf_only=True,
        create_item_subtasks=True,
    )
    
    print("Sync result:", result)

if __name__ == "__main__":
    main()
