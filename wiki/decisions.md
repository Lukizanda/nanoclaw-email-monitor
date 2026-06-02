# Technology Decisions

> Key decisions made during the design phase, with rationale and trade-offs.

**Last updated:** 2026-06-02
**Related:** [[overview]], [[architecture]], [[langchain-filter]]

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

## Claude Haiku for Classification

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
- Agent orchestrates the full flow (fetch → classify → notify) in one session
- NanoClaw's session DB, delivery adapter, and approval flows all work natively
- Better learning — understand how NanoClaw scheduling actually works

**What changed:** LangChain is now a Python MCP server the agent calls,
not a standalone script that writes to inbound.db directly.

---

## LangChain as MCP Server (not standalone script)

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
