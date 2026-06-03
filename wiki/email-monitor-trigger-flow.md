# Email Monitor — Architecture: Agent Wake & Trigger Flow

> The **dynamic** side of the monitor: how a scheduled wake fires the agent, how
> we *make* the agent run the check, and how the 5-hour recurrence keeps itself
> going. For the static component map (who talks to whom) see [[architecture]];
> for why it ended up this shape see [[gmail-integration-issues]].

**Last updated:** 2026-06-03
**Related:** [[architecture]], [[nanoclaw]], [[gmail-integration-issues]], [[email-classification]]

## The one-paragraph version

A recurring **scheduled task** lives as a row in the session's `inbound.db`. The
host's 60-second **sweep** notices when it's due and **wakes the agent container**.
The agent starts a **fresh session**, reads a task prompt that is an **explicit
command**, and runs that command with its **Bash tool**: `bun check_inbox.ts`.
The script does all the real work and the agent relays the result to Telegram.
After the task completes, the sweep **clones the next occurrence** for the next
5-hour slot. No persistent timer — just a self-replacing chain of one-shot rows.

---

## 1. How the schedule is stored

The schedule is a single `messages_in` row of `kind='task'` (in the session's
`inbound.db`), created by `insertTask()` (`src/modules/scheduling/db.ts`):

| Field | Value | Why |
|------|-------|-----|
| `kind` | `task` | Marks it as a scheduled wake, not a chat message |
| `recurrence` | `0 */5 * * *` | Cron — fires at 00/05/10/15/20:00 (in `Asia/Singapore`) |
| `process_after` | next-fire timestamp (UTC) | The sweep only fires it once now ≥ this |
| `trigger` | `1` (column default) | Required for the due-check to pick it up |
| `series_id` | = the row id | Ties every occurrence of this schedule together |
| `platform_id`/`channel_type` | `telegram:<id>` / `telegram` | Routes the agent's reply back to the Telegram DM |
| `content` | `{"prompt": "<explicit command>", "script": null}` | The instruction the agent receives on wake |
| `seq` | next **even** number | Host writes even seq; container writes odd (parity invariant) |

It was inserted **directly** (deterministic) rather than via the agent's
`schedule_task` tool, so setup doesn't depend on the agent behaving.

## 2. The wake — host sweep → container

Every 60s, `src/host-sweep.ts` runs a sweep that (in order):

1. **Syncs `processing_ack`** — pulls the container's completion claims (from
   `outbound.db`) into `messages_in` status.
2. **Detects due messages** — `countDueMessages` (`src/db/session-db.ts`) selects
   rows where `trigger = 1 AND process_after <= now`. Our task matches once due.
3. **Wakes the session** — logs `Waking container for due messages` and spawns the
   agent container (`src/container-runner.ts`) if one isn't already running.
4. **Advances recurrence** — see §5.

So the "schedule" is really: *a due row + a polling sweep that notices it.*

## 3. Fresh session per task (why the agent reads its playbook anew)

When the container's poll loop (`container/agent-runner/src/poll-loop.ts`) picks up
the batch, it checks `isTaskBatch = keep.every(m => m.kind === 'task')`. For a task
batch it calls the provider with **`continuation: undefined`** — a **fresh
session**, not the resumed interactive chat:

```ts
const isTaskBatch = keep.length > 0 && keep.every((m) => m.kind === 'task');
const query = provider.query({ prompt, continuation: isTaskBatch ? undefined : continuation, ... });
```

