/**
 * ensure-schedule.ts — make the email-monitor's recurring check durable.
 *
 * The schedule is a single `kind=task` row in a session's `inbound.db`. It is
 * NOT stored in code or the central DB, so if the session is ever rebuilt
 * (new session id → new DB files) or `data/` is wiped, the schedule silently
 * disappears. This script re-seeds it into whatever the agent group's CURRENT
 * active session is — so the schedule survives session rebuilds.
 *
 * Idempotent: if a recurring check already exists in the current session, it
 * does nothing. Safe to run on every startup (wired into start-all.ps1).
 *
 *   pnpm exec tsx scripts/ensure-schedule.ts
 *
 * Tunables via env: SCHEDULE_AGENT_FOLDER, SCHEDULE_CRON.
 */
import path from 'node:path';

import { initDb, getDb } from '../src/db/connection.js';
import { findSessionByAgentGroup } from '../src/db/sessions.js';
import { insertTask } from '../src/modules/scheduling/db.js';
import { openInboundDb } from '../src/session-manager.js';
import { DATA_DIR, TIMEZONE } from '../src/config.js';

const AGENT_FOLDER = process.env.SCHEDULE_AGENT_FOLDER ?? 'dm-with-alex-emailmonitor';
const CRON = process.env.SCHEDULE_CRON ?? '0 */5 * * *';
const MARKER = 'check_inbox.ts'; // how we recognise our own recurring task
const PROMPT =
  'Scheduled email check. Run this exact command with the Bash tool:\n' +
  '`bun /workspace/agent/check_inbox.ts`\n' +
  'It prints one JSON object on stdout. For each item in its `important` array, ' +
  'send me ONE Telegram message in your notification format (batch them into a ' +
  'single message). If `important` is empty, send nothing. Do not search or ' +
  'classify email yourself — the script does everything.';

const log = (m: string) => console.error(`[ensure-schedule] ${m}`);

async function main() {
  initDb(path.join(DATA_DIR, 'v2.db'));
  const db = getDb();

  // The central DB must be initialised (host has run at least once).
  let ag: { id: string; name: string } | undefined;
  try {
    ag = db.prepare('SELECT id, name FROM agent_groups WHERE folder = ?').get(AGENT_FOLDER) as
      | { id: string; name: string }
      | undefined;
  } catch {
    log('central DB not initialised yet (no agent_groups) — skipping');
    return;
  }
  if (!ag) {
    log(`no agent group with folder '${AGENT_FOLDER}' — nothing to seed`);
    return;
  }

  const session = findSessionByAgentGroup(ag.id);
  if (!session) {
    log(`no active session for ${ag.name} yet — will seed once one exists`);
    return;
  }

  const inb = openInboundDb(ag.id, session.id);
  inb.pragma('busy_timeout = 10000'); // tolerate the running host briefly holding the write lock

  // Idempotency: bail if a recurring check is already queued in this session.
  const existing = inb
    .prepare(
      "SELECT id FROM messages_in WHERE kind='task' AND recurrence IS NOT NULL " +
        "AND status IN ('pending','processing') AND content LIKE ?",
    )
    .get(`%${MARKER}%`) as { id: string } | undefined;
  if (existing) {
    log(`recurring check already present (${existing.id}) in session ${session.id} — nothing to do`);
    return;
  }

  // Route the agent's reply back to the session's messaging group (e.g. the Telegram DM).
  let platformId: string | null = null;
  let channelType: string | null = null;
  if (session.messaging_group_id) {
    const mg = db
      .prepare('SELECT channel_type, platform_id FROM messaging_groups WHERE id = ?')
      .get(session.messaging_group_id) as { channel_type: string; platform_id: string } | undefined;
    if (mg) {
      platformId = mg.platform_id;
      channelType = mg.channel_type;
    }
  }

  // Next fire at the next cron slot, interpreted in the configured timezone
  // (matches how handleRecurrence advances native recurrences).
  const { CronExpressionParser } = await import('cron-parser');
  const nextRun = CronExpressionParser.parse(CRON, { tz: TIMEZONE }).next().toISOString();

  const id = `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  insertTask(inb, {
    id,
    processAfter: nextRun,
    recurrence: CRON,
    platformId,
    channelType,
    threadId: session.thread_id ?? null,
    content: JSON.stringify({ prompt: PROMPT, script: null }),
  });
  log(
    `seeded recurring check ${id} into session ${session.id} ` +
      `(cron '${CRON}', next ${nextRun}, route ${platformId ?? 'none'})`,
  );
}

main().catch((e) => {
  log(`error: ${e instanceof Error ? e.stack ?? e.message : String(e)}`);
  process.exit(1);
});
