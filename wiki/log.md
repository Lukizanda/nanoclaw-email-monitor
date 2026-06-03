# Log

Append-only chronological record of sessions, ingests, and decisions.

---

## [2026-06-02] init | Project wiki created

**Type:** session
**Summary:** First session. Explored NanoClaw codebase, scoped the email monitor
project, and designed the multi-user family architecture.

**What happened:**
- Explored NanoClaw v2 codebase — fresh clone, nothing initialized
- Scoped project: Gmail polling → LangChain filter → NanoClaw agent → Telegram
- Decided on Telegram over WhatsApp (less friction, no ToS risk)
- Decided on Python LangChain for pre-filter (more mature ecosystem, learning goal)
- Designed two-stage classification: Stage 1 junk/ad filter, Stage 2 deep classify
- Expanded scope to multi-user family setup (Alex, Wife, Kids — one agent group each)
- Created `EMAIL_MONITOR_PLAN.md` (7-phase build plan)
- Created `email-monitor-system.excalidraw` (system diagram)
- Created this wiki

**Key decisions made:** See [[decisions]]

---

## [2026-06-02] build | Phase 1 + LangChain MCP server written

**Type:** session
**Summary:** Installed dependencies, created .env, wrote the Python LangChain MCP server.

**What happened:**
- Installed pnpm, ran `pnpm install` (274 packages, better-sqlite3 compiled from source)
- Created `.env` with BooButt assistant name, Asia/Singapore timezone, ANTHROPIC_API_KEY placeholder
- Installed Python packages: mcp 1.27.2, langchain-anthropic 1.4.4, langchain-core 1.4.0
- Decided to use NanoClaw's built-in host-sweep scheduler (Option C) over external cron
- Decided to wrap LangChain as a Python MCP server (not standalone script)
- Wrote `email-filter/classifier.py` — LCEL chains (Stage 1 coarse + Stage 2 deep)
- Wrote `email-filter/server.py` — FastMCP server on port 8765, SSE transport
- Updated Excalidraw diagram to v2 reflecting MCP server architecture
- Updated wiki: architecture, langchain-filter, decisions

**Files created:** email-filter/classifier.py, email-filter/server.py, email-filter/requirements.txt
**Next:** pnpm build passes, first `pnpm run dev` to init DB, then Phase 2 (OneCLI)

---

## [2026-06-02] build | Phases 1-4 complete — agent responding on Telegram

**Type:** session
**Summary:** Brought the full stack up on Windows. Many platform issues hit and
fixed (documented in [[windows-setup-issues]]). Agent now responds on Telegram.

**What happened:**
- Phase 1: Docker Desktop installed (BIOS SVM enable, factory reset, WSL Ubuntu, WSL integration)
- Fixed CRLF/BOM in all shell scripts; Dockerfile pnpm PATH (`/pnpm/bin`)
- Built agent container image; tagged for Windows slug mismatch
- Phase 2: OneCLI installed (Docker compose), CLI in WSL, Anthropic token registered
- Created start-all.ps1 / stop-all.ps1 / build-container.ps1 scripts
- Phase 3-4: Telegram adapter copied from channels branch, paired DM, init-first-agent
- Created agent group `dm-with-alex-emailmonitor` (ag-1780421201100-eatf5p), persona BooTuna
- Fixed: symlink EPERM (Developer Mode), claude path (`/pnpm/bin/claude`),
  claude native binary (cli-wrapper.cjs fallback), stale containers, resolveChannelName
- **Agent successfully responds on Telegram** ✓

**Decisions:** switched classifier default to Ollama (no API key on Claude Max);
Anthropic fallback. See [[decisions]].

**Pages created:** onecli, mcp, windows-setup-issues
**Next:** Phase 5 — configure agent CLAUDE.md with email criteria + recurring poll schedule

---

## [2026-06-03] build | Phase 5 — classifier wired + validated end-to-end

**Type:** session
**Summary:** Wired the LangChain classifier into the agent as an SSE MCP tool and
validated it end-to-end. Core intelligence layer proven working.

**What happened:**
- Discovered agent-runner only supported stdio MCP servers; the SDK supports
  sse/http natively. Extended agent-runner ([[mcp]] gotcha section):
  - types.ts: McpServerConfig now union (stdio | remote sse/http)
  - config.ts + index.ts: pass remote configs through to SDK
- Registered email-classifier (SSE, host.docker.internal:8765) in the agent
  group's container.json
- Rewrote groups/dm-with-alex-emailmonitor/CLAUDE.local.md: classification
  criteria, notification format, recurring-poll (cron */30) setup instructions
