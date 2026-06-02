# Email Monitor Agent — Build Plan

## Overview

An AI agent that polls your Gmail inbox on a schedule, classifies emails against
importance criteria, and sends you a Telegram notification when something needs
your attention. Built on NanoClaw v2.

**Stack:**
- NanoClaw v2 (host + agent container)
- Gmail MCP tool (via OneCLI OAuth)
- Telegram (notification channel)
- Claude Haiku (classification) / Claude Sonnet (reply drafting)

---

## System Flow

```
Gmail Inbox
     │
     │  Gmail API (OAuth via OneCLI)
     ▼
Scheduler (every 30-60 min)
     │
     ▼
inbound.db ──► Agent Container (Docker)
                    │
                    ▼
             ┌──────────────┐
             │  Claude LLM  │
             │              │
             │  Gmail Tool  │◄── fetch emails since last poll
             │  (MCP)       │
             └──────┬───────┘
                    │
                    │ classify against criteria
                    ▼
             important? ──No──► do nothing, update last-poll timestamp
                  │
                 Yes
                  │
                  ▼
            outbound.db
                  │
                  ▼
        Telegram Channel Adapter
                  │
                  ▼
        "⚠️ Important email from X:
         Subject: ...
         Summary: ...
         Want me to draft a reply?"
```

---

## Classification Criteria

Claude will flag emails matching any of the following:

