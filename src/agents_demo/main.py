import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.shared.reasoning import Reasoning

from agents import (
    Agent,
    FileSearchTool,
    HostedMCPTool,
    ModelSettings,
    Runner,
    WebSearchTool,
    function_tool,
)
from agents.mcp.server import MCPServerStdio, MCPServerStdioParams
# Ensure 'src' is on sys.path when running as a script
from pathlib import Path as _PathForSys
_repo_root = _PathForSys(__file__).resolve().parents[2]
_src_path = _repo_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))
from agents_demo.schemas import Invoice, InvoiceLineItem
import requests
from pathlib import Path
import json
import base64
from typing import List, Optional as TOptional


# Load .env if present
load_dotenv()


@function_tool
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@dataclass
class Connectors:
    gmail: Optional[HostedMCPTool]
    clickup: Optional[HostedMCPTool]


def build_connectors() -> Connectors:
    """Build Hosted MCP tools for Gmail and ClickUp if configured.

    connector_id values commonly used (verify in docs):
    - Gmail: "connector_gmail"
    - ClickUp: "connector_clickup"
    """
    # Allow skipping hosted connectors for local testing while keeping env tokens for function tools
    if os.getenv("DISABLE_HOSTED_CONNECTORS", "").lower() in {"1", "true", "yes"}:
        return Connectors(gmail=None, clickup=None)

    gmail_tool = None
    gmail_auth = os.getenv("GMAIL_AUTHORIZATION")
    if gmail_auth:
        gmail_tool = HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "gmail",
                "connector_id": "connector_gmail",
                "authorization": gmail_auth,
                # Change to "always" or "manual" based on your policy
                "require_approval": "never",
            }
        )

    clickup_tool = None
    clickup_auth = os.getenv("CLICKUP_AUTHORIZATION")
    if clickup_auth:
        clickup_tool = HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "clickup",
                "connector_id": "connector_clickup",
                "authorization": clickup_auth,
                "require_approval": "never",
            }
        )

    return Connectors(gmail=gmail_tool, clickup=clickup_tool)


async def maybe_prepare_vector_store() -> Optional[str]:
    """Return a vector store id. If VECTOR_STORE_ID is set, reuse it.
    Otherwise, create a small example store with one file.
    """
    existing = os.getenv("VECTOR_STORE_ID")
    if existing:
        return existing

    text = (
        "MarkItDown by Microsoft converts Office/PDF files to Markdown for easy LLM consumption.\n"
        "This sample also demonstrates OpenAI hosted tools and connectors."
    )
    client = OpenAI()

    # Create a file
    uploaded = client.files.create(
        file=("example.txt", text.encode("utf-8")),
        purpose="assistants",
    )

    vs = client.vector_stores.create(name="agents-demo-vector-store")
    client.vector_stores.files.create_and_poll(
        vector_store_id=vs.id,
        file_id=uploaded.id,
    )

    return vs.id


def maybe_markitdown_mcp() -> Optional[MCPServerStdio]:
    """Return an MCP stdio server for MarkItDown if the binary/module is available.

    Tries a CLI first (MARKITDOWN_MCP_COMMAND or 'markitdown-mcp'),
    then falls back to python -m markitdown_mcp.
    """
    cmd = os.getenv("MARKITDOWN_MCP_COMMAND", "markitdown-mcp")
    if shutil.which(cmd):
        return MCPServerStdio(
            MCPServerStdioParams(command=cmd),
            cache_tools_list=True,
            name="markitdown-stdio",
        )

    module = os.getenv("MARKITDOWN_MCP_PY_MODULE", "markitdown_mcp")
    if shutil.which(sys.executable or "python"):
        try:
            import importlib.util as _util
            if _util.find_spec(module) is not None:
                return MCPServerStdio(
                    MCPServerStdioParams(command=sys.executable, args=["-m", module]),
                    cache_tools_list=True,
                    name=f"{module}-stdio",
                )
        except Exception:
            pass

    return None


def gpt5_settings_for(model_name: str) -> ModelSettings:
    """Return model settings; include reasoning for non-chat GPT‑5 models."""
    if model_name.startswith("gpt-5") and not model_name.startswith("gpt-5-chat"):
        return ModelSettings(reasoning=Reasoning(effort="low"))
    return ModelSettings()


async def main():
    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (
            "Using the available tools, give a short update: "
            "1) Do a quick web search for two recent AI news items. "
            "2) If Gmail is enabled, list my 3 most recent unread email subjects. "
            "3) If ClickUp is enabled, draft a task description to follow up. "
            "4) If file search is enabled, cite 1 snippet from the indexed file."
        )
    )

    # Core tools
    tools = [
        WebSearchTool(),
        add,  # function tool example
    ]

    # File search tool (optional, can be disabled)
    vector_store_id = None
    if os.getenv("DISABLE_FILE_SEARCH", "").lower() not in {"1", "true", "yes"}:
        vector_store_id = await maybe_prepare_vector_store()
        if vector_store_id:
            tools.append(
                FileSearchTool(
                    vector_store_ids=[vector_store_id],
                    include_search_results=True,
                    max_num_results=3,
                )
            )

    # Hosted MCP connectors (optional)
    conns = build_connectors()
    if conns.gmail:
        tools.append(conns.gmail)
    if conns.clickup:
        tools.append(conns.clickup)

    # Local MCP: MarkItDown (optional)
    markit_mcp = maybe_markitdown_mcp()

    # Model selection (default GPT‑5 chat)
    model_name = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5-chat-latest").lower()
    model_settings = gpt5_settings_for(model_name)

    agent = Agent(
        name="Multi-Tool Assistant",
        instructions=(
            "You are a concise assistant. Use tools when helpful. "
            "For Gmail: use gmail_search_attachments to find attachments, gmail_download_attachment to save locally. "
            "For ClickUp: use the available ClickUp tools to manage tasks and custom fields."
        ),
        model=model_name,
        model_settings=model_settings,
        tools=tools,
        mcp_servers=[markit_mcp] if markit_mcp else [],
    )

    print("\nEnabled features:")
    print(f"- Web search: yes")
    print(f"- File search: {'yes' if vector_store_id else 'no'}")
    print(f"- Function tool 'add': yes")
    print(f"- Gmail connector: {'yes' if conns.gmail else 'no'}")
    print(f"- ClickUp connector: {'yes' if conns.clickup else 'no'}")
    print(f"- MarkItDown MCP (local): {'yes' if markit_mcp else 'no'}\n")

    # If we created a local MCP server, connect/cleanup it around the run
    if markit_mcp:
        await markit_mcp.connect()
        try:
            result = await Runner.run(agent, input=prompt, max_turns=20)
        finally:
            await markit_mcp.cleanup()
    else:
        result = await Runner.run(agent, input=prompt, max_turns=20)

    print("\nFinal Output:\n")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())