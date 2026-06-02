# LangChain Pre-Filter

> Python LangChain MCP server that classifies emails inside the NanoClaw agent
> flow — exposed as an MCP tool that Docker containers call via HTTP.

**Last updated:** 2026-06-02
**Related:** [[architecture]], [[email-classification]], [[decisions]]

## Role in the System

The LangChain classifier runs as an always-on Python MCP server on the host
machine (`email-filter/server.py`, port 8765). NanoClaw Docker containers call
it via `host.docker.internal:8765` using the MCP protocol.

The agent orchestrates the full flow:
```
NanoClaw Sweep → Docker Container
    → Gmail MCP tool (fetch emails)
    → classify_emails MCP tool (LangChain server)
    → Claude Sonnet (format + notify)
    → Telegram
```

## Two-Stage Chain

### Stage 1 — Coarse Filter

Classifies each email into one of:
- `junk` — spam, phishing, unsolicited bulk mail
- `ad` — promotional, marketing, sales offers
- `newsletter` — subscription content, digests, announcements
- `important` — requires personal attention or action

Junk / ad / newsletter → discard. Only `important` proceeds to Stage 2.

### Stage 2 — Deep Classify

Classifies important emails by action type:
- `payment` — invoice, billing, overdue, financial
- `meeting` — calendar invite, scheduling, confirmation
- `job` — interview, recruiter, offer, HR
- `reply` — personal email requiring direct response
- `urgent` — explicit deadline, ASAP, time-sensitive language

Also produces: a 2-3 sentence `summary` and an `urgency` level (high/medium/low).

## LCEL Implementation

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

model = ChatAnthropic(model="claude-haiku-4-5-20251001")

# Stage 1 chain
filter_chain = filter_prompt | model | JsonOutputParser()

# Stage 2 chain
deep_chain = deep_prompt | model | JsonOutputParser()

# Full pipeline
def poll_and_filter(emails):
    # Batch Stage 1 — parallel API calls
    results = filter_chain.batch(
        [{"sender": e["sender"], "subject": e["subject"],
          "body_preview": e["body"][:500]} for e in emails],
        config={"max_concurrency": 5}
    )
    important = [e for e, r in zip(emails, results) if r["category"] == "important"]

    # Stage 2 on important only
    deep_results = deep_chain.batch(
        [{"sender": e["sender"], "subject": e["subject"],
          "body_preview": e["body"][:500]} for e in important],
        config={"max_concurrency": 5}
    )
    return [{"email": e, "classification": r} for e, r in zip(important, deep_results)]
```

## Key LCEL Concepts

**`|` pipe operator** — composes Runnables left to right:
`PromptTemplate | ChatAnthropic | JsonOutputParser`
Each step transforms the data and passes it to the next.

**`.batch()`** — runs the same chain on multiple inputs in parallel (async under
the hood via `asyncio.gather`). Returns results in the same order as inputs.
Cap concurrency with `config={"max_concurrency": N}` to avoid rate limits.

**`.ainvoke()`** — async version of `.invoke()`. Used inside `.batch()` internally.
Yields control while waiting on network I/O — this is where the parallelism comes from.

## Multi-User Handling

One script, multiple inboxes:

```python
FAMILY = [
    {"name": "alex",  "gmail": "alex@example.com", "session_db": "..."},
    {"name": "wife",  "gmail": "wife@gmail.com",       "session_db": "..."},
    {"name": "kids",  "gmail": "kids@gmail.com",       "session_db": "..."},
]

async def poll_all():
    await asyncio.gather(*[poll_member(m) for m in FAMILY])
```

Each member's results are written to their own NanoClaw `inbound.db`.
No crossover — Alex never sees Wife's emails and vice versa.

## Handoff to NanoClaw

After filtering, the script writes to the session's `inbound.db`:

```python
conn.execute("""
    INSERT INTO messages_in (seq, role, content, created_at)
    VALUES (?, 'system', ?, ?)
""", (next_odd_seq(conn), json.dumps(payload), datetime.utcnow().isoformat()))
```

Note: NanoClaw container uses **odd** seq numbers. Host uses even. This parity
is load-bearing — do not use even seq numbers from the Python script.

## Cost

Claude Haiku (~$0.80/million input tokens) keeps costs very low.
Estimated: $1-3/month for a typical family inbox load.
Body is truncated to 500 chars for classification — saves tokens, still accurate.
