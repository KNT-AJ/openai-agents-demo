**Agents SDK Demo (Python)**

This repo shows how to use the OpenAI Agents SDK in Python with:

- Web search tool
- File search tool (vector store)
- A sample function tool
- Hosted MCP connectors: Gmail + ClickUp
- Local MCP server: Microsoft MarkItDown

It targets GPT‑5 models (default: `gpt-5-chat-latest`).

Follow the official docs for details and latest updates:
- Tools, Connectors, MCP: https://platform.openai.com/docs/guides/tools-connectors-mcp
- Agents SDK (Python): https://openai.github.io/openai-agents-python/

---

**Prerequisites**

- Python 3.10+
- OpenAI API key with `OPENAI_API_KEY` set

Optional (enable additional tools):
- Gmail connector OAuth token (`GMAIL_AUTHORIZATION`)
- ClickUp connector OAuth token (`CLICKUP_AUTHORIZATION`)
- MarkItDown MCP installed locally (see below)

---

**Setup**

1) Create and activate a venv

- macOS/Linux:
  - `python3 -m venv .venv && source .venv/bin/activate`
- Windows (PowerShell):
  - `py -3 -m venv .venv ; .\.venv\Scripts\Activate.ps1`

2) Install dependencies

- `pip install -r requirements.txt`

3) Set environment variables

Create a `.env` (or export directly in your shell):

- Required
  - `OPENAI_API_KEY=...`
  - Optionally set default model: `OPENAI_DEFAULT_MODEL=gpt-5-chat-latest`

- Optional (Hosted MCP connectors)
  - Gmail: `GMAIL_AUTHORIZATION=...` (OAuth access token)
  - ClickUp: `CLICKUP_AUTHORIZATION=pk_...` (Personal token; do NOT prefix with `Bearer` for the function tools in this repo)

- Optional (File search)
  - To reuse an existing vector store: `VECTOR_STORE_ID=vs_...`

- Optional (MarkItDown MCP via stdio)
  - If the server command differs: `MARKITDOWN_MCP_COMMAND=markitdown-mcp`
  - Or explicitly: `MARKITDOWN_MCP_PY_MODULE=markitdown_mcp` (uses `python -m ...`)

- Optional (Mistral OCR)
  - `MISTRAL_API_KEY=...`
  - `MISTRAL_OCR_URL=...` (confirm the correct endpoint with your account)

Note on connector IDs and scopes:

- This sample uses OpenAI Hosted MCP connectors via `HostedMCPTool`. You supply an OAuth `authorization` token for each connector and pick the correct `connector_id` per the docs. Example IDs below are commonly used, but verify the latest IDs/scopes in the Platform docs under Tools → Connectors.

---

**Run**

- With a custom prompt:
  - `python src/agents_demo/main.py "Find 2 latest AI articles. If Gmail is available, list my 3 most recent unread subjects. If ClickUp is available, draft a new task."`

- Or just run with defaults:
  - `python src/agents_demo/main.py`

The script prints which tools/connectors are enabled based on your environment.

---

**MarkItDown MCP (local)**

MarkItDown converts Office/PDF/HTML files to Markdown. To expose it as MCP locally:

- Install the MCP server (example; verify the official package/instructions):
  - `pip install markitdown markitdown-mcp`  # package name may vary

- Confirm the CLI exists:
  - `markitdown-mcp --help`  (or run via module: `python -m markitdown_mcp`)

The code uses `MCPServerStdio` and will attempt the command in this order:
1) `MARKITDOWN_MCP_COMMAND` env (default `markitdown-mcp`)
2) `python -m ${MARKITDOWN_MCP_PY_MODULE}` (default `markitdown_mcp`)

---

**ClickUp PDF → Markdown (Example flow)**

Goal: Pull an attachment PDF from ClickUp and convert to Markdown using MarkItDown, then save it.

1) Ensure prerequisites:
   - `CLICKUP_AUTHORIZATION` contains a valid OAuth token. Include any needed prefix, for example: `Bearer ey...`
   - MarkItDown MCP is available locally (see section above).

2) Option A: Provide a direct download URL for the ClickUp attachment (from the ClickUp UI or API).

   Option B (recommended): Use the built-in function tool to list attachments for a task and then proceed.

