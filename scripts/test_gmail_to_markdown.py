#!/usr/bin/env python3
"""Test Gmail to Markdown conversion."""
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
from agents_demo.main import gmail_query_to_markdown

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_gmail_to_markdown.py <gmail_query> [output_filename]")
        sys.exit(1)
    
    query = sys.argv[1]
    output_filename = sys.argv[2] if len(sys.argv) > 2 else "gmail_test.md"
    
    print(f"Converting Gmail query to Markdown: {query}")
    result_path = gmail_query_to_markdown(query, output_filename)
    print(f"Markdown saved to: {result_path}")

if __name__ == "__main__":
    main()
