# Running & Startup Runbook

> What has to be running, in what order, how to start it, how to verify it, and
> how to debug a failed startup. Read this first when "nothing responds."

**Last updated:** 2026-06-03
**Related:** [[onecli]], [[mcp]], [[windows-setup-issues]], [[architecture]]

## The four services

The email monitor needs **four** things running on the host. They have a
dependency order — start them top to bottom.

| # | Service | What it is | Port(s) | Must start after |
|---|---------|-----------|---------|------------------|
| 1 | **Docker Desktop** | Container runtime | — | (boot) |
| 2 | **Ollama** | Local model for classification (`qwen3:8b`) | 11434 | — |
| 3 | **OneCLI** | Credential vault (runs in Docker) | 10254 (UI), 10255 (gateway) | Docker |
| 4 | **MCP classifier** | Python LangChain server (`email-filter/server.py`) | 8765 | Ollama |
| 5 | **NanoClaw host** | Node orchestrator (`pnpm run dev`) | 3000 (webhook) | Docker, OneCLI |

NanoClaw spawns the per-agent **Docker containers** on demand — you don't start
those yourself.

## Quick start (after a reboot)

```powershell
cd C:\ClaudeSandbox\nanoclaw-investigate
.\scripts\start-all.ps1
```

This starts OneCLI → MCP server → NanoClaw host (Docker + Ollama are assumed
already running — Docker Desktop and Ollama auto-start on login by default).

Stop everything:
```powershell
.\scripts\stop-all.ps1
```

## Starting each service manually

If `start-all.ps1` fails or you're debugging one piece, start them by hand:

### 1. Docker Desktop
Launch from the Start menu. Wait for the whale icon to stop animating. Verify:
```powershell
docker version          # Server section must appear (not just Client)
```

### 2. Ollama
Usually auto-runs as a background service. If not:
```powershell
ollama serve            # run in its own window if the service isn't up
ollama list             # confirm qwen3:8b is present
```

### 3. OneCLI
```powershell
docker compose -p onecli -f $env:USERPROFILE\.onecli\docker-compose.yml up -d
```
Verify both containers are healthy:
```powershell
docker ps --filter "name=onecli" --format "{{.Names}} {{.Status}}"
```

### 4. MCP classifier (LangChain)
```powershell
cd C:\ClaudeSandbox\nanoclaw-investigate\email-filter
python server.py
```
Leave it running, or detach it:
```powershell
Start-Process python -ArgumentList "server.py" -WorkingDirectory (Resolve-Path .) -WindowStyle Hidden `
  -RedirectStandardOutput ..\logs\mcp-server.out.log -RedirectStandardError ..\logs\mcp-server.err.log
```
Expected stderr on startup: `Uvicorn running on http://0.0.0.0:8765`. Also check
**stdout** for which model it picked — `falling back to Ollama model: qwen3:8b`
(free/local) vs `Using Claude Haiku`. An `ANTHROPIC_API_KEY` in `.env` silently
flips it to Haiku; `load_dotenv` won't override an ambient env value, so clear it
per-process (`$env:ANTHROPIC_API_KEY=""`) if you intend Ollama. This serves both
the `/classify` HTTP endpoint (used by `check_inbox.ts`) and the legacy MCP tool.

### 5. NanoClaw host
```powershell
cd C:\ClaudeSandbox\nanoclaw-investigate
pnpm run dev
```
Detached (note: must be `pnpm.cmd`, not `pnpm`, under Start-Process):
```powershell
$pnpm = (Get-Command pnpm.cmd).Source
Start-Process $pnpm -ArgumentList "run","dev" -WorkingDirectory (Resolve-Path .) -WindowStyle Hidden `
  -RedirectStandardOutput logs\nanoclaw.out.log -RedirectStandardError logs\nanoclaw.err.log
```
Healthy startup ends with `NanoClaw running` and `Webhook server started`.

## Health checks (one-shot)

```powershell
# All four ports up?
foreach ($p in 11434,10254,8765,3000) {
  "{0}: {1}" -f $p, (Test-NetConnection 127.0.0.1 -Port $p -WarningAction SilentlyContinue).TcpTestSucceeded
}
# 11434=Ollama  10254=OneCLI  8765=MCP classifier  3000=NanoClaw webhook
```

```powershell
docker ps --format "{{.Names}}\t{{.Status}}"   # onecli + onecli-postgres healthy
```

## Watching logs (the "terminal 1" equivalent)

When run detached, services log to files instead of a window:

| Service | Log file |
|---------|----------|
| NanoClaw host | `logs/nanoclaw.out.log` (info), `logs/nanoclaw.err.log` (errors + startup) |
| MCP classifier | `logs/mcp-server.out.log`, `logs/mcp-server.err.log` |
| Agent container | `docker logs <container-name>` (lost after it exits — `--rm`) |

Tail NanoClaw live:
```powershell
Get-Content logs\nanoclaw.err.log -Wait -Tail 20
```

## Debugging startup failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `docker version` shows only Client | Docker engine not up | Start Docker Desktop, wait for whale to settle |
| OneCLI containers not listed | Compose not started | Re-run the `docker compose ... up -d` line |
| `Start-Process pnpm` → "not a valid Win32 application" | Bare `pnpm` isn't an exe | Use `pnpm.cmd` (start-all.ps1 already does) |
| `FastMCP.run() got unexpected kwarg 'host'` | Old API call | host/port go on the `FastMCP(...)` constructor, not `run()` |
| Agent "types" forever, no reply | `check_inbox.ts`'s `/classify` call waiting on Ollama (cold + local) | Normal on first call — wait. Persistent → check MCP server + Ollama up |
| Warm container stops responding to new messages | Pre-fix poll-loop wedge (open query blocked the loop) | Fixed in `poll-loop.ts`; if it recurs, `docker rm -f` the container and let the host respawn (see [[gmail-integration-issues]] #7) |
| `claude native binary not found` | Container image issue | Rebuild via `scripts/build-container.ps1` (see [[windows-setup-issues]] #9/#10) |
| Stale containers using old source | Containers spawned before a source edit | `docker ps`, kill them, restart NanoClaw (see [[windows-setup-issues]] #11) |
| `listen EACCES ... cli.sock` | CLI Unix socket on Windows | **Harmless** — ignore (see [[windows-setup-issues]] #15) |

## Known harmless noise

- The `cli.sock` EACCES error on every NanoClaw startup — the CLI channel can't
  bind a Unix socket on Windows. Telegram is unaffected.
- First classify call is slow (Ollama cold start + local model). The agent shows
  a typing indicator the whole time; this is not a hang.

## Image / slug note

The agent container image is `nanoclaw-agent-v2-<slug>` where slug =
sha1(project path). Build from **Windows PowerShell** via
`scripts/build-container.ps1` so the slug matches the host runtime — building in
WSL produces a different slug and NanoClaw won't find the image (see
[[windows-setup-issues]] #8).
