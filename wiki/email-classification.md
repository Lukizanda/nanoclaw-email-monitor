# Email Classification

> Criteria, prompt design, and category definitions for deciding which emails
> require a family member's personal attention.

**Last updated:** 2026-06-03
**Related:** [[langchain-filter]], [[overview]], [[architecture]]

## Classification Categories

### Stage 1 — Coarse Filter

| Category | Description | Action |
|----------|-------------|--------|
| `junk` | Spam, phishing, unsolicited bulk mail | Discard |
| `ad` | Promotional, marketing, sales offers | Discard |
| `newsletter` | Subscription content, digests, announcements | Discard |
| `important` | Requires personal attention or action | Forward to Stage 2 |

### Stage 2 — Action Type

| Action Type | Examples | Urgency |
|-------------|----------|---------|
| `payment` | Invoice overdue, billing issue, bank alert | High |
| `meeting` | Calendar invite, scheduling request, confirmation | Medium |
| `job` | Interview invite, recruiter follow-up, offer letter | High |
| `reply` | Personal email requiring direct response | Medium |
| `urgent` | Any email with explicit deadline/ASAP language | High |

## Classification Prompt (Stage 1)

```
You are an email pre-filter. Classify this email into exactly one category.

Categories:
- "junk"       : spam, phishing, unsolicited bulk mail
- "ad"         : promotional, marketing, sales offers
- "newsletter" : subscription content, digests, announcements
- "important"  : requires personal attention or action

Email:
From: {sender}
Subject: {subject}
Body preview: {body_preview}

Respond with JSON only: {"category": "...", "reason": "..."}
```

## Classification Prompt (Stage 2)

```
This email passed the importance filter. Classify what action is needed.

Types:
- "payment"  : invoice, billing, overdue, financial action required
- "meeting"  : calendar invite, scheduling request, needs response
- "job"      : interview, recruiter, offer, HR, contract
- "reply"    : personal email requiring a direct response
- "urgent"   : explicit deadline, ASAP, time-sensitive language

Email:
From: {sender}
Subject: {subject}
Body: {body_preview}

Respond with JSON:
{"action_type": "...", "summary": "2-3 sentence summary of action needed",
 "urgency": "high|medium|low"}
```

## Notification Format (Telegram)

The agent relays each important email from `check_inbox.ts` in this format (from
`CLAUDE.local.md`), batching multiple into one message:

```
📬 <action_type emoji> <sender name>
Subject: <subject>
<2–3 sentence summary of what action is needed>
Urgency: <high|medium|low>
```

Action-type emojis: payment 💳 · meeting 📅 · job 💼 · reply ✉️ · urgent ⏰

## Edge Cases and Tuning Notes

**False positive risks:**
- Receipts that mention "payment" but are just confirmations (not overdue)
- CC'd emails that look personal but don't require a reply
- Auto-generated meeting notifications from calendar apps (already accepted)

**False negative risks:**
- Emails from unknown senders that are actually important (job leads, new contacts)
- Urgent emails with no explicit urgency keywords in subject line

**Tuning approach:**
- Start with the criteria above
- After first week, review any missed important emails
- Add sender-based rules if specific domains are consistently mis-classified
- Consider adding a `sender_whitelist` for known important contacts

## Gmail Pre-Filter Query

`check_inbox.ts` narrows the fetch with Gmail's own search before anything is
classified — this is the windowing + dedup layer:

```
is:unread after:<epoch of now-6h> -label:BooTuna/seen
```

- `is:unread` — only mail the user hasn't seen
- `after:<epoch>` — last ~6h only (Gmail's `newer_than:` has no hour unit, so we
  use an epoch timestamp; see [[gmail-integration-issues]] #9)
- `-label:BooTuna/seen` — skip anything already checked (dedup across the
  overlapping schedule)

Spam/promotions are already excluded by `is:unread` + the Stage 1 junk/ad filter.

## Per-Person Criteria

Each family member's NanoClaw `CLAUDE.md` can extend the base criteria:

**Alex (default):** payment, meetings, job, reply, urgent
**Wife:** could add school-related emails, medical appointments
**Kids:** could add gaming/hobby platform emails they care about

The LangChain Stage 1/2 currently uses shared prompts, and the agent no longer
does any filtering of its own (the script + classifier decide importance). So
per-person customization would live in the classifier (e.g. per-group prompt
variants, a VIP-sender rules runnable — see [[langchain-filter]] "Extending the
chain") rather than in the agent's `CLAUDE.md`. Not yet implemented — only Alex
is wired today.
