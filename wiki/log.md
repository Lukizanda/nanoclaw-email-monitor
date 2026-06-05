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

**Schedule wired + page added (later same day):** Inserted a recurring `kind=task`
(cron `0 */5 * * *`, Asia/Singapore) that triggers `check_inbox.ts` via an
explicit-command prompt (option B). Verified end-to-end: fired → fresh container →
agent ran the script → 1 important of 7 delivered to Telegram → recurrence advanced
(no re-fire). New wiki page **email-monitor-trigger-flow** documents the wake →
fresh-session → explicit-command-Bash → recurrence flow + the verified trace.
**Pages created:** email-monitor-trigger-flow.

**Schedule durability (later same day):** Realised the schedule is a single
`kind=task` row in the session's `inbound.db` — lost if the session is rebuilt /
data wiped. Built **`scripts/ensure-schedule.ts`**: idempotent re-seed into the
agent group's *current active* session (looks up agent group by stable `folder`,
`findSessionByAgentGroup`, derives Telegram route from the messaging group,
`insertTask` with cron). Wired into `start-all.ps1` as step [4/4] so every
startup re-asserts the schedule. Verified both idempotent (no-op) and seed
(delete → re-create) paths. **Pages created:** schedule-durability.

---

## [2026-06-04] maintenance | Disabled prettier hook + doc-state cleanup

**Type:** session
**Summary:** Fixed the recurring prettier-on-commit churn, then audited and
synced the docs (README + wiki + code comments) to the current implementation.

**What happened:**
- **Prettier pre-commit hook disabled.** Root cause traced: the husky
  `pre-commit` ran `prettier --write "src/**/*.ts"` across the whole tree on
  every commit and rewrote CRLF→LF. Repo blobs are CRLF and this is a Windows
  checkout, so it left ~108 unstaged files dirty after each commit (pure
  line-ending churn, zero real content diff — `git diff --numstat` summed to 0),
  forcing a `git restore -- src/` every time. Upstream maintainers (LF-native
  macOS/Linux) never hit it. Neutered `.husky/pre-commit`; `pnpm run format`
  still available on demand. Committed `e0dd8a5`.
- **Doc-state cleanup.** Audited README + all 16 wiki pages against current
  reality. Most of the wiki was already current from the redesign sync; fixed
  the stragglers that still described the old model:
  - **README.md** — rewrote: classifier is HTTP `/classify` (not "MCP classifier"
    over SSE), added the deterministic `check_inbox.ts` orchestrator + schedule
    sections, status now "working and autonomous" (schedule verified, not "in
    progress"), points at `EMAIL_MONITOR_PLAN_V2.md`.
  - **overview.md** — Phase 6 marked complete (schedule wired/verified); plan V1
    noted as superseded.
  - **running.md** — "four services" reconciled (Docker+Ollama prerequisites;
    start-all manages OneCLI/classifier/host + the ensure-schedule re-seed [4/4]).
  - **onecli.md** — Gmail token is live (not "Phase 3 future").
  - **server.py / test_client.py** — docstrings: live path is `/classify` HTTP;
    `classify_emails` MCP/SSE marked retired; fixed stale `drain_inbox` name →
    `check_inbox.ts`.

**Pages updated:** README, overview, running, onecli, index, log.

---

## [2026-06-05] debug+fix | Perpetual "typing" indicator — split heartbeat signal

**Type:** session
**Summary:** BooTuna showed "typing…" on Telegram indefinitely with no message or
task. Traced it to a 26h warm container holding an idle-but-open query, and fixed
the root cause: one heartbeat file was being used to mean both "alive" and
"working."

**What happened:**
- **Diagnosis (and a corrected hypothesis):** First suspected Telegram `getUpdates`
  redelivery, but the session DB showed the "burst" of inbound was the user's *real*
  messages (asking about the typing itself) — not duplicates. The actual cause was
  host-side typing logic.
- **Root cause:** the poll-loop keeps the interactive query open after a turn (cheap
  follow-ups, see [[gmail-integration-issues]] #7) and touches `.heartbeat` every
  poll tick so an idle container doesn't look dead. The typing module read that same
  fresh heartbeat as "agent working," so an idle-but-open query typed forever until
  a `/clear` / scheduled task / kill ended the query. A quiet overnight stretch with
  no handoff left it typing for hours.
- **Immediate relief:** killed the wedged 26h container (queue fully drained, no
  stale `processing_ack` — safe). Heartbeat went stale → typing stopped.
- **Fix — split the signal:** added a `.working` file touched ONLY in the event loop
  (real provider events), never from the idle poll interval. Typing now gates on
  `.working` (real work) while `.heartbeat` still means "alive" (host-sweep). Files:
  `container/agent-runner/src/db/connection.ts` (+`touchWorking`), `poll-loop.ts`,
  `db/index.ts`, `src/session-manager.ts` (+`workingPath`), `src/modules/typing/index.ts`.
  Both typechecks pass.
- **Deployed:** host rebuilt + restarted (typing fix live); container picks up the
  mounted source on next fresh spawn (no image rebuild). Full writeup:
  [[gmail-integration-issues]] #11.

**Verification status:** deployed but not yet observed end-to-end (no new container
has spawned with the change; Telegram typing can't be observed host-side). Confirm
by messaging BooTuna — typing should clear shortly after each reply.

**Pages updated:** gmail-integration-issues (#11), log.
