# Email Monitor — Schedule Durability (sessions & re-seeding)

> The recurring email check lives as **one row** in a session's `inbound.db` —
> not in code, config, or the central DB. So it can silently vanish if the
> session is rebuilt. This page explains when that happens and how
> `scripts/ensure-schedule.ts` makes the schedule self-healing.

**Last updated:** 2026-06-03
**Related:** [[email-monitor-trigger-flow]], [[architecture]], [[nanoclaw]], [[running]]

## The situation

The 5-hour schedule is a single `kind=task` row (with a `recurrence` cron) in:

```
data/v2-sessions/<agent-group>/<session>/inbound.db  →  messages_in
```

It is **the only copy** — there's no schedule in source, in `.env`, or in the
central `v2.db`. NanoClaw runs schedules entirely off these per-session task
rows. Great for the framework; fragile for *us*, because the row is tied to a
specific **session**, and a session can be re-created.

## When the schedule survives — and when it's lost

A session (and its `inbound.db`) is **reused** as long as `resolveSession()`
([src/session-manager.ts](src/session-manager.ts#L86)) finds an existing
**active** session for the `(agent_group, messaging_group, thread)` key.

| Event | Schedule survives? |
|-------|--------------------|
| Reboot / restart services | ✅ same files reused |
| New container per fire / container restart | ✅ |
| `/clear` (resets LLM memory only) | ✅ |
| **Session row deleted / `status` ≠ `active`** | ❌ new session minted → row gone |
| **`data/` (or the session dir) wiped** | ❌ |
| **Re-pair / re-`/init-first-agent`** (new ids) | ❌ new key → new session |

In all the ❌ cases the monitor just **stops silently** — no error, no
notification — because nothing recreates the row. That's the gap this page
closes.

## The fix: `scripts/ensure-schedule.ts`

An **idempotent re-seed**. It re-establishes the schedule in whatever the agent
group's **current active session** is, so a rebuilt session gets the schedule
back automatically.

What it does:
1. `initDb(data/v2.db)` → look up the agent group by its **stable `folder`**
   (`dm-with-alex-emailmonitor`), not a volatile id.
2. `findSessionByAgentGroup(id)` → the **current active** session
   ([src/db/sessions.ts](src/db/sessions.ts#L56)).
3. `openInboundDb(...)` on that session.
4. **Idempotency:** if a `kind=task` row with a `recurrence` and the
   `check_inbox.ts` marker is already `pending`/`processing`, **do nothing**.
5. Otherwise derive the reply route from the session's **messaging group**
   (`channel_type` + `platform_id` — so it self-heals routing too, not hardcoded),
   compute the next fire via `cron-parser` in `TIMEZONE`, and `insertTask(...)`
   — the same insert NanoClaw's own scheduler uses.

It reuses NanoClaw's own functions (`insertTask`, `findSessionByAgentGroup`,
`cron-parser`), so a re-seeded row is byte-for-byte what a native schedule would
be. No-op and safe to run repeatedly.

### Run it

```powershell
# manual
pnpm exec tsx scripts/ensure-schedule.ts
# tunables
$env:SCHEDULE_CRON = "0 */5 * * *"; $env:SCHEDULE_AGENT_FOLDER = "dm-with-alex-emailmonitor"
```

It is wired into **`scripts/start-all.ps1`** as step **[4/4]** (runs ~6s after the
host starts, once the DB is initialised), so **every startup re-asserts the
schedule**. If the session was rebuilt while down, the next boot puts the
schedule back.

### What it does NOT do

- It won't seed if there's **no active session yet** (fresh install before first
  pairing) — it logs and exits 0; the schedule gets created once a session
  exists (next startup, or the agent's first-run path).
- It only ensures **one** recurring check exists; it never duplicates.

## Verified (2026-06-03)

- **Idempotent path:** with a recurring task present, it detected it
  (`task-…ys2h0u`) and did nothing. ✓
- **Seed path:** deleted the row to simulate a rebuilt session → re-ran → it
  seeded an equivalent task (correct cron, next fire 00:00 SGT, route
  `telegram:<chat-id>` derived from the messaging group). ✓ Net: exactly one
  valid schedule.

## Mental model

The hand-inserted task row was the *origin*; `ensure-schedule.ts` is the
**durable source of truth**. The row is disposable state that can be regenerated;
the script (version-controlled, run on every startup) is what actually guarantees
the monitor keeps firing across session rebuilds and data wipes.

For *how* the task fires once it exists (wake → fresh session → explicit-command
Bash → recurrence), see [[email-monitor-trigger-flow]].
