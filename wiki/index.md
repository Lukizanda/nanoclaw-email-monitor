# Wiki Index

Catalog of all pages. Updated on every session.

**Last updated:** 2026-06-04
**Total pages:** 16

---

## Core

| Page | Summary |
|------|---------|
| [[overview]] | Project goals, family use case, current build status |
| [[architecture]] | End-to-end system design, components, data flow, isolation boundaries (static view) |
| [[email-monitor-trigger-flow]] | Dynamic view: how a scheduled wake fires the agent, the explicit-command method that makes it run the check, recurrence, verified trace |
| [[decisions]] | Technology decisions with rationale and trade-offs |

## Components

| Page | Summary |
|------|---------|
| [[nanoclaw]] | NanoClaw platform — host, entity model, two-DB session split, key files |
| [[onecli]] | OneCLI credential vault — architecture, CLI commands, secret modes, gotchas |
| [[mcp]] | Model Context Protocol — what it is, FastMCP, our custom classifier server, wiring |
| [[langchain-filter]] | Python LangChain classifier — LCEL chains, two-stage classification, served over HTTP (`/classify`; MCP retired), model fallback |
| [[email-classification]] | Classification criteria, prompts, notification format, edge cases |
| [[telegram-flow]] | How Telegram messaging works — long polling, outbound-only, chat ID, polling vs webhooks |

## Operations

| Page | Summary |
|------|---------|
| [[running]] | Startup runbook — the 4 services, start order, health checks, log locations, debugging |
| [[windows-setup-issues]] | Every problem hit on Windows (CRLF, Docker, WSL, pnpm, stale containers) and its fix |
| [[schedule-durability]] | Why the schedule can vanish on session rebuild, and the idempotent `ensure-schedule.ts` re-seed wired into startup |
| [[gmail-integration-issues]] | Runtime/integration headaches: SSE-classify hang, processing_ack poison, Ollama no_think, agent adherence, poll-loop wedge, Gmail-via-proxy, drain→windowed pivot |

## Meta

| Page | Summary |
|------|---------|
| [[log]] | Append-only session and decision log |
| [[WIKI]] | Schema — conventions, workflows, page format |

---

## Sources

Raw source documents live in `wiki/sources/`. None added yet.

To add a source: drop a file in `wiki/sources/` and ask Claude to ingest it.
Claude will read it, update relevant wiki pages, and append to the log.
