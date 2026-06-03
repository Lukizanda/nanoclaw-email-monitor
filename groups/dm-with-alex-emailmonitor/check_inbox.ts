#!/usr/bin/env bun
/**
 * check_inbox.ts — check recent mail for anything important.
 *
 * Runs INSIDE the agent container (where OneCLI injects the Gmail token via the
 * proxy). Deterministic, in code, so nothing is left to agent improvisation:
 *
 *   1. find UNREAD mail received in the last WINDOW_HOURS that we haven't
 *      already checked  (is:unread after:<epoch> -label:BooTuna/seen)
 *   2. classify it via the LangChain classifier (POST /classify, chunked <=15)
 *   3. label everything we looked at `BooTuna/seen` — pure dedup, so the next
 *      run never re-notifies the same email (the 6h window overlaps the 5h
 *      schedule by an hour on purpose, so nothing slips through a gap)
 *   4. print ONE JSON object: { checked, important[], window_hours }
 *
 * We do NOT drain a backlog. Mail older than the window is ignored on purpose —
 * the goal is "tell me about important NEW mail," not "review everything".
 */

const GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me";
const CLASSIFIER =
  process.env.CHECK_CLASSIFIER_URL ?? "http://host.docker.internal:8765/classify";
const LABEL_NAME = process.env.CHECK_LABEL ?? "BooTuna/seen";
const WINDOW_HOURS = parseFloat(process.env.CHECK_WINDOW_HOURS ?? "6");
const MAX_FETCH = parseInt(process.env.CHECK_MAX_FETCH ?? "50", 10);
const CLASSIFY_CHUNK = 15; // classifier caps a single call at 15
const PROXY = process.env.HTTPS_PROXY || process.env.https_proxy || undefined;

const log = (...a: unknown[]) => console.error("[check]", ...a);
const out = (obj: unknown) => console.log(JSON.stringify(obj));

const caPath = process.env.NODE_EXTRA_CA_CERTS;
let caText: string | undefined;

async function gmail(path: string, init: RequestInit = {}): Promise<any> {
  if (caText === undefined && caPath) {
    try {
      caText = await Bun.file(caPath).text();
    } catch {
      caText = "";
    }
  }
  const res = await fetch(GMAIL + path, {
    ...init,
    headers: {
      Authorization: "Bearer onecli-managed",
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    proxy: PROXY, // Gmail must traverse the OneCLI proxy for token injection
    tls: caText ? { ca: caText } : undefined,
  } as any);
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Gmail ${init.method ?? "GET"} ${path} -> ${res.status}: ${t.slice(0, 300)}`);
  }
  return res.status === 204 ? null : res.json();
}

async function ensureLabel(): Promise<string> {
  const data = await gmail("/labels");
  const found = (data.labels ?? []).find((l: any) => l.name === LABEL_NAME);
  if (found) return found.id;
  const created = await gmail("/labels", {
    method: "POST",
    body: JSON.stringify({
      name: LABEL_NAME,
      labelListVisibility: "labelShow",
      messageListVisibility: "show",
    }),
  });
  log("created label", LABEL_NAME, "->", created.id);
  return created.id;
}

async function classify(emails: any[]): Promise<any[]> {
  const important: any[] = [];
  for (let i = 0; i < emails.length; i += CLASSIFY_CHUNK) {
    const chunk = emails.slice(i, i + CLASSIFY_CHUNK);
    const res = await fetch(CLASSIFIER, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails: chunk }),
      proxy: PROXY,
    } as any);
    if (!res.ok) {
      throw new Error(`classifier -> ${res.status}: ${(await res.text()).slice(0, 300)}`);
    }
    const j = await res.json();
    important.push(...(j.important ?? []));
  }
  return important;
}

async function main() {
  const labelId = await ensureLabel();

  const afterEpoch = Math.floor((Date.now() - WINDOW_HOURS * 3600 * 1000) / 1000);
  const q = encodeURIComponent(`is:unread after:${afterEpoch} -label:${LABEL_NAME}`);
  const list = await gmail(`/messages?q=${q}&maxResults=${MAX_FETCH}`);
  const msgs: any[] = list.messages ?? [];
  log(`found ${msgs.length} unread in last ${WINDOW_HOURS}h not yet checked`);
  if (msgs.length === 0) {
    out({ checked: 0, important: [], window_hours: WINDOW_HOURS });
    return;
  }

  const ids: string[] = [];
  const emails: { sender: string; subject: string; body_preview: string }[] = [];
  for (const m of msgs) {
    const full = await gmail(
      `/messages/${m.id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From`,
    );
    const headers: any[] = full.payload?.headers ?? [];
    const h = (n: string) => headers.find((x) => x.name.toLowerCase() === n)?.value ?? "";
    emails.push({
      sender: h("from"),
      subject: h("subject"),
      body_preview: (full.snippet ?? "").slice(0, 500),
    });
    ids.push(m.id);
  }

  const important = await classify(emails);

  // Dedup marker so the next (overlapping) run never re-notifies these.
  await gmail(`/messages/batchModify`, {
    method: "POST",
    body: JSON.stringify({ ids, addLabelIds: [labelId] }),
  });
  log(`checked ${ids.length}, flagged ${important.length} important`);

  out({
    checked: ids.length,
    important: important.map((e: any) => ({
      sender: e.sender,
      subject: e.subject,
      action_type: e.action_type,
      summary: e.summary,
      urgency: e.urgency,
    })),
    window_hours: WINDOW_HOURS,
  });
}

main().catch((e) => {
  out({ error: String(e?.message ?? e) });
  process.exit(1);
});
