# Email Monitor — Plan v2 (current)

> Supersedes `EMAIL_MONITOR_PLAN.md` (v1). This version records **where we came
> from, what changed, and why** — so the design isn't just "the way it is" but a
> trail of decisions. The blow-by-blow lives in `wiki/gmail-integration-issues.md`
> and `wiki/decisions.md`; the current system in `wiki/architecture.md`.

**Status (2026-06-03):** Working end-to-end for one user (Alex / BooTuna) via the
deterministic `check_inbox.ts` path, verified by running the script in-container.
Remaining: wire the recurring schedule; add more family members.

---

## 1. Where we came from (v1)

The original plan (`EMAIL_MONITOR_PLAN.md`) was:

- **The agent does everything.** A scheduled wake every 30 min → the Claude agent
  uses a **Gmail MCP tool** to fetch unread mail → **classifies it itself** using
  criteria written into its `CLAUDE.md` → formats a Telegram notification.
- **Claude Haiku** for classification, **Sonnet** for reply drafting.
- Track a last-poll timestamp; only look at new mail since then.

It was a reasonable v1. Every assumption in it turned out to need revising once we
actually ran it.

---

## 2. What changed, and why

Six pivots, in order. Each links to the detailed write-up.

### P1 — Added a LangChain pre-filter (Python)  · *learning + separation*
v1 classified inside the agent prompt. We split classification into a dedicated
**Python LangChain** two-stage pipeline (coarse junk/ad filter → deep classify).
Reasons: a concrete LangChain/LCEL learning artifact, and a clean
separation — judgment isolated from orchestration, testable on its own.
→ `wiki/langchain-filter.md`

### P2 — Classifier reached over HTTP, not MCP  · *fragility + caller type*
We first exposed the classifier as an **MCP/SSE tool** the agent called. Two
problems: (a) a slow (~15 min) Ollama classify **outlived the SSE connection and
hung the agent forever**; (b) only LLM agents speak MCP comfortably. We added a
plain **`POST /classify`** HTTP endpoint — the door for *code* — and stopped
using the MCP path.
→ `wiki/gmail-integration-issues.md` #2, `wiki/mcp.md`

### P3 — Orchestration moved out of the agent into `check_inbox.ts`  · *the big one*
The agent would **not** reliably follow a multi-step procedure — it re-classified
the whole inbox, skipped the dedup label, made multiple calls, and once just
claimed the tools were "disconnected," even with explicit rules and a fresh
session. So we moved the entire procedure (Gmail search → window → classify-call →
label → dedup) into a **deterministic Bun script**. The agent now only *runs* it
and *relays* the result. We even removed the gmail/classifier MCP tools
(`mcpServers: {}`) so there's nothing to improvise with.
→ `wiki/gmail-integration-issues.md` #6, `wiki/decisions.md` "Orchestration in code"

### P4 — Windowed check, not a backlog drain  · *goal clarity*
We briefly built a bounded "drain the whole unread backlog 3-at-a-time" model,
then realised the goal is **"tell me about important *new* mail,"** not "review
everything." A 100+ email backlog would take hours to drain and delay what
matters. Now: only unread mail from the **last ~6 hours** (`after:<epoch>`), with a
`BooTuna/seen` label purely to dedup the schedule overlap. Old mail is ignored.
→ `wiki/gmail-integration-issues.md` #10

### P5 — Local Ollama (`reasoning=False`), not Haiku  · *free, and fast enough*
v1 assumed paid Haiku. We kept classification **free and local** on Ollama
`qwen3:8b`. The blocker was speed (~60s/email) — fixed by disabling qwen3's
reasoning monologue (`reasoning=False` → ~7s/email). Haiku stays available as an
optional swap via `ANTHROPIC_API_KEY`.
→ `wiki/gmail-integration-issues.md` #4, #5

### P6 — Schedule every ~5h; Gmail via the proxy, not gmail-mcp
Cadence relaxed from 30 min to **~5 hours** (a monitor, not a firehose).
`check_inbox.ts` calls the **Gmail REST API directly through the OneCLI proxy**
(`Bearer onecli-managed`, token injected by host pattern), so no `gmail-mcp` and
no credential in the container.
→ `wiki/gmail-integration-issues.md` #8, #9

**The through-line:** *give the LLM judgment; give code the orchestration.* Almost
every fix above is that principle applied.

---

## 3. Current architecture (v2)

```
NanoClaw scheduler (every 5h)  ──►  Agent runs ONE command: bun check_inbox.ts
                                          │
check_inbox.ts (Bun, in container):       │
  1. Gmail REST via OneCLI proxy ─ unread, last 6h, −label:BooTuna/seen
  2. POST /classify ─► Python classifier (LCEL) ─► Ollama qwen3 (reasoning=False)
  3. apply BooTuna/seen label (dedup)
  4. emit JSON { important }
                                          │
        Agent relays important ──► outbound.db ──► Host ──► Telegram (BooTunaBot)
```

