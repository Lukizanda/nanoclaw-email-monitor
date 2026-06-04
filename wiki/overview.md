# Project Overview

> A self-hosted, multi-user email monitoring agent that watches Gmail inboxes and
> sends Telegram notifications when emails require personal attention.

**Last updated:** 2026-06-04
**Related:** [[architecture]], [[decisions]], [[email-classification]], [[gmail-integration-issues]], [[schedule-durability]], [[email-monitor-trigger-flow]]

## Goal

Build an always-on agent running on a home desktop that:
1. Checks each family member's Gmail for **unread mail from the last ~6 hours**
   (windowed, not a backlog drain), on a schedule (~every 5 hours)
2. Pre-filters junk, ads, and newsletters (Python LangChain, Stage 1)
3. Deep-classifies remaining emails (local Ollama by default; Haiku optional)
4. Sends a Telegram notification with a summary when action is required

The check itself is a deterministic script (`check_inbox.ts`); the agent only
triggers it and relays the result. See [[architecture]].

## Users

| Person | Gmail | Telegram | Role |
|--------|-------|----------|------|
| Alex | alex@example.com | Alex's bot | owner |
| Wife | TBD | Wife's bot | admin (scoped) |
| Kids | TBD | Kids' bot | member |

Each family member is fully isolated — separate agent group, separate credentials,
separate Docker container. No data crossover.

## Classification Criteria

An email is flagged as important if it matches any of:
- Payment / invoice / billing / overdue
- Meeting invite or scheduling request
- Job-related: interview, recruiter, offer, HR
- Personal email requiring a direct reply
- Explicit urgency (deadline, ASAP, time-sensitive)

See [[email-classification]] for the full prompt design.

## Current Status

**Working and autonomous for Alex, via the deterministic `check_inbox.ts` path.**
The full chain is verified end-to-end through the scheduled 5-hour wake (not just
manual `docker exec`): the recurring task fires → fresh container → agent runs the
script → important mail delivered to Telegram.

- [x] Phase 1 — Foundation (pnpm, .env, container image, first run)
- [x] Phase 2 — OneCLI credential vault (Anthropic + Gmail tokens)
- [x] Phase 3 — Gmail access (now via REST through the OneCLI proxy, not gmail-mcp)
- [x] Phase 4 — Telegram channel (BooTunaBot, paired DM)
- [x] Phase 5 — Classification + `check_inbox.ts` orchestration (windowed, label-dedup)
- [x] Phase 6 — Scheduling: every-5h recurring `kind=task` wired and verified
      end-to-end (cron `0 */5 * * *`, Asia/Singapore); durability via
      `ensure-schedule.ts` re-seed in `start-all.ps1`. See [[schedule-durability]]
      and [[email-monitor-trigger-flow]]. Only open item: a script self-deliver
      fallback if the agent ever narrates instead of running the command.
- [ ] Phase 7 — Additional family members (Wife, Kids)

**Key architecture note:** orchestration was moved out of the LLM agent and into
`check_inbox.ts` after the agent proved an unreliable orchestrator — see
[[gmail-integration-issues]] for the full story. `EMAIL_MONITOR_PLAN.md` (V1)
predates this pivot and is superseded by `EMAIL_MONITOR_PLAN_V2.md` (the current plan).

## Why NanoClaw

- Self-hosted — emails never leave the home machine
- Multi-user isolation built in (per-agent Docker containers)
- Channel adapters abstract Telegram delivery
- Extensible — can add more family members, more channels, more tools later

## Learning Goals

- NanoClaw v2 architecture (host + container, session DBs, entity model)
- Python LangChain and LCEL (chain composition, batch processing, async)
- Gmail OAuth via OneCLI credential vault
- Docker container isolation in practice
