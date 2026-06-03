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
from starlette.requests import Request
from starlette.responses import JSONResponse
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


# Safety backstop: cap how many emails one call will classify. The local
# Ollama model is slow (~5-10s/email), so an unbounded batch (e.g. a whole
# unread backlog) can grind for many minutes and stall the agent. The agent
# is instructed to cap at 15; this is defense-in-depth against over-fetching.
MAX_EMAILS_PER_CALL = int(os.environ.get("EMAIL_FILTER_MAX_BATCH", "15"))


@mcp.tool()
def classify_emails(emails: list[dict]) -> dict:
    """
    Classify a list of emails for importance and required action.

    Each email dict must have: sender (str), subject (str), body_preview (str).
    At most 15 emails are classified per call (the first 15 if more are sent);
    pass fewer and call again for the rest.

    Returns a dict:
    - important: list of important emails, each with action_type, summary, urgency
    - classified: how many emails were actually classified
    - skipped: how many were dropped by the per-call cap (classify next call)
    """
    capped = emails[:MAX_EMAILS_PER_CALL]
    important = run_pipeline(capped, stage1_chain, stage2_chain)
    return {
        "important": important,
        "classified": len(capped),
        "skipped": max(0, len(emails) - len(capped)),
    }


@mcp.custom_route("/classify", methods=["POST"])
async def classify_http(request: Request) -> JSONResponse:
    """
    Plain-HTTP twin of the classify_emails MCP tool.

    Lets a deterministic orchestrator (the container-side drain_inbox script)
    POST a batch of emails and get the importance verdict back as JSON, without
    speaking MCP. Body: {"emails": [{sender, subject, body_preview}, ...]}.
    Same per-call cap and return shape as classify_emails.
    """
    body = await request.json()
    emails = body.get("emails", [])
    capped = emails[:MAX_EMAILS_PER_CALL]
    important = run_pipeline(capped, stage1_chain, stage2_chain)
    return JSONResponse(
        {
            "important": important,
            "classified": len(capped),
            "skipped": max(0, len(emails) - len(capped)),
        }
    )


if __name__ == "__main__":
    print(f"Starting email classifier MCP server on {HOST}:{PORT}")
    print("Docker containers can reach this at: http://host.docker.internal:8765/sse")
    mcp.run(transport="sse")