Full detail + diagram: `wiki/architecture.md` and `email-monitor-system.excalidraw`.

**Component responsibilities**

| Layer | Lang | Job |
|------|------|-----|
| `classifier.py` | Python | Decide importance (LangChain + Ollama) |
| `server.py` | Python | Serve it: `POST /classify` (host :8765) |
| `check_inbox.ts` | TS/Bun | Orchestrate: Gmail, windowing, labelling, calling the classifier |
| agent + NanoClaw host | TS | Trigger the script, relay/deliver to Telegram |

---

## 4. Status

- [x] Foundation, OneCLI vault, Telegram channel, agent group (BooTuna)
- [x] Gmail access via OneCLI proxy (REST, not gmail-mcp)
- [x] LangChain classifier (Ollama `reasoning=False`) + `/classify` HTTP endpoint
- [x] `check_inbox.ts` — windowed, label-dedup; **verified via `docker exec`**
- [x] Poll-loop wedge fix (warm containers no longer go deaf on `/clear`)
- [x] **Recurring schedule wired (option B)** — `kind=task`, cron `0 */5 * * *`,
      Asia/Singapore, prompt = explicit `bun check_inbox.ts` command. Verified
      end-to-end (2026-06-03): fired → fresh container → agent ran the script →
      found 1 important of 7 → delivered to Telegram → recurrence advanced to the
      next slot (no re-fire). Fires at 00/05/10/15/20:00 SGT.
- [~] Confirm reliability over many firings. One firing succeeded; if a future
      scheduled run ever fails to execute the script, escalate to **self-deliver**
      (script writes `outbound.db` directly) or option A (agent-free pre-task hook).
- [ ] Additional family members (Wife, Kids) — repeat the agent-group pattern

---

## 5. Next steps (concrete)

1. **Schedule:** create a recurring `kind=task` (cron `0 */5 * * *`, Asia/Singapore)
   whose prompt is the **explicit command** ("Run `bun /workspace/agent/check_inbox.ts`
   and report any important emails"). Explicit-command prompts are the reliable
   lever — vague "check my inbox" is what the agent rationalised around.
2. **Reliability fallback:** if a scheduled run still doesn't execute the script,
   make `check_inbox.ts` write the notification to `outbound.db` itself so delivery
   doesn't depend on the agent relaying at all.
3. **Tune window/cadence** if needed (`CHECK_WINDOW_HOURS`, schedule cron).

---

## 6. Backlog / optional enhancements

| Enhancement | Where it lives now | Notes |
|-------------|--------------------|-------|
| Stage-3 extractor (amount/due-date, meeting time) | `classifier.py` `RunnableBranch` | Richer notifications; chain stays HTTP-compatible |
| VIP-sender rules pre-filter | `classifier.py` `RunnableLambda` | Skip the LLM for known-important senders |
| Ollama→Haiku fallback | `.with_fallbacks([...])` | Free by default, resilient |
| Daily digest mode | scheduler | One 8am summary vs per-run |
| Reply drafting (approval flow) | re-add a gmail tool | Was removed in P3; re-enable if wanted |
| Multi-account Gmail | per-agent-group OneCLI creds | Work + personal |

---

## 7. Key files

| File | Purpose |
|------|---------|
| `groups/dm-with-alex-emailmonitor/check_inbox.ts` | The deterministic orchestrator (our code) |
| `groups/dm-with-alex-emailmonitor/CLAUDE.local.md` | Agent playbook — "run the script, relay result" |
| `groups/dm-with-alex-emailmonitor/container.json` | `mcpServers: {}` (no email tools by design) |
| `email-filter/classifier.py` | LCEL two-stage classifier (judgment) |
| `email-filter/server.py` | `/classify` HTTP endpoint + (vestigial) MCP tool |
| `container/agent-runner/src/poll-loop.ts` | Patched: `/clear` handoff + heartbeat fix |
| `wiki/` | `architecture`, `gmail-integration-issues`, `decisions`, `langchain-filter`, `mcp` |

---

## 8. Resuming

> "Email monitor on NanoClaw. Current plan: `EMAIL_MONITOR_PLAN_V2.md`. The system
> is the `check_inbox.ts` windowed model — read `wiki/architecture.md`. Next task:
> wire the every-5h schedule."

`EMAIL_MONITOR_PLAN.md` (v1) is kept for history — it's the original
agent-orchestrated design, now superseded.
