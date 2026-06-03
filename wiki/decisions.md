# Technology Decisions

> Key decisions made during the design phase, with rationale and trade-offs.

**Last updated:** 2026-06-03
**Related:** [[overview]], [[architecture]], [[langchain-filter]], [[gmail-integration-issues]]

> Decisions are kept in history even when superseded (ADR style). Entries marked
> **⟳ Superseded** were later reversed — the newest decisions are at the bottom.

---

## Telegram over WhatsApp

**Decision:** Use Telegram as the notification channel.

**Alternatives considered:**
- WhatsApp Personal (Baileys bridge) — unofficial, ToS risk, QR re-auth
- WhatsApp Cloud API — official but requires Meta Business account + dedicated number
- Telegram — bot via @BotFather, no account overhead, no ToS risk

**Why Telegram:**
- 2-minute setup (BotFather → token → done)
- No QR codes, no session drops, no business accounts
- No ban risk for personal low-traffic use
- Most popular choice in self-hosted AI assistant community

**Trade-off:** Requires family members to install Telegram if they don't use it.

---

## Python over TypeScript for LangChain

**Decision:** Implement the pre-filter as a standalone Python script.

**Alternatives considered:**
- LangChain.js (TypeScript) — integrates natively with NanoClaw's Node stack
- Python LangChain — separate process, different runtime

**Why Python:**
- Python LangChain is more mature with better docs and community
- Richer ecosystem (more examples, more integrations)
- Cleaner separation of concerns — pre-filter is independent of NanoClaw internals
- Easier to iterate and debug standalone
- Better for learning LangChain (more tutorials in Python)

**Trade-off:** Two runtimes (Node + Python) on the host machine.

---

## Claude Haiku for Classification ⟳ Superseded → Ollama

