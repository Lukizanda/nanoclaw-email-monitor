# Windows Setup Issues & Fixes

> Every problem hit while bringing NanoClaw + Telegram + Docker + OneCLI up on
> Windows 11, and exactly how each was fixed. Read this first if setup breaks.

**Last updated:** 2026-06-02
**Related:** [[nanoclaw]], [[onecli]], [[mcp]], [[architecture]]

## Context

NanoClaw is built for macOS/Linux. Running it on Windows 11 (with Docker Desktop
+ WSL 2) surfaced a chain of platform issues. None are showstoppers, but they
compound. This is the full list in roughly the order we hit them.

---

## 1. Shell scripts had CRLF line endings + BOM

**Symptom:**
```
./container/build.sh: line 8: $'\r': command not found
./container/build.sh: line 1: ﻿#!/bin/bash: No such file or directory
```

**Cause:** Git on Windows checked out `.sh` files with CRLF line endings and a
UTF-8 BOM. Bash chokes on both — `\r` becomes a literal command character and
the BOM corrupts the shebang.

**Fix:** Convert all shell scripts to LF, strip BOM:
```powershell
Get-ChildItem "C:\ClaudeSandbox\nanoclaw-investigate" -Recurse -Include "*.sh" | ForEach-Object {
  $c = [System.IO.File]::ReadAllText($_.FullName)
  $c = $c.Replace("`r`n","`n").Replace("`r","`n").TrimStart([char]0xFEFF)
  [System.IO.File]::WriteAllText($_.FullName, $c, [System.Text.UTF8Encoding]::new($false))
}
```

**Prevention:** Add a `.gitattributes` with `*.sh text eol=lf` to keep shell
scripts LF on checkout.

---

## 2. WSL had no Linux distribution

**Symptom:**
```
Windows Subsystem for Linux has no installed distributions.
```

**Cause:** WSL 2 was enabled but no distro installed. Docker Desktop needs one.

**Fix:**
```powershell
wsl --install -d Ubuntu
```

---

## 3. Virtualization disabled in BIOS

**Symptom:** Docker Desktop: *"Virtualization support wasn't detected."*
`Get-ComputerInfo` showed `HyperVRequirementVirtualizationFirmwareEnabled = False`.

**Cause:** CPU virtualization (AMD SVM / Intel VT-x) was off in BIOS.

**Fix:** Reboot → enter BIOS (Del/F2) → enable **SVM Mode** (AMD) or
**Intel Virtualization Technology** (Intel) → save & exit. After enabling,
`systeminfo` shows *"A hypervisor has been detected"* (which is why
`Get-ComputerInfo` then returns blank — that's expected, not a failure).

---

## 4. Docker Desktop stuck on "Starting the Docker Engine"

**Symptom:** Engine never responds. Logs show:
```
still waiting for init control API to respond after 3m
GET /ping → ConnectionClosed (context deadline exceeded)
```
The `docker-desktop` WSL distro never appeared in `wsl --list`.

**Cause:** First-time WSL distro setup never completed.

**Fix:** Docker Desktop → Settings → Troubleshoot → **Reset to factory
defaults**. Forced a clean first-time setup. (Virtual Machine Platform was
already enabled in our case — confirm with `dism /online /get-featureinfo
/featurename:VirtualMachinePlatform`.)

---

## 5. Docker not found inside WSL

**Symptom:**
```
The command 'docker' could not be found in this WSL 2 distro.
```

**Cause:** Docker Desktop's WSL integration wasn't enabled for Ubuntu.

**Fix:** Docker Desktop → Settings → Resources → **WSL Integration** → toggle
Ubuntu on → Apply & Restart.

---

## 6. pnpm global bin not in PATH (Dockerfile build)

**Symptom:** Build failed at the pnpm global-install layer:
```
[ERROR] The configured global bin directory "/pnpm/bin" is not in PATH
```

**Cause:** Dockerfile set `ENV PATH="$PNPM_HOME:$PATH"` but pnpm 11.x installs
binaries to `$PNPM_HOME/bin`, not `$PNPM_HOME`.

**Fix:** `container/Dockerfile`:
```dockerfile
ENV PATH="$PNPM_HOME/bin:$PNPM_HOME:$PATH"
```

---

## 7. Windows symlink permission denied (EPERM)

**Symptom:**
```
EPERM: operation not permitted, symlink 'C:\app\skills\agent-browser' -> '...'
Failed to route inbound message
```

**Cause:** `syncSkillSymlinks` in `container-runner.ts` creates symlinks. Windows
restricts symlink creation to admins by default.

**Fix:** Settings → Privacy & Security → For Developers → enable **Developer
Mode**. No restart needed.

---

## 8. Install slug mismatch → wrong Docker image name

**Symptom:**
```
Unable to find image 'nanoclaw-agent-v2-1c4453fc:latest' locally
pull access denied ... repository does not exist
Container exited code=125
```
But we'd built `nanoclaw-agent-v2-cc43d48f:latest`.

**Cause:** The image name embeds `sha1(projectRoot)[:8]`. The build ran in WSL
(`/mnt/c/ClaudeSandbox/...`) but the NanoClaw host runs on Windows
(`C:\ClaudeSandbox\...`) — different paths → different SHA1 → different image name.

**Fix (quick):** Tag the built image with the Windows-slug name:
```powershell
docker tag nanoclaw-agent-v2-cc43d48f:latest nanoclaw-agent-v2-1c4453fc:latest
```

**Fix (permanent):** Build from Windows PowerShell so the slug matches the
runtime. See `scripts/build-container.ps1`, which computes the slug from the
Windows path and builds with the correct tag.

---

## 9. Claude Code path wrong (/pnpm/claude)

**Symptom:**
```
Error: Claude Code native binary not found at /pnpm/claude
```

**Cause:** `container/agent-runner/src/providers/claude.ts` hardcoded
`pathToClaudeCodeExecutable: '/pnpm/claude'`, but pnpm 11.x puts the shim at
`/pnpm/bin/claude`.

**Fix:**
```typescript
pathToClaudeCodeExecutable: '/pnpm/bin/claude',
```
The agent-runner source is live-mounted RO at runtime, so this takes effect on
the next *fresh* container — see issue #11.

---

## 10. Claude Code native binary not installed (Windows .exe shim)

**Symptom:**
```
Error: claude native binary not installed.
```
`/pnpm/bin/claude` pointed at `claude.exe` (a Windows binary) inside the Linux
container. The pnpm postinstall created a Windows-style cmd-shim.

**Cause:** pnpm's cmd-shim generation produced a `.exe` target. The native
Linux binary postinstall couldn't overwrite the read-only pnpm store file.

**Fix:** Use the official Node.js fallback `cli-wrapper.cjs` instead of the
native binary. `container/Dockerfile`:
```dockerfile
RUN WRAPPER=$(ls /pnpm/global/v11/7-*/node_modules/@anthropic-ai/claude-code/cli-wrapper.cjs 2>/dev/null | head -1) && \
    printf '#!/bin/sh\nexec node "%s" "$@"\n' "$WRAPPER" > /pnpm/bin/claude && \
    chmod +x /pnpm/bin/claude
