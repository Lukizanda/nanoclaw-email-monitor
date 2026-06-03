# LangChain Classifier

> Python LangChain service that classifies emails for importance. Pure judgment:
> emails in → important emails out. Reached over a plain HTTP endpoint.

**Last updated:** 2026-06-03
**Related:** [[architecture]], [[mcp]], [[email-classification]], [[decisions]], [[gmail-integration-issues]]

## Role in the System

The classifier runs as an always-on Python service on the host
(`email-filter/server.py`, port 8765). It does **one thing**: take a list of
emails and return the ones that matter, tagged with action type / summary /
urgency. It is called by **`check_inbox.ts`** over plain HTTP:

```
check_inbox.ts  ──POST /classify {emails:[...]}──▶  server.py → classifier.py (LCEL) → Ollama
                ◀──────── {important:[...]} ────────
```

What this service **does not** do (those live in `check_inbox.ts` — see
[[architecture]]): fetch Gmail, window by time, label, dedup, schedule, or write
any database. It has no knowledge of Gmail, NanoClaw, or Telegram. That clean
boundary is the point — swap the model or rewrite the orchestrator and the other
side doesn't care.

(It also still exposes a `classify_emails` **MCP/SSE** tool, but nothing calls it
anymore — the live path is HTTP `/classify`. See [[mcp]].)

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

Also produces a 2-3 sentence `summary` and an `urgency` level (high/medium/low).

## LCEL Implementation

The default model is **local Ollama** with reasoning disabled (a reasoning
model's hidden monologue is pure overhead for a labelling task — see
[[gmail-integration-issues]] #4). Claude Haiku is an optional swap if
`ANTHROPIC_API_KEY` is set.

```python
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

model = ChatOllama(model="qwen3:8b", format="json", temperature=0,
                   reasoning=False)          # think:false → ~7s/email, not ~60s
# or: ChatAnthropic(model="claude-haiku-4-5-...") when ANTHROPIC_API_KEY is set

stage1 = STAGE1_PROMPT | model | JsonOutputParser()   # coarse filter
stage2 = STAGE2_PROMPT | model | JsonOutputParser()   # deep classify

def run_pipeline(emails, stage1, stage2):
    s1 = stage1.batch([{...} for e in emails], config={"max_concurrency": 5})
    important = [e for e, r in zip(emails, s1) if r["category"] == "important"]
    if not important:
        return []
    s2 = stage2.batch([{...} for e in important], config={"max_concurrency": 5})
    return [{**e, **r} for e, r in zip(important, s2)]   # action_type/summary/urgency
```

`run_pipeline()` is what both `/classify` (HTTP) and the legacy `classify_emails`
(MCP) call.

## Key LCEL Concepts

**`|` pipe operator** — composes Runnables left to right:
`PromptTemplate | model | JsonOutputParser`. Each step transforms the data and
passes it on. New behaviour = slot in another Runnable (e.g. a `RunnableBranch`
stage-3 extractor, or `.with_fallbacks([...])` for Ollama→Haiku).

**`.batch()`** — runs the chain on many inputs concurrently. Returns results in
input order. Cap with `config={"max_concurrency": N}`. (Note: Ollama serialises
requests on one GPU by default, so the real win is per-call speed, not parallelism.)

**`.ainvoke()`** — async `.invoke()`, used inside `.batch()`; yields on network I/O.

## Cost

**Free by default** — local Ollama, no API spend. The trade-off is speed
(~7s/email with `reasoning=False`; the model runs partly on CPU). Setting
`ANTHROPIC_API_KEY` switches to Claude Haiku — near-instant, ~$1-3/month at a
typical inbox load, but it bills the Anthropic API (separate from a Claude Max
plan). Body is truncated to ~500 chars before classification.

## Extending the chain

Because every stage is a Runnable, you grow capability by adding runnables, not
rewriting. Realistic additions: a `RunnableBranch` stage-3 that extracts
structured detail per action_type (amount/due-date for payments, time/place for
meetings), a rules pre-filter that short-circuits VIP senders before the LLM, or
`.with_fallbacks([ChatAnthropic(...)])` so an Ollama failure transparently retries
on Haiku. The HTTP contract (`/classify`) stays identical, so `check_inbox.ts`
never changes.
