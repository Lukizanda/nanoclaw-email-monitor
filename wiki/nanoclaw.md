# NanoClaw

> Self-hosted personal AI assistant platform — a host process that orchestrates
> per-session agent containers across multiple users and chat platforms.

**Last updated:** 2026-06-02
**Related:** [[architecture]], [[decisions]]

## What It Is

NanoClaw is not a single chatbot — it is infrastructure for running AI agents.
One NanoClaw instance can host multiple agent groups, each wired to different
chat platforms, with full isolation between them.

For this project: one NanoClaw instance hosts three agent groups (Alex, Wife,
Kids), each delivering to a separate Telegram bot.

## Core Architecture

```
Channel (Telegram/Discord/etc.)
        │
        ▼
NanoClaw Host (Node.js)
  - channel adapters
  - entity model (users → groups → sessions)
  - router → inbound.db
  - delivery ← outbound.db
        │
        ▼  (per session)
Docker Container
  - agent-runner (Bun)
  - Claude API
  - MCP tools
```

## Entity Model

```
users
  └── user_roles (owner / admin / member)
  └── agent_group_members

agent_groups  (one per "persona" — Alex, Wife, Kids)
  └── CLAUDE.md (personality + instructions)
  └── sessions

messaging_groups  (one Telegram DM = one messaging group)
  └── wired to an agent_group

sessions  (agent_group + messaging_group + thread → one Docker container)
```

## Two-DB Session Split

The key architectural choice: host and container never talk directly.

- `inbound.db` — host writes, container reads (`messages_in` table)
- `outbound.db` — container writes, host reads (`messages_out` table)

Exactly one writer per file. No IPC, no sockets, no shared memory.
The SQLite files are the entire IO surface between host and container.

Heartbeat is a file touch at `/workspace/.heartbeat` (not a DB write).

## Key Files

| File | Purpose |
|------|---------|
| `src/index.ts` | Entry point — init DB, adapters, delivery polls, sweep |
| `src/router.ts` | Routes inbound messages to the right session + inbound.db |
| `src/delivery.ts` | Polls outbound.db, delivers via channel adapter |
| `src/session-manager.ts` | Resolves/creates sessions, manages DB paths |
| `src/container-runner.ts` | Spawns Docker containers with session DB mounts |
| `src/host-sweep.ts` | 60s sweep — stale detection, due-message wake, recurrence |
| `container/agent-runner/src/` | Agent poll loop, Claude calls, MCP tools |
| `groups/<name>/CLAUDE.md` | Per-agent-group personality and instructions |

## OneCLI Secret Mode Gotcha

When NanoClaw first creates an agent, OneCLI defaults to `selective` secret
mode — no secrets assigned even if they exist in the vault.

Symptom: container starts but gets 401 from APIs whose credentials are in the vault.

Fix:
```bash
onecli agents list
onecli agents set-secret-mode --id <agent-id> --mode all
```

No container restart needed — gateway looks up secrets per request.

## Multi-User Model

Each family member = one agent group with:
- Their own `groups/<name>/CLAUDE.md`
- Their own Docker container at session time
- Their own inbound/outbound session DBs
- Their own OneCLI credential entry
- Their own Telegram bot token

Privilege levels: owner → global admin → scoped admin → member.
Roles are stored in `data/v2.db` (central DB), not in env vars.

## Running NanoClaw

```bash
pnpm run dev        # host with hot reload
pnpm run build      # compile TypeScript
./container/build.sh  # rebuild Docker image
pnpm test           # host tests (vitest)
```

Logs: `logs/nanoclaw.log` (full), `logs/nanoclaw.error.log` (errors only).
