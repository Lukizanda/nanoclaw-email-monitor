# Telegram Messaging Flow

> How messages get from a Telegram chat to the agent and back — and why it works
> on a home desktop with no public IP, port forwarding, or firewall changes.

**Last updated:** 2026-06-03
**Related:** [[architecture]], [[nanoclaw]], [[running]]

## The key idea: the desktop calls *out*, nothing connects *in*

NanoClaw does **not** listen for Telegram to connect to your desktop. Instead,
your desktop continuously reaches *out* to Telegram's servers — like a browser
making requests. This is **long polling**.

From the startup logs:
```
[chat-sdk:telegram] Telegram webhook reset { dropPendingUpdates: false }
[chat-sdk:telegram] Telegram polling started { limit: 100, timeout: 30 }
```

1. NanoClaw opens an **outbound** HTTPS request to Telegram's `getUpdates` API —
   "any new messages for this bot?" — and holds it open ~30 seconds.
2. When you DM the bot, Telegram queues the message and returns it on that open
   request.
3. The request closes; NanoClaw immediately opens another. Repeat forever.

Because the desktop is the *client* (it initiates every connection), Telegram
never needs your desktop's address. This is why the whole thing runs behind a
home router / NAT / firewall with **zero network configuration**.

## Full round trip

```
You DM the bot
      │  (Telegram holds the message)
      ▼
NanoClaw's open getUpdates poll returns it          ← OUTBOUND from desktop
      │
      ▼
Router: messaging group → agent group → session → inbound.db
      │
      ▼
Docker container wakes; agent runs; writes reply → outbound.db
      │
      ▼
Delivery poll reads outbound.db → Telegram sendMessage API   ← OUTBOUND from desktop
      │
      ▼
Reply appears in your Telegram chat
```

**Both directions are outbound HTTP from the desktop to Telegram's API.**
Nothing ever connects *into* the machine.

## How it knows where to send replies

Two identifiers do the work:

| Identifier | Where it lives | Role |
|-----------|----------------|------|
| **Bot token** | `.env` (`TELEGRAM_BOT_TOKEN`) | Authenticates *which bot* on every Telegram API call |
| **Chat ID** | `data/v2.db` (`telegram:<id>`, e.g. `telegram:1234567890`) | *Where* to deliver replies — the `sendMessage` target |

The chat ID was captured during **pairing** (when you sent the 4-digit code to
the bot) and stored as a messaging group wired to the agent group. Every reply's
`sendMessage` call targets that chat ID. See [[nanoclaw]] for the entity model
(user → messaging group → agent group → session).

## Polling vs webhooks

NanoClaw started a generic webhook receiver on **port 3000**
(`Webhook server started port=3000 adapters=["telegram"]`), but Telegram here
uses **polling**, not webhooks. In fact the `Telegram webhook reset` line
*deletes* any registered Telegram webhook — Telegram's API won't let you use
`getUpdates` (polling) while a webhook is set. So **port 3000 is not part of the
Telegram flow** in this install; it's there for channels that push via webhooks.

| Mode | Who initiates | Needs public endpoint? | Used here? |
|------|--------------|------------------------|-----------|
| **Long polling** | Desktop → Telegram | No | ✅ yes |
| **Webhook** | Telegram → your endpoint | Yes (public URL or tunnel) | no |

## Why polling is the right choice here

- **No networking setup** — works behind NAT/firewall on a home machine
- **No public exposure** — nothing inbound to secure
- **Survives IP changes** — the desktop's address never matters

Trade-offs (only relevant at scale): polling has slightly higher latency than
webhooks and holds an open connection per bot. If you ever ran many bots or
needed minimal latency, you'd switch to webhook mode — but that requires a public
HTTPS endpoint (or a tunnel like ngrok/Cloudflare Tunnel), which polling avoids
entirely. For a personal/family monitor, polling is strictly simpler and fine.