- Fixed server.py: FastMCP host/port moved to constructor (run() API changed)
- Fixed start-all.ps1: pnpm.cmd (bare 'pnpm' fails in Start-Process on Windows)
- **Validated classifier end-to-end** via test_client.py over SSE: 4 emails →
  2 important (payment/high, meeting/medium), newsletter+ad correctly dropped.
  Full chain works: SSE → FastMCP → LCEL → Ollama qwen3:8b.

**Known gap:** gmail MCP tool not installed yet (Telegram done, Gmail OAuth
skipped). Classifier path testable now; true end-to-end email monitoring needs
the Gmail tool (/add-gmail-tool).

**Next:** (1) agent-level test — message BooTuna to call classify_emails from
inside the container (validates container→host SSE). (2) /add-gmail-tool for
real inbox access. (3) verify recurring schedule fires.

**UPDATE (same session):** Agent-level test PASSED. BooTuna called classify_emails
over SSE from inside the container, correctly flagged an overdue invoice
(payment/high) and dropped a newsletter, and reported in the notification format.
Full chain validated: Telegram → NanoClaw → container → SSE → host classifier →
Ollama → Telegram. Note: container→host SSE is slow on first call (Ollama cold +
local model) — agent "types" for a while before replying; this is expected, not
a hang. Remaining: /add-gmail-tool (real inbox), verify recurring */30 schedule.
**Pages created:** overview, architecture, nanoclaw, langchain-filter, email-classification, decisions

---

## [2026-06-03] debug+redesign | Gmail end-to-end: fought the agent, moved orchestration into code

**Type:** session
**Summary:** Took the monitor from "wired" to "actually working." A chain of
runtime headaches across Gmail/classifier/agent/scheduler, then an architecture
pivot: stop making the LLM agent the orchestrator. Full writeup in
[[gmail-integration-issues]].

**What happened:**
- **SSE classify hang (root cause found):** a slow (~15 min) Ollama classify
  outlived the MCP SSE connection → result lost → agent hung forever. Heartbeat
  froze. Not "just slow" — a transport correctness bug.
- **processing_ack poison loop:** force-killing the hung container left a
  `processing` claim (in outbound.db) → host-sweep killed every new spawn.
  Cleared the claim + retired the message. Lesson: don't force-kill progressing
  runs.
- **Ollama speed:** `qwen3:8b` reasoning monologue = ~60s/email. `reasoning=False`
  (no_think) → ~7s/email.
- **Haiku flip:** `ANTHROPIC_API_KEY` in `.env` silently switched the classifier
  off Ollama; `load_dotenv` won't override ambient env. Clear it per-process.
- **Agent adherence (the big one):** even with explicit rules + fresh session +
  removed tools, the agent would not run the bounded procedure — it improvised a
  freeform whole-inbox classify, or claimed "tools disconnected." 
- **Poll-loop wedge fixed:** warm containers went deaf because an open
  interactive query blocked the main loop and `/clear` had no path to end it.
  Generalised the task-handoff to also end the query for `/clear`; touch
  heartbeat in the poll interval. `poll-loop.ts`.
- **Architecture pivot:** moved all orchestration into a deterministic Bun script
  (`check_inbox.ts`) that does Gmail REST (via the OneCLI proxy, `Bearer
  onecli-managed`) → HTTP `/classify` (added a `custom_route` to server.py) →
  dedup label. Agent reduced to "run one command, relay result." Removed the
  gmail/classifier MCP servers (`mcpServers: {}`) so there's nothing to improvise
  with.
- **Requirement pivot:** dropped the "drain the whole backlog" model for a simple
  **windowed check** — unread mail from the last 6h (`after:<epoch>`; Gmail
  `newer_than` has no hour unit), `BooTuna/seen` label only for overlap dedup.
  Target schedule: every 5h.

**Decisions:** keep LangChain (extensibility — add runnables later, e.g. a
RunnableBranch stage-3 extractor); stay on free Ollama with no_think; split
judgment (LLM/LangChain) from orchestration (code).

**State:** `check_inbox.ts` verified working via `docker exec`. Still to do: wire
the every-5h schedule with an explicit-command task prompt; confirm the agent
runs it reliably (else have the script self-deliver).

**Pages created:** gmail-integration-issues
**Pages synced to the new architecture:** architecture, mcp, langchain-filter,
overview, decisions (ADR-style supersede + 3 new decisions), email-classification,
running. Stale "agent calls classify_emails over SSE every 30 min / LangChain
polls Gmail and writes inbound.db" claims removed; MCP path marked retired in
favour of HTTP `/classify` + `check_inbox.ts`.
