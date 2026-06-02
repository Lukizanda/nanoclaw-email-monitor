# Email Classification

> Criteria, prompt design, and category definitions for deciding which emails
> require a family member's personal attention.

**Last updated:** 2026-06-02
**Related:** [[langchain-filter]], [[overview]]

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

When the NanoClaw agent sends a Telegram notification:

```
Important email from {sender_name} <{sender_email}>
Subject: {subject}
Action: {action_type} ({urgency})

{summary}

Want me to draft a reply?
```

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

Before LangChain even runs, use Gmail's own filter to narrow the fetch:

```python
query = "is:unread -in:spam -category:promotions -category:social"
```

This removes obvious spam and social notifications before Claude sees them,
reducing token usage and classification noise.

## Per-Person Criteria

Each family member's NanoClaw `CLAUDE.md` can extend the base criteria:

**Alex (default):** payment, meetings, job, reply, urgent
**Wife:** could add school-related emails, medical appointments
**Kids:** could add gaming/hobby platform emails they care about

The LangChain Stage 1/2 uses shared prompts. Per-person customization happens
at the NanoClaw agent layer (final formatting and additional filtering in `CLAUDE.md`).
