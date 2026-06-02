# System Architecture

> End-to-end design of the family email monitor: data flow, components, and boundaries.

**Last updated:** 2026-06-02
**Related:** [[nanoclaw]], [[langchain-filter]], [[overview]]

## Data Flow

```
NanoClaw Host Sweep (every 30 min)
        │ wakes each agent group
        ▼
Docker Container (one per family member)
        │
        ├── 1. Gmail MCP tool ──────────────────► Gmail API
        │        fetch new emails since last poll
        │
        ├── 2. classify_emails MCP tool ─────────► LangChain MCP Server
        │        (host.docker.internal:8765)         (Python, port 8765)
        │                                             Stage 1: junk/ad filter
        │                                             Stage 2: deep classify
        │                                             ──► Claude Haiku API
        │
        └── 3. Claude Sonnet (agent)
                 format notification
                 ──► NanoClaw channel adapter
                      ──► Telegram (Alex / Wife / Kids)
```

## Components

### Python LangChain Filter (outside NanoClaw)
- Runs as a scheduled Python script on the host machine
- Polls Gmail via Google API every 30 minutes
- Tracks last-poll timestamp to only fetch new emails
- Stage 1: classifies as junk / ad / newsletter / important
- Stage 2: deep-classifies important emails (payment / meeting / job / reply / urgent)
- Writes important emails to each user's NanoClaw `inbound.db`
- See [[langchain-filter]] for implementation details

### NanoClaw Host (Node.js)
- Always-running service on the home desktop
- Manages agent groups, session DBs, channel adapters
- Wakes Docker containers when new messages arrive in `inbound.db`
- Polls `outbound.db` and delivers via Telegram adapter
- See [[nanoclaw]] for architecture details

### Docker Agent Containers (one per family member)
- Isolated runtime (Bun) per agent group
- Reads from `inbound.db`, writes to `outbound.db`
- Runs Claude Haiku for final classification and notification formatting
- Has access to MCP tools (Gmail for full body fetch if needed)
- No access to other family members' session DBs

### OneCLI Vault
- Stores Gmail OAuth tokens securely
- Injects credentials at request time — never in env vars or chat
- Each family member has a separate credential entry
- Tokens auto-refresh; no re-auth needed after initial setup

### Session DBs (two per session)
- `inbound.db` — LangChain filter writes, Docker container reads
- `outbound.db` — Docker container writes, NanoClaw host reads
- Single writer per file — no lock contention
- Located at `data/v2-sessions/<session-id>/`

## Boundaries

| Boundary | What crosses it |
|----------|----------------|
| Gmail API → LangChain | Email metadata + body text (OAuth token via OneCLI) |
| LangChain → inbound.db | Structured JSON: sender, subject, body, classification |
| inbound.db → Docker container | Mounted SQLite file (read-only from container perspective) |
| Docker container → outbound.db | Formatted notification message |
| outbound.db → Telegram | Text message via Telegram Bot API |

## Isolation Model

Each family member maps to one NanoClaw **agent group**:
- Separate `CLAUDE.md` (custom classification criteria per person)
- Separate Docker container (separate runtime, separate process)
- Separate session DBs (no shared state)
- Separate OneCLI credential (separate Gmail OAuth token)
- Separate Telegram bot (separate notification channel)

No family member can see another's emails or notifications.

## Diagram

See `email-monitor-system.excalidraw` in the repo root for the visual diagram.
Open with the Excalidraw VS Code extension or excalidraw.com.