```
Verify: `docker run --rm --entrypoint bash <image> -c "/pnpm/bin/claude --version"`
should print `2.1.116 (Claude Code)`.

---

## 11. Stale containers kept using old source

**Symptom:** After fixing the claude path (#9) and rebuilding, the
`/pnpm/claude` error *came back*.

**Cause:** The agent-runner is a persistent poll loop — a container stays "Up"
after processing a message (until idle timeout). Bun loads the source module
once at container start. Containers spawned *before* the source fix kept the old
`/pnpm/claude` value in memory and processed new messages with it. Four zombie
containers were running simultaneously:
```
docker ps --filter "name=nanoclaw-v2"
→ 4 containers "Up 7-20 minutes"
```

**Fix:** Kill all stale containers, then restart the NanoClaw host (clears its
in-memory running-container tracking):
```powershell
docker ps --filter "name=nanoclaw-v2" --format "{{.Names}}" | ForEach-Object { docker kill $_ }
# then Ctrl+C and restart `pnpm run dev`
```
The next message spawns a fresh container that loads the corrected source.

**Lesson:** After editing agent-runner source, kill running containers — a live
mount only affects *newly spawned* containers, not ones already running.

---

## 12. OneCLI install needed explicit bind host

**Symptom:**
```
Error: Could not safely determine a bind address for OneCLI.
```

**Cause:** The OneCLI installer couldn't auto-detect a bind IP under WSL.

**Fix:**
```bash
export ONECLI_BIND_HOST=127.0.0.1
curl -fsSL https://onecli.sh/install | sh
```

---

## 13. OneCLI CLI wouldn't install in Git Bash

**Symptom:**
```
Error: unsupported operating system: mingw64_nt-10.0-26200
```

**Cause:** The CLI installer doesn't recognize the Git-Bash/MSYS environment.

**Fix:** Install inside WSL Ubuntu instead:
```powershell
wsl -d Ubuntu -- bash -c "curl -fsSL https://onecli.sh/cli/install | sh"
```
Then invoke via full path: `wsl -d Ubuntu -- bash -c "~/.local/bin/onecli ..."`.

---

## 14. resolveChannelName missing from ChannelAdapter

**Symptom:** Build error after copying the Telegram adapter:
```
TS2353: 'resolveChannelName' does not exist in type 'ChannelAdapter'
```

**Cause:** The `channels` branch is ahead of trunk — its Telegram adapter uses
an adapter method trunk's interface didn't declare yet.

**Fix:** Added the optional method to `src/channels/adapter.ts`:
```typescript
resolveChannelName?(platformId: string): Promise<string | null>;
```

---

## 15. CLI socket EACCES (harmless)

**Symptom (every startup):**
```
Failed to start channel adapter channel="cli"
listen EACCES: permission denied ...\data\cli.sock
```

**Cause:** The CLI channel uses a Unix domain socket. Windows handles these
differently and the bind fails.

**Impact:** None for our use case — the CLI channel is the local-terminal admin
transport, not Telegram. The `init-first-agent` script's socket handoff also
fails for the same reason, falling back to a direct `inbound.db` write (which
works). Safe to ignore.

---

## Summary: the Windows gotcha pattern

Most issues trace to three root causes:
1. **Line endings / paths** — CRLF, BOM, and `C:\` vs `/mnt/c/` path divergence.
2. **WSL/Docker plumbing** — virtualization, distro, WSL integration, factory reset.
3. **pnpm 11.x layout** — `/pnpm/bin` not `/pnpm`, and Windows-style cmd-shims
   leaking into Linux containers.

Plus one operational lesson: **kill stale containers after editing agent-runner
source** ([[nanoclaw]] — the live mount only affects fresh spawns).
