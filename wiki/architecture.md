# System Architecture

> End-to-end design of the email monitor as actually built: data flow,
> components, and boundaries.

**Last updated:** 2026-06-03
**Related:** [[nanoclaw]], [[langchain-filter]], [[mcp]], [[overview]], [[gmail-integration-issues]]

## Design principle

**The LLM does judgment; code does orchestration.** Classifying an email
(judgment) lives in the Python/LangChain service. Finding mail, windowing,
de-duping, and labelling (orchestration) lives in a deterministic script
(`check_inbox.ts`). The agent's only job is to *run* that script and relay the
result — it does not orchestrate anything itself. This split is the outcome of a
long debugging session; see [[gmail-integration-issues]] for why.

## Data Flow

```
NanoClaw host — scheduled task fires every 5h (or a Telegram message arrives)
        │ wakes the agent-group container
        ▼
Agent (Claude, in container)
        │ runs ONE command:  bun /workspace/agent/check_inbox.ts
        ▼
check_inbox.ts  (Bun, deterministic orchestrator — in the container)
        ├── Gmail REST API ───────────────► via OneCLI proxy (token injected)
        │     search: is:unread after:<now-6h> -label:BooTuna/seen
        │     fetch Subject/From/snippet for each
        │
        ├── POST /classify ──────────────► Python classifier (host :8765)
        │     {emails:[...]}  (chunked ≤15)    server.py → classifier.py (LCEL)
        │                                       Stage 1: junk/ad/newsletter/important
        │                                       Stage 2: deep classify (important only)
        │                                       ──► Ollama qwen3:8b (reasoning=False)
        │
        ├── apply label BooTuna/seen ─────► Gmail REST (dedup marker)
        │
        └── print JSON { checked, important:[...], window_hours }
        ▼
Agent relays the `important` list  ──► outbound.db
        ▼
NanoClaw host delivery poll  ──► Telegram (BooTunaBot)
```

The agent never searches, classifies, or labels mail itself — it has no Gmail or
classifier MCP tools (`container.json` → `mcpServers: {}`). Its sole email
capability is running the script via Bash.

## Components

### Python LangChain Classifier (host, port 8765) — *judgment only*
- `classifier.py`: two-stage LCEL pipeline (coarse junk/ad/newsletter/important →
  deep classify). Model: Ollama `qwen3:8b` with `reasoning=False` by default
  (Claude Haiku if `ANTHROPIC_API_KEY` is set).
- `server.py`: exposes **`POST /classify`** (the live path) and a now-vestigial
  `classify_emails` MCP/SSE tool. Holds the per-call cap.
- Does **not** touch Gmail, labels, scheduling, or Telegram. See [[langchain-filter]].

### `check_inbox.ts` (Bun, in the container) — *orchestration*
- The deterministic email worker. Calls Gmail REST through the OneCLI proxy
  (`Authorization: Bearer onecli-managed`, CA from `NODE_EXTRA_CA_CERTS`), so no
  real credential ever enters the container.
- Windowed model: only unread mail from the last `CHECK_WINDOW_HOURS` (default 6),
  not already labelled `BooTuna/seen`. No backlog draining — old mail is ignored.
- Calls `/classify`, applies the dedup label, prints one JSON object.
- Lives in the group folder, live-mounted at `/workspace/agent/check_inbox.ts`.

### NanoClaw Host (Node.js)
- Always-running service. Routes messages, runs the scheduler (fires the email
  check every 5h), polls `outbound.db`, delivers via the Telegram adapter.
- See [[nanoclaw]].

### Agent Container (Bun, one per agent group)
- Runs the LLM agent (`agent-runner`). For email, its only job is to run
  `check_inbox.ts` and relay the result. Reads `inbound.db`, writes `outbound.db`.

### OneCLI Vault
- Injects the Gmail OAuth token at request time, matched by host pattern
  (`gmail.googleapis.com`) and the per-agent auth token in the proxy URL.
  `check_inbox.ts`'s REST calls get the token injected transparently. See [[onecli]].

### Session DBs (two per session)
- `inbound.db` — host writes, container reads.
- `outbound.db` — container writes, host reads (also holds `processing_ack`).
- Single writer per file. Located at `data/v2-sessions/<agent-group>/<session>/`.

## Boundaries

| Boundary | What crosses it |
|----------|----------------|
| Scheduler → agent | A `kind=task` wake ("run the check") |
| Agent → `check_inbox.ts` | A Bash command |
| `check_inbox.ts` → Gmail API | REST calls, OAuth token injected by OneCLI proxy |
| `check_inbox.ts` → classifier | `POST /classify {emails:[...]}` → `{important:[...]}` (plain HTTP) |
| Agent → `outbound.db` | The important-emails notification text |
| `outbound.db` → Telegram | Text message via the host's Telegram adapter |

## Isolation Model (multi-user, by design)

Each family member maps to one NanoClaw **agent group** — separate `CLAUDE.local.md`,
container, session DBs, and OneCLI Gmail credential. No member can see another's
mail or notifications. Currently only **Alex** (`dm-with-alex-emailmonitor`, persona
BooTuna) is wired; additional members follow the same pattern. See
[[overview]] for status.

## Diagram

`email-monitor-system.excalidraw` in the repo root predates the `check_inbox.ts`
redesign — treat this page as the source of truth until the diagram is refreshed.
