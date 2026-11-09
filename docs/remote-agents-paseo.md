# Remote coding agents from your phone (optional): Paseo

This guide is **optional** and changes no file of the vault. It lets you start and follow Claude Code agents on your projects from a phone, through [Paseo](https://paseo.sh) (open source, Apache-2.0), while the second brain keeps its usual role: it knows where each project is, prepares the context, and rewrites the STATE files from the commits every evening.

Checked against **Paseo v0.15.3** (source tag `v0.15.3`, commit `d91ae13`). Re-check the settings below when you update.

## How it fits the second brain

```text
PHONE (Paseo app, end-to-end encrypted relay)
        |
PASEO DAEMON on your computer (Windows, macOS) or on an always-on Linux VM
        |
   +----+-------------------------+
   |                              |
agent "second brain"          agent on a project repo
(Claude Code, cwd = vault)    (Claude Code, own worktree and branch)
prepares context and prompt   develops; you approve from the app
```

- The **second brain prepares and you start**. It reads `projects/<name>/STATE.md`, the stack in `projects/INDEX.md` and `memory/preferences.md`, then writes the prompt for the project agent and suggests the mode. You start that agent from the Paseo app, which takes a few taps.
- **Do not give agents Paseo's own tools (MCP).** In v0.15.3 those tools don't check who calls them. An agent that has them can approve any agent's pending permission, switch any agent to bypass mode, and create child agents in bypass mode. Hiding single tools (`disabledTools`) only hides them from the model, so it is not a security boundary.
- The **evening close needs no change**: `scripts/attivita-progetti.py` already reads every branch, so it sees the commits the agents make in their worktrees.
- The **dashboard stays on `127.0.0.1`**. The phone talks to Paseo, never to the dashboard or the vault files.
- Today's rules still apply: start every agent in **plan** mode; never use bypass; no push or merge to `main`; no deploy; no production credentials; dependencies only from the lockfile (`npm ci`) unless you approve a new one.

## What to know before installing (security review of v0.15.3)

No malicious code was found. A static scan with [skillspector](https://github.com/NVIDIA/skillspector) v2.9.6 (`--no-llm`) reports `DO_NOT_INSTALL`, but its HIGH findings in product code are pattern noise, for example base64 audio samples in an example and zero-width characters in the UI. The real risks come from the defaults:

| Risk | What to do |
|---|---|
| **The Windows installer and all auto-updates are not code-signed.** Updates are downloaded every 30 minutes and trusted on the GitHub release hash alone. One maintainer controls the releases. The release workflow signs and notarizes the macOS build; check it with `spctl` (step 1). | Check the installer hash (below). Read the changelog before you click install on an update. |
| **No daemon password by default.** Anything that reaches `127.0.0.1:6767` controls the daemon, including `/mcp/agents`. `https://app.paseo.sh` is an allowed origin by default. | Set a password. Empty the allowed origins. |
| **The first-run screen has everything ticked:** Paseo tools for agents, six Paseo skills copied to `~/.claude/skills` (not vetted), and the CLI. | Untick the tools and the skills. The CLI is fine: it is a small shim to the bundled CLI and you need it for the password. |
| **Claude agents start in `auto` mode**, where a classifier approves permission prompts instead of you. | Choose **plan** when you start an agent. Never `auto`, never bypass. |
| A repo's `paseo.json` setup commands run without approval. | Open only your own repos. |
| A built-in usage plugin reads your Claude Code OAuth token to show your quota. It sends the token only to `api.anthropic.com`. | Nothing to do; be aware of it. |
| A client can ask a CLI-installed daemon to run `npm install -g @getpaseo/cli@latest`. | Prefer the desktop app; on a server, pin the CLI version. |
| Phone push notifications (turn finished, permission needed) go in clear text through Expo to Apple and Google, with a preview of the last message. | Agents must not write secrets or personal data in their messages. |
| Agents run with **your** user's permissions. Provider sandbox options are not a host boundary. | For untrusted work, or to stop depending on your own computer, use a dedicated VM (Linux section). |

## Install

### 1. Download and verify

Download from the **GitHub release** <https://github.com/getpaseo/paseo/releases/tag/v0.15.3>. Check that the SHA-256 matches the digest GitHub shows next to the file:

| File | SHA-256 |
|---|---|
| `Paseo-Setup-0.15.3-x64.exe` (Windows x64) | `c39057f0f0c2bf84363067a5e12fa9589cf555bb6016558c8406a257f450df75` |
| `Paseo-Setup-0.15.3-arm64.exe` (Windows ARM) | `3db7a3dbeb3c42048fac6a8d661d11cc7dc50896a978e3058a2bdf86b2a378d9` |
| `Paseo-0.15.3-arm64.dmg` (Mac, Apple silicon) | `9965bb43ce050bc07d5224ce44f04da0ba9e3539944a1a31f887fefe5fd4df5f` |
| `Paseo-0.15.3-x64.dmg` (Mac, Intel) | `960e668e6a74a25f2f6b971eb1cbbfeb94bc008a41962332eab7cf60e4829036` |
| `Paseo-0.15.3-amd64.deb` (Linux) | `b4ce65fd58f52d6f061a9a4d2b2542df8be565eac2ef59f7aa2c1f448c404883` |
| `Paseo-x86_64.AppImage` (Linux) | `7af1f366a20a1a163fa5b57759234df48e2991301272350268a0c79243c3a989` |

- **Windows (PowerShell):** `(Get-FileHash .\Paseo-Setup-0.15.3-x64.exe).Hash`. Then run `Get-AuthenticodeSignature .\Paseo-Setup-0.15.3-x64.exe`: it says `NotSigned`, which is expected for this release. Windows SmartScreen warns about it; continue only if the hash matched.
- **macOS:** run `shasum -a 256 ~/Downloads/Paseo-0.15.3-arm64.dmg`. After you install, run `spctl -a -vv /Applications/Paseo.app`: it must say `accepted` and `source=Notarized Developer ID`.
- **Linux:** `sha256sum Paseo-0.15.3-amd64.deb`.

### 2. First run

Prerequisites: Claude Code installed and logged in (`claude`, then `/login`), and `gh` logged in (`gh auth login`), on the machine that runs the daemon.

Open Paseo. On the setup screen:

- **untick** the Paseo tools for agents (orchestration);
- **untick** the Paseo skills;
- keep the **CLI**: it installs `paseo` in `~/.local/bin` (on Windows a `paseo.cmd` there).

### 3. Password

In a new terminal, run `paseo daemon set-password`. The config stores only a bcrypt hash. Do not put the password in the `PASEO_PASSWORD` environment variable: every process of your user could read it there. Keep it in your password manager.

### 4. Harden the configuration

Quit Paseo, then edit the daemon config:

- Windows: `%USERPROFILE%\.paseo\config.json`
- macOS and Linux: `~/.paseo/config.json`

Set these keys. Keep everything else that is already in the file, including `daemon.auth`, which the password command wrote:

```json
{
  "daemon": {
    "listen": "127.0.0.1:6767",
    "cors": { "allowedOrigins": [] },
    "mcp": { "enabled": false, "injectIntoAgents": false },
    "relay": { "enabled": false, "requireProtectedSecurity": true }
  }
}
```

- `listen` on the loopback address only. Never `0.0.0.0`.
- `allowedOrigins: []` stops web pages, including `app.paseo.sh`, from talking to your daemon through your browser.
- `mcp.enabled: false` turns the agent-control tools off completely. See "How it fits the second brain".
- The relay stays off until you pair a phone (step 5).

Desktop settings (`desktop-settings.json` in the app's data folder: `%APPDATA%\Paseo\` on Windows, `~/Library/Application Support/Paseo/` on macOS): `"releaseChannel": "stable"`. While you are trying it out, also set `"daemon": { "keepRunningAfterQuit": false }`.

Check who can read the folder:

- Windows: `icacls %USERPROFILE%\.paseo`. Only your user, `SYSTEM` and `Administrators` should appear.
- macOS and Linux: `ls -ld ~/.paseo`. It should be `drwx------`; if not, run `chmod 700 ~/.paseo`.

### 5. Pair your phone

1. Install the Paseo app: App Store "Paseo", or Google Play `sh.paseo`. The F-Droid build has no push notifications.
2. On the computer, run `paseo daemon pair --relay`, or open Settings → host → Pair a device. This turns the relay on; `requireProtectedSecurity: true` keeps older, unprotected clients out.
3. Scan the QR code. **Treat the QR code like a password**: whoever scans it can drive your agents. Do not screenshot it or share it.
4. In the app, allow notifications if you want push for "finished" and "needs permission". Errors are not pushed.

### 6. First test (plan mode only)

1. In the app, open a **personal test repo**. Do not start with a work repo or one that holds real personal data.
2. Start a Claude Code agent in **plan** mode with a read-only question, for example "describe the structure of this repo; do not modify files".
3. Check that the answer arrives, that a push notification arrives when the turn ends, and that a permission request, if one comes, shows up in the app.
4. Write down which permission rules applied: Claude Code reads `~/.claude/settings.json` and the repo's `.claude/settings.json` (deny rules for push, `reset --hard`, `.env*`).

## Platform notes

### Windows

- The daemon uses the environment it was started with, not a login shell. If `claude` or `gh` is not found, start Paseo after they are on `PATH`.
- App logs: `%APPDATA%\Paseo\logs\main.log`.
- The secret files in `%USERPROFILE%\.paseo` are protected only by your profile permissions; the Unix `0600` mode does not apply on Windows.

### macOS (not yet tested with this template; see the checklist)

- The release workflow signs and notarizes the app, so Gatekeeper should open it without warnings. Confirm this with `spctl` (step 1).
- Settings live in `~/Library/Application Support/Paseo/`, the daemon config in `~/.paseo/`.
- The CLI symlink goes to `~/.local/bin/paseo`. If `paseo` is not found, add `~/.local/bin` to `PATH` in `~/.zshrc`.
- Sleep stops the agents. For long runs, keep the Mac awake (for example `caffeinate -i`) or move to a VM.

### Linux / Proxmox VM (always on, no need to keep your computer running)

- Use a **dedicated VM** (for example Ubuntu on Proxmox) with a **dedicated user** that has no production credentials, no backups mounted and no access to real patient or customer data. That user's SSH key gets read access only to the repos it works on.
- Install the `.deb` or the AppImage, or, headless, the CLI pinned to one version: `npm install -g @getpaseo/cli@0.15.3`, never `@latest`. Run `npm audit` before you trust it.
- Log in to `claude` and `gh` as that user. Pair the phone through the relay; open no ports. As an alternative to the relay, use Tailscale with `listen` set to the tailnet IP plus a password, never a public address.
- Start the daemon at boot with a systemd unit for that user. Checking that this survives a reboot is still a TODO.

## Test checklist (please report results in an issue)

- [ ] Windows x64: hash, install, set the password, hardened config, pair, plan-mode agent, push notification.
- [ ] **macOS (Apple silicon and Intel): `spctl` reports notarized, install, CLI on `PATH`, set the password, hardened config, pair, plan-mode agent, push notification.**
- [ ] Linux VM: install, systemd unit, survives a reboot, pair through the relay.
- [ ] The evening close sees the commits an agent made on its branch in a Paseo worktree.
- [ ] With `mcp.enabled: false`, an agent has no `paseo` tools: ask it to list its tools.
