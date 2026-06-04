from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from typing import Any

STAGE1_PROMPT = PromptTemplate.from_template("""
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

Respond with JSON only. No markdown, no explanation.
{{"category": "junk|ad|newsletter|important", "reason": "one sentence"}}
""")

STAGE2_PROMPT = PromptTemplate.from_template("""
This email passed the importance filter. Classify what action is needed.

Action types:
- "payment"  : invoice, billing, overdue, financial action required
- "meeting"  : calendar invite, scheduling request, needs a response
- "job"      : interview, recruiter, offer, HR, contract
- "reply"    : personal email requiring a direct response
- "urgent"   : explicit deadline, ASAP, time-sensitive language

Email:
From: {sender}
Subject: {subject}
Body preview: {body_preview}

Respond with JSON only. No markdown, no explanation.
{{"action_type": "payment|meeting|job|reply|urgent", "summary": "2-3 sentences describing what action is needed", "urgency": "high|medium|low"}}
""")


def build_chains(ollama_model: str = "qwen3:8b", anthropic_api_key: str | None = None):
    """
    Build Stage 1 + Stage 2 LCEL chains.

    Uses Claude Haiku by default (better accuracy). Falls back to Ollama
    if no ANTHROPIC_API_KEY is set (free, local, no key needed).
    """
    if anthropic_api_key:
        model = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=anthropic_api_key,
            max_tokens=256,
        )
    else:
        model = ChatOllama(
            model=ollama_model,
            format="json",
            temperature=0,
            # qwen3 is a reasoning model: by default it emits a long hidden
            # <think>…</think> monologue before the JSON answer, which on a
            # partial-CPU 8B model costs ~30-60s/email. reasoning=False maps to
            # Ollama's `think: false` — skip the monologue and answer directly.
            # Classification is a simple labelling task that doesn't need it.
            reasoning=False,
        )

    stage1 = STAGE1_PROMPT | model | JsonOutputParser()
    stage2 = STAGE2_PROMPT | model | JsonOutputParser()
    return stage1, stage2


def run_pipeline(
    emails: list[dict[str, str]],
    stage1_chain,
    stage2_chain,
) -> list[dict[str, Any]]:
    if not emails:
        return []

    inputs = [
        {
            "sender": e.get("sender", ""),
            "subject": e.get("subject", ""),
            "body_preview": e.get("body_preview", "")[:500],
        }
        for e in emails
    ]

    # Stage 1 — batch classify all emails in parallel
    stage1_results = stage1_chain.batch(inputs, config={"max_concurrency": 5})

    important_pairs = [
        (email, result)
        for email, result in zip(emails, stage1_results)
        if result.get("category") == "important"
    ]

    if not important_pairs:
        return []

    important_emails = [email for email, _ in important_pairs]

    # Stage 2 — deep classify important emails only
    stage2_inputs = [
        {
            "sender": e.get("sender", ""),
            "subject": e.get("subject", ""),
            "body_preview": e.get("body_preview", "")[:500],
        }
        for e in important_emails
    ]
    stage2_results = stage2_chain.batch(stage2_inputs, config={"max_concurrency": 5})

    return [
        {
            **email,
            "action_type": result.get("action_type", "reply"),
            "summary": result.get("summary", ""),
            "urgency": result.get("urgency", "medium"),
        }
        for email, result in zip(important_emails, stage2_results)
    ]


# ----------------------------------------------------------------------------
# ALTERNATIVE: the same filter-then-enrich expressed as ONE composed chain.
#
# This is what we discussed — the two-stage split is NOT required for the
# compute saving. RunnableBranch routes each email *inside* LCEL: Stage 2 only
# runs when Stage 1 said "important", so junk/ad/newsletter short-circuit and
# never hit the expensive deep-classify call — identical saving to the manual
# `if category == "important"` filter in run_pipeline above.
#
# We DON'T use this version. Trade-offs vs. the two-chain + Python-glue approach:
#   + One declarative pipeline; pipelines per-email (an important email can start
#     Stage 2 while another's Stage 1 is still running — no hard barrier).
#   + "Pure LCEL" — easy to slot in a Stage 3 with another RunnableBranch.
#   - The "27 dropped, 3 important" funnel is buried inside chain execution; you
#     need callbacks/instrumentation to observe it, vs. a plain list you can count.
#   - Can't cleanly time "all of Stage 1" vs "all of Stage 2" — they interleave.
#   - More LCEL machinery (assign / RunnableBranch / passthrough) to read.
#
# Needs these extra imports at the top of the file:
#   from langchain_core.runnables import RunnableBranch, RunnablePassthrough
#
# def build_single_chain(ollama_model: str = "qwen3:8b", anthropic_api_key: str | None = None):
#     # Same model selection as build_chains(); both prompts share one `model`.
#     stage1, stage2 = build_chains(ollama_model, anthropic_api_key)
#
#     def is_important(x: dict) -> bool:
#         return x.get("stage1", {}).get("category") == "important"
#
#     # Input to the chain is one email's fields: {sender, subject, body_preview}.
#     # .assign() RUNS a runnable on the whole input dict and ADDS its result under
#     # the given key (without dropping the original fields), so Stage 2's prompt
#     # can still read sender/subject/body_preview after Stage 1 has run.
#     classify_chain = (
#         RunnablePassthrough.assign(stage1=stage1)           # -> {..fields.., stage1: {category, reason}}
#         | RunnableBranch(
#             (is_important, RunnablePassthrough.assign(stage2=stage2)),  # important -> + {stage2: {...}}
#             RunnablePassthrough(),                          # else: stop, no Stage 2 call
#         )
#     )
#     return classify_chain
#
# def run_pipeline_single(emails: list[dict[str, str]], classify_chain) -> list[dict[str, Any]]:
#     if not emails:
#         return []
#
#     inputs = [
#         {
#             "sender": e.get("sender", ""),
#             "subject": e.get("subject", ""),
#             "body_preview": e.get("body_preview", "")[:500],
#         }
#         for e in emails
#     ]
#
#     # ONE blocking .batch() does both stages; junk short-circuits past Stage 2.
#     results = classify_chain.batch(inputs, config={"max_concurrency": 5})
#
#     # Keep only emails that reached Stage 2 (i.e. were classified important),
#     # and zip back to the ORIGINAL email dicts to preserve any extra fields.
#     out = []
#     for email, r in zip(emails, results):
#         s2 = r.get("stage2")
#         if not s2:
#             continue
#         out.append(
#             {
#                 **email,
#                 "action_type": s2.get("action_type", "reply"),
#                 "summary": s2.get("summary", ""),
#                 "urgency": s2.get("urgency", "medium"),
#             }
#         )
#     return out
# ----------------------------------------------------------------------------