Why it matters here: a fresh session **re-reads `CLAUDE.local.md`** and carries no
stale chat context. Earlier, resuming the long interactive session dragged in an
irrelevant transcript and made the agent ignore the routine (see
[[gmail-integration-issues]] #6). The task's session id is also **not persisted**,
so the next real chat message still resumes the human conversation.

## 4. The method: how we MAKE the agent run the trigger

This is the crux. Waking the agent isn't enough — it has to actually run the
script. We force that with **two** things working together:

**(a) The task prompt is an explicit command, not a goal.** The `content.prompt`
is literally:

> *"Scheduled email check. Run this exact command with the Bash tool:
> `bun /workspace/agent/check_inbox.ts`. … For each item in its `important` array,
> send me one Telegram message … If `important` is empty, send nothing."*

Agents execute literal commands reliably; they *rationalise* vague goals. A prompt
like "check my inbox" previously let the agent improvise (it once replied "tools
disconnected" instead of acting). A command leaves no room for that.

**(b) There are no competing tools.** The agent group's `container.json` has
`"mcpServers": {}` — **no `gmail`, no `classify_emails`**. The only way the agent
can touch email is `Bash → bun check_inbox.ts`. With nothing else to reach for,
the path of least resistance *is* the script. (`Bash` is allow-listed with
`permissionMode: 'bypassPermissions'`, and `bun` + the script exist in the
container.)

So the trigger is mechanically: the agent issues `Bash("bun /workspace/agent/check_inbox.ts")`.
That's the same command we run by hand via `docker exec` — the agent is just the thing typing it.

```
scheduled task fires ─▶ fresh session ─▶ prompt = "run `bun check_inbox.ts`"
                                              │
                                   agent's Bash tool ─▶ bun /workspace/agent/check_inbox.ts
```

**Residual risk + fallback.** This still relies on the agent *choosing* to run the
command. One verified firing succeeded; it's not proven over many. If a future run
ever narrates instead of executing, the escalation is to make `check_inbox.ts`
**self-deliver** (write the notification to `outbound.db` directly) so delivery no
longer depends on the agent at all — or move the trigger into a pre-task `script`
hook that runs the check with `wakeAgent=false` (no LLM in the loop). See plan v2.

## 5. Recurrence — the self-replacing chain

There is **no long-lived timer**. Recurrence is handled by `handleRecurrence()`
(`src/modules/scheduling/recurrence.ts`), called from the sweep:

1. Find `messages_in` rows that are `completed` **and** still have a `recurrence`.
2. Parse the cron **in `Asia/Singapore`** (`cron-parser`), compute the next run.
3. `insertRecurrence()` — insert a fresh `pending` row for that next time, copying
   `series_id` forward.
4. `clearRecurrence()` — null out `recurrence` on the just-completed row so it's
   never cloned again.

So each occurrence is a one-shot row that, on completion, spawns its successor. The
successor is **future-dated**, which is what prevents a past-due row from re-firing
every 60s. (A past-due `pending` task with `trigger=1` *would* re-fire each sweep —
that's exactly why the advance-and-future-date step is load-bearing.)

## 6. Verified end-to-end trace (2026-06-03)

The flow above, observed live:

```
20:14  insert recurring task (process_after = now-1m, cron 0 */5 * * *)
20:15  sweep → "Waking container for due messages" → spawn container …930170
20:15  poll-loop: "Processing 1 message(s), kinds: task [fresh session]"
20:15  agent → Bash("bun /workspace/agent/check_inbox.ts") → classifier /classify hit
20:16  Result: "Checked 7 unread emails, found 1 important — notification sent"
20:16  Message delivered → Telegram (msgs 67, 68)
20:16  sweep → original task → completed; recurrence advanced →
       new pending row @ 2026-03-06T16:00:00Z (00:00 SGT), no re-fire
```

## 7. Failure modes seen (and their guards)

- **Agent rationalises instead of running the script** → explicit-command prompt +
  `mcpServers: {}`; ultimate guard = script self-delivery. ([[gmail-integration-issues]] #6)
- **Warm container runs *old* code** — Bun loads the source at process start, so a
  long-lived container won't pick up a `poll-loop.ts`/`check_inbox.ts` edit. Kill it
  so the next fire spawns fresh.
- **Poll-loop wedge** — a warm container could go deaf to `/clear`; fixed by ending
  the open query on handoff + heart-beating in the poll interval. ([[gmail-integration-issues]] #7)
- **Stale `processing_ack` poison loop** — force-killing a busy container leaves a
  claim that makes the sweep kill every new spawn; clear the claim. ([[gmail-integration-issues]] #3)
- **Services down** — the sweep can't fire if the host/Ollama/classifier/OneCLI/Docker
  aren't up. After reboot: `scripts/start-all.ps1`; confirm the classifier logs
  "falling back to Ollama". ([[running]])

## 8. Code map

| Concern | File |
|--------|------|
| Sweep: due-detection, wake, recurrence hook | `src/host-sweep.ts` |
| Due query (`trigger=1 AND process_after<=now`) | `src/db/session-db.ts` (`countDueMessages`) |
| Task insert / cancel / update | `src/modules/scheduling/db.ts` |
| Next-fire + clone (cron in TZ) | `src/modules/scheduling/recurrence.ts` |
| Container spawn on wake | `src/container-runner.ts` |
| Fresh-session-per-task + the relay | `container/agent-runner/src/poll-loop.ts` |
| The work the agent triggers | `groups/dm-with-alex-emailmonitor/check_inbox.ts` |
| The agent's playbook | `groups/dm-with-alex-emailmonitor/CLAUDE.local.md` |
| No competing tools | `groups/dm-with-alex-emailmonitor/container.json` (`mcpServers: {}`) |
