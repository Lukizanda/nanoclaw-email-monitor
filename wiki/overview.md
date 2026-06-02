# Project Overview

> A self-hosted, multi-user email monitoring agent that watches Gmail inboxes and
> sends Telegram notifications when emails require personal attention.

**Last updated:** 2026-06-02
**Related:** [[architecture]], [[decisions]], [[email-classification]]

## Goal

Build an always-on agent running on a home desktop that:
1. Polls each family member's Gmail inbox every 30 minutes
2. Pre-filters junk, ads, and newsletters (Python LangChain)
3. Deep-classifies remaining emails (Claude Haiku via NanoClaw)
4. Sends a Telegram notification with a summary when action is required

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

**Phase:** Pre-build (planning complete, nothing initialized)

- [ ] Phase 1 — Foundation (pnpm install, .env, first run)
- [ ] Phase 2 — OneCLI credential vault
- [ ] Phase 3 — Gmail MCP tool
- [ ] Phase 4 — Telegram channel
- [ ] Phase 5 — Agent configuration + schedule
- [ ] Phase 6 — Testing and tuning
- [ ] Phase 7 — Optional enhancements

See `EMAIL_MONITOR_PLAN.md` in the repo root for full phase details.

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