> **Superseded:** Now defaults to **local Ollama `qwen3:8b` with `reasoning=False`**
> (free, no API key — the user is on Claude Max, which isn't an API key). Haiku is
> kept as an optional swap via `ANTHROPIC_API_KEY`. The speed gap was closed by
> disabling qwen3's reasoning monologue (~60s → ~7s/email). See the "Ollama with
> `reasoning=False`" decision below and [[gmail-integration-issues]] #4.

**Decision:** Use Claude Haiku for both LangChain stages.

**Alternatives considered:**
- Claude Sonnet — more capable but ~20x more expensive
- Local model via Ollama — free but lower accuracy, more setup
- Rule-based filter — deterministic but brittle, misses nuance

**Why Haiku:**
- Email classification is a simple task — Haiku is more than capable
- ~$0.80/million input tokens → ~$1-3/month for family use
- 500-char body truncation keeps per-email cost negligible
- Reserve Sonnet only for reply drafting (higher quality needed)

---

## NanoClaw Scheduler over External Cron (Option C)

**Decision:** Use NanoClaw's built-in host-sweep scheduler to trigger agents,
not Windows Task Scheduler or a Python polling loop.

**Alternatives considered:**
- Option A: Windows Task Scheduler runs Python script every 30 min
- Option B: Python `while True` / `sleep(1800)` polling loop
- Option C: NanoClaw host-sweep triggers agent on cron schedule ← chosen

**Why Option C:**
- Architecturally correct — uses NanoClaw as it's designed to be used
- NanoClaw's session DB, delivery adapter, and approval flows all work natively
- Better learning — understand how NanoClaw scheduling actually works

**Still valid** — we still use NanoClaw's scheduler. But two specifics changed:
- **Cadence:** ~every 5 hours (windowed 6h check), not every 30 min.
- **The agent no longer "orchestrates the full flow."** It triggers a
  deterministic script (`check_inbox.ts`) and relays the result — the agent
  proved unreliable as an orchestrator. See [[gmail-integration-issues]] #6 and
  the "Orchestration in code" decision below.

---

## LangChain as MCP Server (not standalone script) ⟳ Superseded → HTTP

> **Superseded:** The classifier is still a Python service, but the **agent no
> longer calls it over MCP**. The deterministic `check_inbox.ts` calls a plain
> **HTTP `POST /classify`** endpoint instead. MCP is the door for LLM agents;
> plain HTTP is the door for code, and our orchestrator is code. The
> `classify_emails` MCP tool still exists but is unused. See [[mcp]] and
> [[gmail-integration-issues]] #2.

**Decision:** Wrap the LangChain classifier as a Python MCP server the agent calls.

**Alternatives considered:**
- Standalone Python script writing directly to inbound.db
- Classification logic baked into the agent's CLAUDE.md prompt only

**Why MCP server:**
- Clean separation — LangChain runs on host, agent calls it as a named tool
- MCP is NanoClaw's native tool extension mechanism
- Agent calls it on-demand with structured input/output (JSON schema enforced)
- Can be tested independently of NanoClaw
- Learning goal: building a custom MCP server in Python with FastMCP

**Trade-off:** Requires the Python server to be running before agents start.
Handled with a startup script or Windows service.

---

## Multi-User from the Start

**Decision:** Design for multiple family members from day one.

**Alternatives considered:**
- Build single-user first, add multi-user later
- Use one shared agent group for all family members

**Why multi-user from start:**
- Isolation is architecturally cleaner when designed in from the beginning
- NanoClaw's entity model already supports it natively
- Adding users later would require restructuring the agent group setup
- Separate Telegram bots per person is strictly better UX than a shared bot

**Trade-off:** More initial setup (3x OAuth flows, 3x bot tokens, 3x agent groups).

---

## Docker (NanoClaw Requirement)

**Decision:** Accept Docker as a dependency via NanoClaw.

**Context:** Docker is required by NanoClaw's container isolation model. For this
specific use case (single household, personal data), Docker isolation is more
than needed. A simpler script calling Claude API directly would also work.

**Why accept it:**
- Primary goal includes learning NanoClaw end-to-end
- Docker provides genuine security benefit even for personal use
- Keeping NanoClaw's architecture intact makes future enhancements easier

**Trade-off:** Heavier setup (Docker Desktop install, image build time).

---

## Orchestration in code, not in the agent  *(2026-06-03)*

**Decision:** Move the entire email procedure — search, window, classify-call,
label, dedup — out of the LLM agent and into a deterministic script
(`check_inbox.ts`). The agent only *runs* the script and *relays* the result.

**Why:** The agent repeatedly refused to follow a fixed multi-step procedure even
with explicit "Hard rules" and a fresh session — it re-classified the whole
inbox, skipped the dedup label, made multiple calls, and once just claimed the
tools were "disconnected." LLM agents are reliable at *judgment* and *running an
explicit command*, and unreliable at *being a state machine*. (We even removed
the gmail/classifier MCP tools — `mcpServers: {}` — so there's nothing to
improvise with.) See [[gmail-integration-issues]] #6.

**Trade-off:** The agent can no longer do ad-hoc email actions (read/draft a
specific message) — those tools are gone. Re-add a gmail server if needed.

---

## Windowed check, not a backlog drain  *(2026-06-03)*

**Decision:** Only look at unread mail from the last ~6 hours (`after:<epoch>`),
on a ~5h schedule, with a `BooTuna/seen` label purely to dedup the overlap.
Ignore older mail entirely.

**Alternatives considered:** a bounded "drain" that chewed through the whole
unread backlog a few at a time (built, then dropped).

**Why:** The actual goal is "tell me about important *new* mail," not "review the
whole inbox." A 100+ email backlog would take hours to drain and delay the mail
that actually matters. "Review everything" and "monitor what's new" are different
systems — we picked the one that matches the goal. See [[gmail-integration-issues]] #10.

---

## Ollama with `reasoning=False`, staying free  *(2026-06-03)*

**Decision:** Keep classification on local Ollama `qwen3:8b`, but disable the
reasoning monologue (`reasoning=False` → Ollama `think:false`).

**Why:** `qwen3` is a reasoning model; for a simple labelling task its hidden
`<think>` block was ~all the latency (~60s/email on partial-CPU). Disabling it
dropped to ~7s/email — fast enough to stay free and local instead of paying for
Haiku. Also a correctness win: short classify calls don't outlive their
connection. See [[gmail-integration-issues]] #2, #4.
