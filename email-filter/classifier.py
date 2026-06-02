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
