# Family Email Monitor

An AI agent that watches multiple Gmail inboxes, decides which emails actually
need a person's attention, and sends a concise Telegram notification when one
does — one isolated agent per family member.

Built on [NanoClaw](https://github.com/qwibitai/nanoclaw) (MIT, © 2026 Gavriel)
as the host/runtime, with a custom Python **LangChain MCP classifier** as the
intelligence layer.

> **Status:** working end-to-end for a single user (agent responds on Telegram).
> Multi-user family rollout and the recurring poll schedule are in progress.
> See [`EMAIL_MONITOR_PLAN.md`](EMAIL_MONITOR_PLAN.md) for the phased build plan.

---

## What it does

```
Gmail inbox(es)
     │  (polled on a schedule)
     ▼
NanoClaw agent  ──►  classify_emails (custom LangChain MCP server)
     │                   Stage 1: drop junk / ads / newsletters
     │                   Stage 2: payment? meeting? job? reply? urgent?
     ▼
Telegram  ──►  "⚠️ Important email from <sender>: <summary>. Draft a reply?"
```

Each family member gets their own agent group — separate container, separate
session DB, separate credentials, separate Telegram bot. No one sees anyone
else's mail.

## My contribution

The base NanoClaw platform provides the host, container isolation, channel
adapters, and credential vault. **What I designed and built on top:**

| Area | Work |
|------|------|
| **LangChain MCP classifier** | [`email-filter/`](email-filter/) — a Python [FastMCP](https://github.com/modelcontextprotocol) server exposing a `classify_emails` tool. Two-stage [LCEL](email-filter/classifier.py) pipeline: a cheap coarse filter drops obvious noise, then a deeper pass tags action type + urgency. Model-agnostic: Claude Haiku when an API key is set, local Ollama (`qwen3:8b`) as a free fallback. |
| **Architecture & multi-user design** | Per-family-member agent isolation mapped onto NanoClaw's entity model; classification criteria and notification format; scheduling via the host sweep. |
| **Project wiki** | [`wiki/`](wiki/) — a [Karpathy-style](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) compounding knowledge base: architecture, MCP internals, OneCLI, design decisions, and a full Windows-setup troubleshooting log. |
| **Tooling & ops** | PowerShell start/stop/build scripts, a Windows-correct container build, and fixes to run the macOS/Linux-first stack cleanly on Windows 11 + WSL2. |

## Tech stack

- **Runtime:** NanoClaw v2 (Node host + Bun agent containers, Docker isolation)
- **Intelligence:** Python · LangChain (LCEL) · MCP (FastMCP, SSE transport)
- **Models:** Claude Haiku / Sonnet (via Anthropic) or Ollama (local)
- **Messaging:** Telegram (Chat SDK adapter)
- **Credentials:** OneCLI Agent Vault (tokens never enter the container)
- **Data:** SQLite (two-DB-per-session message bus)

## Documentation

The [`wiki/`](wiki/) folder is the best place to understand the system — open it
as an Obsidian vault for the linked graph, or start with:

- [`wiki/overview.md`](wiki/overview.md) — goals, users, status
- [`wiki/architecture.md`](wiki/architecture.md) — end-to-end data flow
- [`wiki/mcp.md`](wiki/mcp.md) — how the classifier is exposed as an MCP tool
- [`wiki/langchain-filter.md`](wiki/langchain-filter.md) — the LCEL classification design
- [`wiki/decisions.md`](wiki/decisions.md) — technology choices and trade-offs
- [`wiki/windows-setup-issues.md`](wiki/windows-setup-issues.md) — every setup problem and fix

A visual system diagram lives in
[`email-monitor-system.excalidraw`](email-monitor-system.excalidraw) (open with
the Excalidraw VS Code extension or excalidraw.com).

## Running it

The classifier (standalone, testable without NanoClaw):

```bash
cd email-filter
pip install -r requirements.txt
python server.py            # MCP server on :8765 (Ollama default, no API key needed)
```

The full stack (Windows):

```powershell
.\scripts\start-all.ps1     # OneCLI vault + NanoClaw host
```

For first-time NanoClaw setup (auth, container build, channel pairing), see the
original project's instructions in [`README.nanoclaw.md`](README.nanoclaw.md).

## Credits & license

This project is a personal fork of **[NanoClaw](https://github.com/qwibitai/nanoclaw)**
by Gavriel, used under the MIT License. The original project README is preserved
at [`README.nanoclaw.md`](README.nanoclaw.md), and the upstream copyright notice
is kept in [`LICENSE`](LICENSE) as the license requires.

My additions (the `email-filter/` MCP classifier, the `wiki/`, the scripts, and
the email-monitor design) are likewise released under the MIT License.
