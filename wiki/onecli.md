# OneCLI

> Credential vault and API proxy for NanoClaw agent containers — agents make API
> calls through it without ever seeing raw credentials.

**Last updated:** 2026-06-04
**Related:** [[nanoclaw]], [[architecture]], [[decisions]], [[gmail-integration-issues]]

## What It Is

OneCLI is a locally-hosted credential gateway. It sits between agent containers
and external APIs, injecting the right credentials at request time. Agents never
hold tokens — they just make HTTP calls and OneCLI rewrites the Authorization
header on the wire.

```
Agent Container
    │  GET https://api.anthropic.com/v1/messages
    │  Authorization: Bearer placeholder
    ▼
OneCLI Gateway (port 10255)
    │  looks up secret for api.anthropic.com
    │  rewrites header: Bearer <real token>
    ▼
Anthropic API
```

## Architecture

OneCLI runs as two Docker containers managed by Docker Compose:

```
onecli          ← the gateway + API server (port 10254 UI, 10255 proxy)
onecli-postgres ← credential storage (PostgreSQL)
```

Data lives in Docker volumes (`pgdata`, `app-data`) — survives container restarts.
Compose file: `~/.onecli/docker-compose.yml`

## Starting and Stopping

```powershell
# Start (after PC restart)
.\scripts\start-all.ps1

# Or start OneCLI alone
docker compose -p onecli -f $env:USERPROFILE\.onecli\docker-compose.yml up -d

# Stop
docker compose -p onecli -f $env:USERPROFILE\.onecli\docker-compose.yml down
```

Web UI: `http://127.0.0.1:10254`

## CLI Commands

The CLI lives at `~/.local/bin/onecli` inside WSL. Run via:

```powershell
wsl -d Ubuntu -- bash -c "~/.local/bin/onecli <command>"
```

Common commands:

```bash
# List all secrets
onecli secrets list

# Register a new secret
onecli secrets create --name Anthropic --type anthropic \
  --value <token> --host-pattern api.anthropic.com

# List all agents
onecli agents list

# Set secret mode for an agent
onecli agents set-secret-mode --id <agent-id> --mode all

# See what secrets an agent has access to
onecli agents secrets --id <agent-id>
```

## Secret Modes — Critical Gotcha

When NanoClaw creates a new agent group for the first time, OneCLI defaults
to **selective** mode — the agent gets **no secrets**, even if the vault has
matching credentials.

**Symptom:** Container starts fine but gets `401 Unauthorized` from Anthropic
or other APIs.

**Fix:**
```bash
onecli agents list                                      # find the agent id
onecli agents set-secret-mode --id <id> --mode all     # grant all matching secrets
```

No container restart needed — the gateway looks up secrets per request.

Mode options:
- `selective` — default, nothing assigned, you assign manually
- `all` — any vault secret whose host pattern matches gets injected

## Our Secrets

| Secret name | Type | Host pattern | Used for |
|-------------|------|-------------|---------|
| Anthropic | anthropic | api.anthropic.com | Claude agent containers |
| Gmail | google-oauth | gmail.googleapis.com | `check_inbox.ts` REST calls (token injected at request time) |

Alex's Gmail token is registered and live — `check_inbox.ts` fetches the inbox
via REST through the OneCLI proxy (`Authorization: Bearer onecli-managed`, the
gateway swaps in the real token). Additional family members' tokens get added as
they're onboarded (Phase 7).

## How NanoClaw Uses OneCLI

`ONECLI_URL=http://127.0.0.1:10254` in `.env` tells NanoClaw where the gateway is.

When spawning a Docker container, `src/container-runner.ts` calls
`onecli.ensureAgent()` — this registers the agent with OneCLI so it gets
credentials injected. The container's `ANTHROPIC_BASE_URL` is set to the
OneCLI proxy endpoint so all API calls route through it.

## Approval Flows (Future)

OneCLI can require human sign-off before a credentialed action is executed.
Configure via the web UI at `http://127.0.0.1:10254`. When triggered, NanoClaw
routes the approval request to a Telegram DM (or whichever channel is configured).

Not set up yet — relevant for Phase 7 (reply drafting with approval flow).
