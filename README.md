# Family Email Monitor

An AI agent that watches a Gmail inbox, decides which emails actually need a
person's attention, and sends a concise Telegram notification when one does —
one isolated agent per family member.

Built on [NanoClaw](https://github.com/qwibitai/nanoclaw) (MIT, © 2026 Gavriel)
as the host/runtime, with a custom Python **LangChain classifier** (served over
HTTP) as the intelligence layer and a small deterministic orchestrator script
that does the actual inbox work.

> **Status:** working and autonomous for a single user. A recurring task fires
> every 5 hours, wakes the agent, runs the check, and notifies on Telegram —
> verified end-to-end. Multi-user family rollout (Wife, Kids) is the remaining
> work. See [`EMAIL_MONITOR_PLAN_V2.md`](EMAIL_MONITOR_PLAN_V2.md) for the
> current plan and the journey that got here.

---

## What it does

```
Recurring scheduled task (every 5h, Asia/Singapore)
     │  host sweep notices it's due → wakes a fresh agent container
     ▼
Agent runs one command:  bun check_inbox.ts   (deterministic orchestrator)
     │   1. fetch UNREAD Gmail from the last ~6h   (OneCLI-proxied REST)
     │   2. POST them to /classify  ──►  LangChain LCEL classifier
     │          Stage 1: drop junk / ads / newsletters
     │          Stage 2: payment? meeting? job? reply? urgent?
     │   3. label seen   (BooTuna/seen — dedup across overlapping windows)
     ▼
Telegram  ──►  "⚠️ Important email from <sender>: <summary>"
```

The key design choice: **the LLM does judgment, code does orchestration.** An
earlier version asked the agent to drive the whole loop (search inbox, call a
classify tool, dedup, notify) and it proved unreliable — it improvised, skipped
steps, or hung. Now a plain TypeScript script (`check_inbox.ts`) does every
deterministic step, the classifier does the per-email judgment, and the agent
is reduced to "run this one command and relay the result."

Each family member gets their own agent group — separate container, separate
session DB, separate credentials, separate Telegram bot. No one sees anyone
else's mail.

## My contribution

The base NanoClaw platform provides the host, container isolation, channel
adapters, and credential vault. **What I designed and built on top:**

| Area | Work |
|------|------|
| **LangChain classifier** | [`email-filter/`](email-filter/) — a Python [FastMCP](https://github.com/modelcontextprotocol) server exposing a `POST /classify` HTTP endpoint. Two-stage [LCEL](email-filter/classifier.py) pipeline: a cheap coarse filter drops obvious noise, then a deeper pass tags action type + urgency. Model-agnostic: Claude Haiku when an API key is set, local Ollama (`qwen3:8b`, run with `reasoning=False` for speed) as a free fallback. |
| **Deterministic orchestrator** | [`check_inbox.ts`](groups/dm-with-alex-emailmonitor/) — the script the agent runs. Windowed Gmail fetch over the OneCLI credential proxy, chunked calls to `/classify`, and a `seen` label for dedup. Moving orchestration out of the LLM and into code is what made the monitor reliable. |
| **Scheduling & durability** | A recurring `kind=task` row drives the 5-hour cadence via NanoClaw's host sweep; [`scripts/ensure-schedule.ts`](scripts/ensure-schedule.ts) re-seeds it on every startup so the schedule survives session rebuilds. |
| **Architecture & multi-user design** | Per-family-member agent isolation mapped onto NanoClaw's entity model; classification criteria and notification format. |
| **Project wiki** | [`wiki/`](wiki/) — a [Karpathy-style](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) compounding knowledge base: architecture, the trigger flow, design decisions, integration headaches, and a full Windows-setup troubleshooting log. |
| **Tooling & ops** | PowerShell start/stop/build scripts, a Windows-correct container build, and fixes to run the macOS/Linux-first stack cleanly on Windows 11 + WSL2. |

## Tech stack

- **Runtime:** NanoClaw v2 (Node host + Bun agent containers, Docker isolation)
- **Intelligence:** Python · LangChain (LCEL), served over HTTP via FastMCP's `custom_route`
- **Orchestration:** TypeScript (Bun) — `check_inbox.ts`, run by the agent's Bash tool
- **Models:** Claude Haiku (via Anthropic) or Ollama `qwen3:8b` (local, free)
- **Messaging:** Telegram (Chat SDK adapter)
- **Credentials:** OneCLI Agent Vault (tokens never enter the container)
- **Data:** SQLite (two-DB-per-session message bus)

## Documentation

The [`wiki/`](wiki/) folder is the best place to understand the system — open it
as an Obsidian vault for the linked graph, or start with:

- [`wiki/overview.md`](wiki/overview.md) — goals, users, status
- [`wiki/architecture.md`](wiki/architecture.md) — end-to-end system design (static view)
- [`wiki/email-monitor-trigger-flow.md`](wiki/email-monitor-trigger-flow.md) — how a scheduled wake fires the agent and runs the check (dynamic view)
- [`wiki/langchain-filter.md`](wiki/langchain-filter.md) — the LCEL classification design
- [`wiki/gmail-integration-issues.md`](wiki/gmail-integration-issues.md) — the runtime headaches and the architecture pivot
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
python server.py            # serves POST /classify on :8765 (Ollama default, no API key needed)
```

The full stack (Windows):

```powershell
.\scripts\start-all.ps1     # OneCLI vault + classifier + NanoClaw host + schedule re-seed
```

For first-time NanoClaw setup (auth, container build, channel pairing), see the
original project's instructions in [`README.nanoclaw.md`](README.nanoclaw.md).

## Credits & license

This project is a personal fork of **[NanoClaw](https://github.com/qwibitai/nanoclaw)**
by Gavriel, used under the MIT License. The original project README is preserved
at [`README.nanoclaw.md`](README.nanoclaw.md), and the upstream copyright notice
is kept in [`LICENSE`](LICENSE) as the license requires.

My additions (the `email-filter/` classifier, the orchestrator + scripts, the
`wiki/`, and the email-monitor design) are likewise released under the MIT License.
