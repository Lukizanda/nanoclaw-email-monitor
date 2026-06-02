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
**Pages created:** overview, architecture, nanoclaw, langchain-filter, email-classification, decisions