3) Run the agent with an instruction like:

   a) If you have a direct URL:

   `python src/agents_demo/main.py "Download this ClickUp file <PASTE_FILE_URL_HERE> using download_clickup_file. Then use the MarkItDown MCP tools to convert the local PDF path to Markdown. Finally, save it to converted/my_doc.md using save_markdown and summarize the key points."`

   b) If you have the task id (e.g., `868f60hen`):

   `python src/agents_demo/main.py "Call get_clickup_task_attachments with task_id='868f60hen' and show me the list. Pick the first PDF, pass its 'url' to download_clickup_file to save locally. Use the MarkItDown MCP tools to convert the downloaded PDF path to Markdown, then call save_markdown('...','my_converted.md'). Summarize the content."`

What happens:
- The `download_clickup_file` function tool downloads the PDF locally to `data/downloads/` using your `CLICKUP_AUTHORIZATION` header.
- The agent calls the local MarkItDown MCP server to convert the file (the LLM will list/choose the correct MCP tool method).
- The agent calls `save_markdown` to write the resulting Markdown to `data/converted/` and returns the path.

Tips:
- If the MarkItDown MCP expects a file path, pass the path returned by `download_clickup_file` as the input.
- If the connector returns only an attachment id, you can either fetch a direct URL yourself or instruct the agent to use the ClickUp connector's tools to obtain a download URL, then call `download_clickup_file`.
- For function tools using ClickUp here, set `CLICKUP_AUTHORIZATION` to the raw token (e.g., `pk_...`), not `Bearer pk_...`.

---

**Invoice Extraction + ClickUp**

Tools for structuring invoice data and sending to ClickUp:

- `extract_invoice_from_markdown(markdown_path)` → JSON (see `src/agents_demo/schemas.py`)
- `extract_invoice_from_text(text)` → same, useful for OCR text
- `clickup_update_task_custom_fields_from_invoice(task_id, invoice_json, field_map_json="", update_description=True, auto_create_missing=True)`
  - `field_map_json` is optional. If omitted or `{}`, the tool auto‑matches invoice keys to existing ClickUp custom fields by name. If no match is found and `auto_create_missing` is true, it creates a best‑guess field on the task's list (short_text/number/date) and then sets the value.
  - If `update_description` is true, appends a Markdown line‑item table to the task description
- `clickup_upsert_task_fields_from_kv(task_id, kv_json, update_description=False, auto_create_missing=True)`
  - Generic K/V upsert into a task's custom fields. Useful when you have arbitrary extracted fields from OCR/LLM beyond the invoice schema.
- `clickup_create_subtasks_from_invoice_line_items(task_id, invoice_json, auto_create_missing=True)`
  - Creates a subtask per invoice/quote line item and sets item fields (Quantity, Unit, Unit Price, Amount, Item Description). Reuses/creates list-level fields as needed.

Workflows:
- Convert PDF via MarkItDown MCP → `extract_invoice_from_markdown` → update ClickUp
- If the PDF is scanned or tables parse poorly: `mistral_ocr_extract_text` on the PDF → `extract_invoice_from_text` → update ClickUp
- If the parsed invoice/quote has `line_items`, also call `clickup_create_subtasks_from_invoice_line_items` to add each as a subtask with item details.

Extraction notes:
- The extractor is tuned for invoices and quotes and attempts to pull structured line items when it detects tabular item lists.

Notes:
- The agent instructions are optimized to attempt both MarkItDown MCP and OCR, score results, and pick the better input for extraction automatically.
- For ClickUp custom fields, you can now simply pass the task id and the extracted invoice JSON; the tool will map/create fields as needed.

---

**Gmail Invoices wrapper**

- Module: `src/gmail_invoices.py`
- Purpose: Thin, stable API to orchestrate Gmail → Planner workflows without re‑implementing Gmail logic.
- Public functions:
  - `list_invoice_attachments(query: str, lookback_days: int)` → list of attachment refs (no bytes)
  - `download_attachment(ref)` → bytes of the selected attachment
  - `upload_pdf_to_planner(pdf_bytes, source_message_id=None)` → InsertReport dict
- Behavior:
  - Reuses existing Gmail helpers in this repo (read‑only).
  - Uploads PDFs to the planning app at `PLANNER_API_BASE/orders/pending/upload-pdf`.
  - Env: `PLANNER_API_BASE` (required), `PLANNER_API_KEY` (optional), plus existing Gmail envs.


---

**Notes / Tips**

- GPT‑5 models: If you switch to a non‑chat GPT‑5 model (e.g., `gpt-5.1`), you must provide reasoning settings. See `default_models.py` in the SDK or pass `model_settings` with `reasoning={"effort": "low|medium|minimal"}`.
- File search: The sample creates a vector store and indexes a tiny example file if `VECTOR_STORE_ID` is not set.
- Approvals: Hosted MCP tools are set to `require_approval="never"` for easy testing. Adjust to your workflow/policies.