- **Payment / Financial** — invoices, overdue notices, billing issues, bank alerts
- **Meetings** — calendar invites, scheduling requests, meeting confirmations
- **Job / Career** — interview invitations, recruiter follow-ups, offer letters, HR correspondence
- **Personal response required** — emails addressed directly to you requiring a reply (not newsletters, not CC'd bulk mail)
- **Urgent / time-sensitive** — any email with explicit urgency signals (deadlines, "ASAP", "by end of day")

Emails that do NOT match: newsletters, marketing, automated notifications, receipts (unless overdue), CC'd FYI emails.

---

## Phase 1 — Foundation

**Goal:** Get NanoClaw running locally.

- [ ] Install Node dependencies: `pnpm install` (from repo root)
- [ ] Copy `.env.example` to `.env`
- [ ] Add `ANTHROPIC_API_KEY` to `.env`
- [ ] Run NanoClaw once to initialize `data/v2.db`: `pnpm run dev`
- [ ] Confirm host starts without errors, then stop it

**Files to know:**
- `.env` — all secrets and config
- `data/v2.db` — central SQLite database (auto-created on first run)
- `src/index.ts` — entry point

---

## Phase 2 — OneCLI (Credential Vault)

**Goal:** Install OneCLI so OAuth tokens are stored securely and injected at
request time — never hardcoded in env vars or chat context.

- [ ] Run the `/init-onecli` skill in Claude Code
- [ ] Follow the prompts to install OneCLI and start the vault service
- [ ] Verify OneCLI is running: `onecli --help`

**Why this matters:** Gmail OAuth tokens live in the OneCLI vault. The agent
never sees raw credentials — the vault proxies requests and injects tokens
automatically.

---

## Phase 3 — Gmail Tool

**Goal:** Wire Gmail as an MCP tool available inside the agent container.

- [ ] Run the `/add-gmail-tool` skill in Claude Code
- [ ] Complete the OAuth flow (browser redirect, sign in with Google, grant permissions)
- [ ] Verify the tool appears in the agent's MCP tool list

**Scopes needed:** `gmail.readonly` is sufficient for read + classify.
Add `gmail.compose` only if you want the agent to draft replies.

**Key MCP tool calls the agent will use:**
- `list_emails` — fetch emails with filters (after timestamp, unread, etc.)
- `get_email` — fetch full body of a specific email
- `search_emails` — Gmail query syntax (e.g. `is:unread after:2024/01/01`)

---

## Phase 4 — Telegram Channel

**Goal:** Wire Telegram as the notification delivery channel.

- [ ] Open Telegram, search for `@BotFather`
- [ ] Send `/newbot`, follow prompts, copy the bot token
- [ ] Add `TELEGRAM_BOT_TOKEN=<your-token>` to `.env`
- [ ] Run the `/add-telegram` skill in Claude Code
- [ ] Start a conversation with your new bot in Telegram
- [ ] Run `/init-first-agent` to bootstrap the agent and wire it to your Telegram DM

---

## Phase 5 — Email Monitor Agent Configuration

**Goal:** Configure the agent group with the right personality, tools, and schedule.

### 5a. Agent Personality (CLAUDE.md)

Edit `groups/main/CLAUDE.md` (or create a dedicated `groups/email-monitor/`) and
add an instruction block like:

```markdown
## Role
You are an email monitoring assistant. Your job is to periodically check the
user's Gmail inbox and notify them only when an email genuinely requires their
personal attention.

## Classification Rules
Flag an email as important if it matches ANY of:
- Payment, invoice, billing, overdue, financial action required
- Meeting invite or scheduling request that needs a response
- Job-related: interview, recruiter, offer, HR, contract
- Direct personal email requiring a reply (not newsletters, not bulk CC)
- Explicit urgency: deadline, ASAP, time-sensitive language

Do NOT notify for: newsletters, marketing, automated receipts, CC FYIs,
promotional emails, social media notifications.

## Notification Format
When you find an important email, send:
- Sender name and email
- Subject
- 2-3 sentence summary of what action is needed
- Ask if the user wants a draft reply (only if a reply is appropriate)

## Poll Behavior
- Only check emails received since your last poll (track the timestamp)
- If nothing important, stay silent — do not send "all clear" messages
- Batch multiple important emails in one message if found in the same poll
```

### 5b. Scheduled Poll

Use NanoClaw's scheduling system to trigger the agent every 30-60 minutes.

- [ ] Configure the recurrence rule in the session or via the scheduling MCP tool
- [ ] Set poll interval: `*/30 * * * *` (every 30 min) or `0 * * * *` (hourly)
- [ ] Store last-poll timestamp in session state so only new emails are fetched

---

## Phase 6 — Testing & Tuning

- [ ] Send yourself a test email matching each criteria category
- [ ] Confirm notifications arrive on Telegram with correct summaries
- [ ] Send non-matching emails (newsletter, receipt) and confirm silence
- [ ] Tune classification prompt based on any false positives/negatives
- [ ] Optionally: test the "draft reply" approval flow

---

## Phase 7 — Optional Enhancements

| Enhancement | Effort | Value |
|-------------|--------|-------|
| Daily digest mode (one summary at 8am instead of real-time) | Low | Reduces interruptions |
| Reply drafting with approval flow | Medium | Saves time on routine replies |
| Priority levels (urgent vs. FYI) | Low | Better signal in notifications |
| Attachment awareness (flag if important attachment present) | Low | Catches contract PDFs etc. |
| Multi-account Gmail support | Medium | Work + personal inbox |

---

## Cost Estimate

| Inbox volume | Poll interval | Est. tokens/month | Approx cost/month |
|-------------|---------------|-------------------|-------------------|
| Light (20 emails/day) | 60 min | ~750k | ~$0.75 |
| Moderate (100 emails/day) | 30 min | ~3M | ~$3 |
| Heavy (500+ emails/day) | 60 min | ~10M | ~$10 |

Using Claude Haiku for classification (~$0.80/million input tokens).
Switch to Sonnet only for reply drafting.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `.env` | API keys, bot tokens, config |
| `data/v2.db` | Central DB — users, agent groups, sessions |
| `data/v2-sessions/` | Per-session inbound/outbound DBs |
| `groups/main/CLAUDE.md` | Agent personality and instructions |
| `src/router.ts` | Inbound message routing |
| `src/delivery.ts` | Outbound delivery via channel adapters |
| `src/host-sweep.ts` | Scheduled wake / recurrence logic |
| `container/agent-runner/src/` | Agent poll loop and tool execution |
| `logs/nanoclaw.log` | Full host log |
| `logs/nanoclaw.error.log` | Errors and delivery failures |

---

## Resuming This Plan

When continuing in a new session, tell Claude:
> "I'm building an email monitor agent on NanoClaw. The plan is in
> `EMAIL_MONITOR_PLAN.md`. I'm currently on Phase X."

Check off completed items as you go.
