# Gmail / Email-Monitor Integration Issues & Fixes

> Every headache hit wiring the email monitor end-to-end — Gmail access, the
> classifier, the agent, the scheduler — and exactly how each was fixed. The
> setup-time problems (OAuth, Docker, WSL) live in [[windows-setup-issues]];
> this page is the *runtime / integration* fights.

**Last updated:** 2026-06-03
**Related:** [[mcp]], [[langchain-filter]], [[onecli]], [[nanoclaw]], [[email-classification]], [[decisions]]

## Context

Getting "notify me on Telegram about important new email" actually *working* —
not just wired — surfaced a chain of problems across every layer: the Gmail
credential path, the MCP transport, the local LLM's speed, the NanoClaw poll
loop, and (most of all) the agent's unreliability as an orchestrator. Roughly in
the order we hit them.

The single biggest lesson is at the bottom (#10) and shaped the final design:
**keep judgment in the LLM, but move orchestration into code.**

---

## 1. Classifier unreachable from a cold container (OneCLI proxy)

**Symptom:** On a freshly-spawned container the agent's `classify_emails` tool
failed; the agent then silently judged importance itself.

**Cause:** The classifier is an SSE MCP server on `host.docker.internal:8765`.
The container's `HTTPS_PROXY` points at the OneCLI gateway, which tried to
intercept the connection to the host and failed.

**Fix:** Set `NO_PROXY=host.docker.internal,localhost,127.0.0.1` for the
container so the classifier connection bypasses the proxy (Gmail/Anthropic still
go *through* it). `src/container-runner.ts`.

**Lesson:** There was **no coded fallback** to "use the LLM directly" — the agent
just improvised when its tool errored. That improvisation looks like graceful
degradation but is the same unreliability that caused #6. A real fallback is an
explicit branch you control (e.g. LangChain `.with_fallbacks([...])`), not the
model quietly doing something reasonable-ish.

---

## 2. MCP-over-SSE classify call hangs forever on slow Ollama

**Symptom:** A check would freeze. The container stayed "Up" but did nothing for
15+ minutes; heartbeat frozen; no Telegram reply ever arrived.

**Cause:** On local Ollama a big batch took ~15 min to classify. The MCP **SSE
connection dropped mid-call** (idle/timeout). The classifier finished and pushed
the result onto a dead stream → the result was lost → the agent SDK hung forever
waiting for a `tool_result` that never came. (Diagnosed via the OneCLI MITM log:
last `/v1/messages` to Anthropic *before* the freeze, SSE reconnect ~17 min
later; classifier log showed the calls completing into the void.)

**Fix (immediate):** Bound every classify call to a small batch so it always
finishes well within the connection's lifetime. **Fix (root):** stop routing the
classify through the agent's open MCP-over-SSE turn at all — the deterministic
script calls a plain HTTP `/classify` endpoint instead (see #10).

**Lesson:** Long-running MCP-over-SSE tool calls are fragile. Keep tool calls
short, or use a request/response transport. "It's just slow" was actually a
correctness bug.

---

## 3. Stale `processing_ack` poison loop after a force-kill

**Symptom:** After killing a stuck container, **every** new container the host
spawned was instantly killed with `reason="claim-stuck"`, in a ~60s loop. The
monitor was completely dead.

**Cause:** A killed container left its message claimed as `status='processing'`
in `processing_ack`. The host-sweep's stale-claim detector saw the orphaned
claim, killed each new spawn, and reset the message with backoff — forever.
(`processing_ack` lives in **`outbound.db`**, despite what some docs imply.)

**Fix:** Stop the host, set the stuck `processing` row to `completed`, and retire
the orphaned message (`status='completed', trigger=0`) so it won't re-fire.
Then restart.

**Lesson:** **Do not force-kill a slow-but-still-progressing run** — let it
finish. If you must kill, clean up the claim afterward or you create the poison
loop. (Check Ollama's `ollama ps` keep-alive countdown to tell "still working"
from "actually hung.")

---

## 4. Ollama `qwen3:8b` was painfully slow (~60s/email)

**Symptom:** Each email took ~1 minute to classify; any real batch took many
minutes.

**Cause:** Two things compounding: (a) `qwen3:8b` is a **reasoning model** — it
emits a long hidden `<think>…</think>` monologue before the JSON answer, even for
a trivial label; (b) it ran **43% CPU / 57% GPU** (model didn't fully fit in
VRAM), so CPU token latency dominated.

**Fix:** Disable the thinking phase — `ChatOllama(..., reasoning=False)` (maps to
Ollama's `think: false`). `email-filter/classifier.py`. Dropped to **~7s/email**
(verified in isolation: 3 emails in ~20s).

**Lesson:** For a simple labelling task, a reasoning model's monologue is pure
overhead. Match the model behaviour to the task. (Claude Haiku would be ~instant
but is paid; chose to stay on free local Ollama.)

---

## 5. Classifier silently ran on Haiku instead of Ollama

**Symptom:** A run that "should" have been slow Ollama was instant, with calls to
`api.anthropic.com` and zero calls to `127.0.0.1:11434`.

**Cause:** `ANTHROPIC_API_KEY` was set in `.env`, so `build_chains()` picked
`ChatAnthropic` (Haiku) over Ollama. Also: `load_dotenv()` does **not** override a
variable already present in the process environment, so an empty `.env` value
won't undo a system-level one.

**Fix:** To force Ollama, clear the var *for the classifier process* before
launch: `$env:ANTHROPIC_API_KEY = ""` then start `server.py`. Confirm via the
startup banner ("falling back to Ollama model: qwen3:8b") and by watching which
host the classify calls hit.

**Lesson:** Always confirm *which* model is actually serving — `.env` + ambient
env can flip it under you.

---

## 6. The agent would not follow the procedure (prompt adherence)

**Symptom (repeated, three forms):**
1. Given a step-by-step playbook, the agent classified the **whole inbox**, made
   multiple `classify_emails` calls, and **never applied the dedup label**.
2. Told to "run the drain script," it instead reached for the `classify_emails`
   MCP tool and wrote a freeform summary.
3. With the email tools removed, it replied **"Gmail tools are disconnected"**
   instead of running the script.

**Cause:** LLM agents improvise. Even explicit "Hard rules: at most 3 emails,
exactly one call" and a fresh session didn't bind it. Whenever a tool was present
it reached for it; when the prompt was vague ("check my inbox") it rationalised.

**Fix:** Three moves, together:
- Move the entire procedure into a deterministic script (`check_inbox.ts`, #10).
- **Remove the competing tools** — no `gmail` / `classify_emails` MCP servers in
  `container.json` (`mcpServers: {}`), so there's nothing to reach for.
- Give the agent an **explicit one-line command** to run, not a procedure to
  follow: `bun /workspace/agent/check_inbox.ts`.

**Lesson:** Don't make an LLM a state machine. It's reliable at *judgment* ("is
this important?", "phrase this alert") and *running an explicit command*, and
unreliable at executing a fixed multi-step procedure. Put the procedure in code.

---

## 7. Warm-container poll-loop wedge — `/clear` (and any handoff) deadlocks

**Symptom:** After the agent replied once, a warm container went **deaf** — a
later `/clear` (or message) was never processed; heartbeat frozen; only a
container kill recovered it.

**Cause:** The interactive query is kept **open** after a reply (cheap follow-up
pushes), so the main loop is parked in `await processQuery`. New chat messages
get *pushed* into that open query — but `/clear` is deliberately excluded from
the push path (it must reset the continuation, which only the main loop does),
and **nothing ended the query for it**. So `/clear` sat pending forever while the
main loop stayed parked. The frozen heartbeat was a side effect: an idle open
query emits no events, and only events touched the heartbeat.

**Fix:** In the poll interval, when a `/clear` (or a scheduled task) is pending,
**end the open query** so the main loop regains control and handles it — same
mechanism tasks already used. Also `touchHeartbeat()` in the poll interval so a
healthy idle container doesn't look dead. `container/agent-runner/src/poll-loop.ts`
(generalised `endedForTask` → `endedForHandoff`).

**Lesson:** If you keep a turn open for pushes, every kind of message that the
*pusher* can't handle must have a path to **end the turn** and hand control back.

---

## 8. Calling Gmail from container code (no `gmail-mcp`)

**Symptom:** `check_inbox.ts` needs Gmail, but we removed the `gmail` MCP server.

**Fix:** Call the Gmail REST API directly from the container script and let
OneCLI inject the token:
- `fetch("https://gmail.googleapis.com/gmail/v1/users/me/…", { headers: { Authorization: "Bearer onecli-managed" }, proxy: HTTPS_PROXY, tls: { ca: <NODE_EXTRA_CA_CERTS> } })`.
- OneCLI matches the host pattern (`gmail.googleapis.com`) and the per-agent auth
  token embedded in `HTTPS_PROXY`, then rewrites `Bearer onecli-managed` to the
  real token. No real credential ever touches the container.
- Bun's `fetch` needs the proxy + CA passed **explicitly** (`proxy`, `tls.ca`).

**Lesson:** The OneCLI proxy injection isn't tied to `gmail-mcp` — any in-container
HTTP client using the proxy + stub bearer gets the same injection. Credentials
stay out of the container regardless of who makes the call.

---

## 9. Gmail `newer_than:` has no hour granularity

**Symptom:** A "last 6 hours" window via `newer_than:6h` didn't work.

**Cause:** Gmail search `newer_than:` / `older_than:` only accept `d` / `m` / `y`
units — no hours.

**Fix:** Use `after:<epoch_seconds>` for sub-day windows:
`after:${Math.floor((Date.now() - 6*3600*1000)/1000)} -label:BooTuna/seen`.

**Lesson:** Gmail's relative date operators are coarse; use epoch `after:` for
precise windows. (Also: nested labels use `/`, e.g. `BooTuna/seen`.)

---

## 10. Requirement churn: "drain the backlog" vs "monitor new mail"

**Symptom:** We built a bounded, oldest-first **drain** that chewed through the
whole unread inbox 3-at-a-time, label-tracking each as processed — then hit a
100+ email backlog and realised it would take hours to surface anything recent.

**Cause:** The implicit requirement ("process the whole inbox") didn't match the
actual goal ("tell me about important *new* mail"). We engineered the wrong thing
thoroughly.

**Fix:** Pivot to a **windowed check**: look only at unread mail from the last N
hours (`after:<epoch>`), classify, notify, and keep a `BooTuna/seen` label purely
to dedup the overlap (6h window vs 5h schedule). Old mail is ignored on purpose.
`check_inbox.ts`.

**Lesson:** Pin the *actual* requirement before optimising. "Review everything"
and "monitor what's new" are completely different systems. Requirements can — and
should — change when the goal becomes clear.

---

## The through-line

Almost every fight above is one principle in different clothes:

> **Give the LLM judgment; give code the orchestration.**

- Classification (judgment) → LangChain + the model, behind a stable
  `/classify` HTTP contract.
- Search / window / dedup-label / batching (orchestration) → `check_inbox.ts`,
  deterministic, in code.
- The agent → runs one explicit command and relays the result; nothing more.

The moment we stopped asking the model to *be* the pipeline and let it *call* the
pipeline, the system became predictable.
