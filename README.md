# OpenAI Agents Demo

This repository demonstrates how to use the OpenAI Agents SDK in Python with various tools and MCP connectors.

## Features

- Web search tool
- File search tool (vector store)
- Sample function tools
- Hosted MCP connectors: Gmail + ClickUp
- Local MCP server: Microsoft MarkItDown
- Invoice extraction and processing
- Gmail to ClickUp integration

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables:
   - `OPENAI_API_KEY` (required)
   - `GMAIL_AUTHORIZATION` (optional)
   - `CLICKUP_AUTHORIZATION` (optional)

## Usage

Run the main demo:
```bash
python src/agents_demo/main.py
```

## Documentation

See the README.md file for detailed setup and usage instructions.