# Model Context Protocol (MCP)

> The protocol NanoClaw uses to give agents access to external tools — and how
> we implemented a custom Python MCP server for email classification.

**Last updated:** 2026-06-02
**Related:** [[langchain-filter]], [[architecture]], [[nanoclaw]]

## What MCP Is

MCP (Model Context Protocol) is an open standard by Anthropic for connecting
AI agents to external tools and data sources. It defines how an agent discovers
tools, calls them, and receives results — without knowing anything about how
the tool is implemented internally.

Think of it like a USB standard: any device that speaks USB works with any
port. Any tool that speaks MCP works with any MCP-compatible agent.

```
Agent (Claude)
    │  "I need to classify these emails"
    │  calls: classify_emails([...])
    ▼
MCP Protocol
    │  standardised request/response format
    ▼
Our Python Server (email-filter/server.py)
    │  routes to the right function
    ▼
LangChain LCEL chains → Ollama / Haiku
```

## Transport: SSE

Our server uses **SSE (Server-Sent Events)** transport — HTTP-based, which means:
- Server runs on a normal port (8765)
- Docker containers reach it via `http://host.docker.internal:8765/sse`
- No special networking needed beyond standard HTTP

Other transport options: `stdio` (subprocess pipe, used by Claude Desktop),
`streamable-http` (newer variant). SSE is the right choice for a network service.

## FastMCP

FastMCP is a Python library that wraps the MCP SDK to eliminate boilerplate.
Without FastMCP you'd manually handle: protocol handshakes, tool schema
generation, message framing, error serialisation. FastMCP does all of that.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="email-classifier",          # server identity
    instructions="..."                # shown to the agent on connect
)
```

## Registering a Tool

The `@mcp.tool()` decorator turns a Python function into an MCP tool:

```python
@mcp.tool()
def classify_emails(emails: list[dict]) -> list[dict]:
    """
    Classify a list of emails for importance and required action.
    Each email dict must have: sender, subject, body_preview.
    Returns only important emails with action_type, summary, urgency.
    """
    return run_pipeline(emails, stage1_chain, stage2_chain)
```

Three things happen automatically:
- **Schema generation** — type hints (`list[dict]`) become a JSON Schema the
  agent uses to know what arguments to pass
- **Tool registration** — the function appears in the server's tool list
- **Description** — the docstring becomes the tool description the agent reads
  to decide when and how to call it

## The Full Call Chain

```
NanoClaw host sweep fires
    │
    ▼
Docker container wakes (agent group: Alex)
    │
    ▼
Claude (agent) runs
    │  reads CLAUDE.md instructions
    │  decides: "I need to check Gmail and classify emails"
    │
    ├──► Gmail MCP tool (built-in NanoClaw)
    │        fetches emails since last poll
    │        returns list of email dicts
    │
    ├──► classify_emails MCP tool (our server)
    │        POST http://host.docker.internal:8765/sse
    │        payload: [{sender, subject, body_preview}, ...]
    │        → FastMCP routes to classify_emails()
    │        → run_pipeline() runs Stage 1 + Stage 2 via LangChain
    │        → Ollama/Haiku classifies each email
    │        response: [{...email, action_type, summary, urgency}, ...]
    │
    ▼
Claude formats notification message
    │  "Important email from billing@acme.com..."
    ▼
NanoClaw channel adapter → Telegram
```

## Starting the Server

```bash
cd email-filter
python server.py
```

Output on start:
```
ANTHROPIC_API_KEY not set — falling back to Ollama model: qwen3:8b
Starting email classifier MCP server on 0.0.0.0:8765
Docker containers can reach this at: http://host.docker.internal:8765/sse
```

The server must be running **before** any agent tries to call `classify_emails`.
It stays running permanently alongside NanoClaw.

Note: host/port are set on the `FastMCP(...)` constructor (`host=`, `port=`),
not on `mcp.run()` — the installed `mcp` SDK's `run(transport="sse")` takes no
host/port kwargs.

## Model Selection

The server picks its model based on what's available:

| Condition | Model used | Cost |
|-----------|-----------|------|
| `ANTHROPIC_API_KEY` set in `.env` | Claude Haiku | ~$0.80/M tokens |
| No API key | Ollama `qwen3:8b` (local) | Free |

Override the Ollama model via `.env`:
```
EMAIL_FILTER_MODEL=llama3.2:3b
```

## Wiring to NanoClaw Agent Group

MCP servers are registered per agent group in `groups/<folder>/container.json`
under `mcpServers`. The agent-runner reads this and passes it to the Claude
Agent SDK at query time.

```jsonc
// groups/dm-with-alex-emailmonitor/container.json
{
  "mcpServers": {
    "email-classifier": {
      "type": "sse",
      "url": "http://host.docker.internal:8765/sse"
    }
  }
}
```

`host.docker.internal` lets the container reach the Python server running on the
host. The agent sees `classify_emails` in its tool list automatically (from the
tool's docstring + schema).

### Gotcha: agent-runner needed an SSE/HTTP patch

Trunk's agent-runner narrowed its `McpServerConfig` to **stdio only**
(`{command, args, env}`) — it spawns MCP servers as subprocesses *inside* the
container. Our classifier runs on the *host* (where Ollama + LangChain live),
reachable only over the network. The underlying Claude Agent SDK already
supports `type: 'sse'` / `type: 'http'`, so we widened the agent-runner to pass
remote configs through:

- `container/agent-runner/src/providers/types.ts` — `McpServerConfig` is now a
  union of `McpStdioServerConfig | McpRemoteServerConfig`
- `container/agent-runner/src/config.ts` — uses the shared type
- `container/agent-runner/src/index.ts` — passes remote configs through to the SDK

This is a fork-level change (NanoClaw's philosophy: customize via code).

## Why a Separate MCP Server vs Built-in Tool

NanoClaw ships built-in MCP tools (Gmail, scheduling, self-mod). We could have
added classification logic directly to the agent's `CLAUDE.md` prompt, but a
dedicated MCP server is better because:

- **Separation of concerns** — LangChain/Ollama logic is isolated from NanoClaw
- **Testable independently** — run the server and call it with curl/Python without NanoClaw
- **Swappable** — change the classification model without touching NanoClaw at all
- **Learning** — building a custom MCP server is the core skill here

## Testing the Server Manually

Once running, test it without NanoClaw using Python:

```python
# test_server.py
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test():
    async with sse_client("http://localhost:8765/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("classify_emails", {
                "emails": [
                    {
                        "sender": "billing@acme.com",
                        "subject": "Invoice #1042 overdue — action required",
                        "body_preview": "Dear Alex, your invoice of $450 is now 14 days overdue."
                    },
                    {
                        "sender": "news@medium.com",
                        "subject": "Your weekly digest",
                        "body_preview": "Top stories this week..."
                    }
                ]
            })
            print(result)

asyncio.run(test())
```

Expected output: only the invoice email returned, newsletter discarded.
