"""
LangChain Email Classifier — MCP Server

Exposes a single MCP tool: classify_emails
Runs as an SSE server on port 8765 so NanoClaw Docker containers can reach it
via host.docker.internal:8765 (Windows/Mac Docker Desktop).

Start:
    python server.py

The agent group config should point to:
    http://host.docker.internal:8765/sse
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from classifier import build_chains, run_pipeline

# Load optional overrides from the parent project's .env
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Ollama model to use (default: qwen3:8b). Override via .env or environment.
OLLAMA_MODEL = os.environ.get("EMAIL_FILTER_MODEL", "qwen3:8b")

# Optional: set ANTHROPIC_API_KEY to use Claude Haiku instead of Ollama.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or None

HOST = os.environ.get("EMAIL_FILTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("EMAIL_FILTER_PORT", "8765"))

if ANTHROPIC_API_KEY:
    print(f"Using Claude Haiku (Anthropic API)")
else:
    print(f"ANTHROPIC_API_KEY not set — falling back to Ollama model: {OLLAMA_MODEL}")

stage1_chain, stage2_chain = build_chains(
    ollama_model=OLLAMA_MODEL,
    anthropic_api_key=ANTHROPIC_API_KEY,
)

mcp = FastMCP(
    name="email-classifier",
    instructions=(
        "Classifies emails for importance and action type. "
        "Call classify_emails with a list of email dicts. "
        "Returns only emails that require personal attention, with action type and summary."
    ),
    host=HOST,
    port=PORT,
)


@mcp.tool()
def classify_emails(emails: list[dict]) -> list[dict]:
    """
    Classify a list of emails for importance and required action.

    Each email dict must have: sender (str), subject (str), body_preview (str).

    Returns only important emails, each with added fields:
    - action_type: payment | meeting | job | reply | urgent
    - summary: 2-3 sentence description of what action is needed
    - urgency: high | medium | low
    """
    return run_pipeline(emails, stage1_chain, stage2_chain)


if __name__ == "__main__":
    print(f"Starting email classifier MCP server on {HOST}:{PORT}")
    print("Docker containers can reach this at: http://host.docker.internal:8765/sse")
    mcp.run(transport="sse")
