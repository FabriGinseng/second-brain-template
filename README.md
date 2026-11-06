# second-brain-template

A starter kit for a personal "second brain": an Obsidian vault of plain Markdown, kept up to date by an AI coding agent ([Claude Code](https://claude.com/claude-code)) under rules you control. Italian version: [README.it.md](README.it.md).

> **Status: v0.1.** The vault structure, the setup wizard, the checks and the local dashboard work. Scheduled jobs are generated for macOS, Linux and Windows. Used daily on macOS. On Linux and Windows the automated tests pass in CI, but nobody has used the installer there for real yet: see "Platform support". Nothing here has been tested against a real iCloud, Nextcloud or Fastmail account.

## What you get

- **Projects**: one short `STATE.md` per project, rewritten (never appended), a dated `decisions.md`, and a row in `projects/INDEX.md`.
- **Rules the agent follows**: a short `CLAUDE.md`, decisions in `docs/adr/` (confidential notes, autonomy level), a glossary.
- **Permissions that back the rules**: `.claude/settings.json` blocks push, force-push, history rewrites and the confidential folder.
- **A check**: `scripts/verify` verifies the vault rules. No model, files only.
- **Commands and subagents** in `.claude/`: see "Commands". The command texts are in Italian in v0.1.
- **A local dashboard** (Python standard library, `127.0.0.1` only): projects, plan, today, radar, services and limits, posts, and an assistant panel. It shows only the pages of the modules you chose.
- **`setup.py` and `doctor.py`**: a first-run wizard made of modules, and a check of what your choices need.

## Requirements

- Python 3.9 or newer and git.
- [Claude Code](https://code.claude.com/docs/en/setup) with a paid Claude plan (the free plan does not include it). The agent, the weekly drafts and the `claude` model choice use it and your plan quota.
- Optional, only if you pick the matching feature: [Ollama](https://ollama.com) for local models; Chrome, Chromium or Edge for the post images; [Obsidian](https://obsidian.md) to read the notes in a nice interface; n8n only if you prefer it to the built-in news collector.

`python3 doctor.py` tells you what is missing and prints the official install command for your system. It never installs anything by itself.

## Install step by step

The same four steps on every system; the details differ only for the first one.

1. **Install Python, git and Claude Code.** Check with `python3 --version`, `git --version`, `claude --version` (on Windows `py -3 --version`).
2. **Get the template.** `git clone https://github.com/FabriGinseng/second-brain-template.git my-second-brain`, then `cd my-second-brain`. You can open that folder as a vault in Obsidian.
3. **Run the wizard.** `python3 setup.py` (Windows: `py -3 setup.py`). It asks for the language, your name and role, then offers each optional module with a yes or no. Before it writes anything it shows a summary and waits for your yes. It never overwrites a file that exists.
4. **Check.** `python3 doctor.py`, then `python3 scripts/verify`, which must print `OK`.

Then follow [GETTING_STARTED.md](GETTING_STARTED.md): about 15 minutes, each step says what you should see.

### macOS

Python: `brew install python`, or the installer from python.org (see the note in "Troubleshooting"). git: `xcode-select --install`. Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`. Everything in this guide works here, including the calendar from the Calendar app.

### Linux

Python and git from your package manager (for example `sudo apt install python3 git`). Claude Code: the same `curl` command as above. Scheduled jobs use systemd user timers: run `loginctl enable-linger $USER` once so they also run when you are not logged in. For the post images install Chromium or Chrome.

### Windows

Use `py -3` where this guide says `python3`. Python: `winget install Python.Python.3.12`. git: `winget install Git.Git`. Claude Code: `irm https://claude.ai/install.ps1 | iex` in PowerShell. Native Windows is the least tested path: WSL 2 is the safer choice for Claude Code until it has been tested for real.

## The setup wizard and its modules

`python3 setup.py --list` shows the modules and what each one does; `python3 setup.py --add <module>` adds one later without touching what you already have. A module can only ask you questions and then do a few fixed things (write a setting, create a folder or a file that does not exist, add a line to `.gitignore`, add `deny` rules). It cannot run commands.

| Module | What it asks | What it does |
|---|---|---|
| `core` (always) | your name, role, language | `config.json`, `memory/` files, your name in `CLAUDE.md` |
| `riservata` | the name of a confidential folder | creates it, git-ignores it, blocks Claude Code from reading and editing it |
| `radar` | topics, feed addresses, who collects the news, which model for each step | the Monday radar: news from your feeds, filtered for your projects, one short card each in `radar/` |
| `bozze` | LinkedIn, Instagram or both | the Monday drafts in `content/`; never publishes |
| `servizi` | nothing | the Services page of the dashboard |
| `assistente` | which model answers, which calendar, and whether appointments may go to Claude | the assistant panel in "Today" |
| `scaffold` | nothing | a registry of project templates, two profiles (`personal`, `lavoro`) and a reminder for repos the vault does not know: see "Track the repos you already have" |

**After the questions, the wizard prepares the computer.** It scans RAM, free disk, CPU and graphics card (nothing else, nothing is sent anywhere) and uses that to suggest a local model: about 8 GB of RAM gets a 4B model, 16 GB or more `qwen3:8b`, less than that Claude or no model, and no download is offered if the disk is nearly full. Then, one step at a time, it asks before doing each of these and shows the command it would run: install Ollama or Obsidian if you chose something that needs them (with `brew` on macOS, `winget` on Windows, `flatpak` on Linux), download the local models you picked (`ollama pull`), turn on the secret scan before commits, add the Claude usage status line to `~/.claude/settings.json` (a copy of the file is kept), register the scheduled jobs, and run the radar once so its page has something to show. You can say no to any step and do it later by hand. It does **not** run installers that are downloaded from the internet and piped into a shell: for Claude Code (and Ollama on Linux) it prints the official command and you run it yourself. With `--yes` or `--answers` it never installs anything.

You can also run the wizard without questions: `python3 setup.py --answers answers.json --yes`. `tests/risposte-tutti.json` is a complete example. `python3 setup.py --dry-run` shows what would happen and changes nothing. `python3 setup.py --clean-example` removes the example project when you have your own.

## Local or Claude: who answers what

Every step that needs a model has its own setting in `config.json` (`modelli`), and the default is `none`: no model, nothing leaves your computer, nothing to download.

| Choice | What happens | Cost |
|---|---|---|
| `none` | the radar matches keywords and you read every candidate; the assistant panel stays off | nothing |
| `ollama:<model>` | everything stays on your computer; slower and less precise | disk space and RAM |
| `claude` | more precise; the text of that step leaves your computer for Anthropic | your plan quota |

What is sent with `claude`: for the radar, the titles of the news and the stack and goal of your projects; for the assistant, your question and, only if you allowed it at setup, the titles and times of your appointments. The confidential folder is never sent by any step. Dates, weekdays and free hours are computed by the code, not by the model, because a model gets them wrong.

`python3 scripts/modello.py --ram` suggests a local model for your RAM (about 8 GB: a 4B model; 16 GB or more: `qwen3:8b`). These are thresholds, not measurements on your machine. `python3 scripts/modello.py --check-model <step>` runs three fixed test requests and tells you whether the model you chose is suitable. To download a model: `ollama pull <model>`.

## The assistant and your calendar

The panel in "Today" answers questions about your day ("what is due this week?", "when am I free tomorrow?") and can propose an appointment that you confirm with a click. It has no tools and no web: it only sees a text the code prepares. The model can be wrong, and the page says so.

The calendar goes through `scripts/calendario.py`. Choose a provider in `config.json` (`calendario.provider`) or in the wizard:

| Provider | Systems | Reads | Writes | Needs |
|---|---|---|---|---|
| `macos` | macOS | yes | yes | the Calendar app (Google and iCloud accounts already in it) |
| `ics` | all | yes (repeating events too) | no | the secret iCal address of a calendar, or a `.ics` file |
| `caldav` | all | yes | yes | server, user and an app password (iCloud, Nextcloud, Fastmail) |
| `none` | all | no | no | nothing: the assistant says it does not know your appointments |

The addresses and passwords are credentials. They live **outside** the vault, which goes into git: `~/.config/second-brain/` on macOS and Linux, `%APPDATA%\second-brain\` on Windows, in files readable only by you (`chmod 600`; otherwise the provider refuses to read them).

- `calendari.json` for `ics`: `{"calendari": [{"nome": "Personal", "url": "https://..."}, {"nome": "Holidays", "file": "/path/holidays.ics"}]}`. In Google Calendar the address is under the calendar's settings, "Secret address in iCal format". Only `https://` addresses are accepted.
- `caldav.json` for `caldav`: `{"server": "https://caldav.icloud.com", "utente": "you@example.com", "password": "app password"}`. Only `https://`, redirects are not followed, a server that points to another domain is refused, and no error message shows the password.

If a calendar cannot be read, the assistant does not answer about free hours instead of telling you that you are free when you are not. If the model is `claude` and you did not allow it at setup (`moduli.assistente.calendario_al_cloud`), the assistant does not receive your appointments. Google Calendar outside the Mac is not supported for writing; reading works through the secret iCal address. Repeating rules the reader does not understand (for example "second Tuesday and fourth Thursday") are shown as a warning in "Today", not ignored in silence.

## The dashboard

`python3 scripts/dashboard/server.py`, then open http://127.0.0.1:8765. It listens only on your computer. The menu shows the pages of the modules you chose; a page you did not choose is not there. `second-brain.dashboard` (see "Scheduled jobs") keeps it running. On Linux and Windows the job status buttons stay empty because they use launchd.

## When a page is empty

A new install starts with empty pages on purpose: they fill when something has run once. Nothing is broken if you see these.

| Page | Fills when | What to do |
|---|---|---|
| Radar | the radar has run once | put your feeds in `memory/feeds.md`, then run `python3 scripts/feed.py` and `python3 scripts/radar.py` (Windows: `py -3`), or press Radar in the Avvii page. After that the jobs run every Monday. |
| Local model | Ollama is running and a model is downloaded | start the Ollama app (or `ollama serve`), then `ollama pull <model>`; the call list fills as the radar and the assistant use it. Swap and the process list exist only on macOS. |
| Uso di Claude | Claude Code has saved your usage percentages, and you have used it | add the status line below to `~/.claude/settings.json`; the tokens per day come from your own Claude Code sessions and appear by themselves. |
| Today, calendar part | a calendar provider is connected | see "The assistant and your calendar". |
| Avvii | the jobs are registered | `install_jobs.py`; the job status (running, loaded) is read from launchd, so only macOS shows it. |

The status line for the Claude usage page (put the real path of your vault; on Windows use `py -3 -I C:\path\to\vault\scripts\statusline-uso.py`):

```json
{ "statusLine": { "type": "command", "command": "python3 -I /path/to/vault/scripts/statusline-uso.py" } }
```

It only saves the two usage percentages and their renewal time, not the content of your sessions. It touches your global `~/.claude`, so the wizard does not do it for you.

## Commands

Start `claude` in the vault folder and type:

| Command | What it does |
|---|---|
| `/nuovo-progetto <name> [path]` | creates the project folder, its `STATE.md` and the row in `projects/INDEX.md`; with a path it also writes the `Repo:` field |
| `/morning` | the morning brief: projects, news, priorities |
| `/chiudi-giornata` | rewrites the STATE files from your commits, runs the checks and commits locally; never pushes |
| `/weekly-review` | what moved, what is stuck, what is neglected |
| `/post` | turns a note into a LinkedIn draft in `content/linkedin/` |
| `/bozze-settimana` | three post drafts for the week (LinkedIn and Instagram, as you chose) |
| `/commit-push-pr` | commit, push and open a PR for a code repo, asking you before the push |
| `/adotta-repo` | once: lists the git repos on your computer that the vault does not know and records your answers |

Subagents: `researcher` (reads the news and writes cards in `radar/`), `reviewer` (reviews the week, writes nothing), `writer` (drafts, only with `/post`). None of them can start another.

## Scheduled jobs

`scripts/jobs.json` defines the jobs once; `python3 install_jobs.py` registers them with the scheduler of your system: launchd on macOS, systemd user timers on Linux, Task Scheduler on Windows. Start with `python3 install_jobs.py --dry-run` to read what it would do. `python3 install_jobs.py --uninstall` removes them. Each job is safe to start twice, so catching up after the computer was off is harmless. The jobs of a module you chose are registered; the other optional ones need `--all`.

| Job | When | What it does |
|---|---|---|
| `second-brain.morning` | weekdays 08:00 and at login (macOS and Windows; not on Linux yet) | the morning start: closes pending work, creates the daily note |
| `second-brain.chiusura` | weekdays 18:30 | `/chiudi-giornata`: rewrites the STATE files from your commits |
| `second-brain.pulizia` | Friday 18:00 | weekly check and report |
| `second-brain.dashboard` | at login, kept running | the local dashboard |
| `second-brain.feed` (optional, chosen in setup) | Monday 07:00 | `scripts/feed.py`: collects the news from `memory/feeds.md` into `inbox/` (built-in collector; skip it if you use n8n) |
| `second-brain.radar` (optional, chosen in setup) | Monday 07:30 | filters the news in `inbox/` for your projects, with the models you chose |
| `second-brain.bozze` (optional, chosen in setup) | Monday 08:30 | `/bozze-settimana`: three post drafts |

The text of a news item is untrusted: every title goes through `content-guard` (hidden-instruction patterns) before any model sees it. Logs are in `~/Library/Logs` (macOS), `$XDG_STATE_HOME/second-brain` or `~/.local/state/second-brain` (Linux), `%LOCALAPPDATA%\second-brain\logs` (Windows).

## Checks

- `python3 scripts/verify` checks the vault rules: short STATE files, a consistent `INDEX`, valid links, that this README mentions every job and command, and the `scaffold/` registry if you have one. Run it after any change to a STATE or the index; `/chiudi-giornata` runs it for you.
- `python3 doctor.py` checks Python, git, Claude Code, `verify`, and what your choices need (Ollama running, each local model downloaded, enough RAM, n8n if you picked it). `--ci` checks only the required items.
- Secret scan: `scripts/hooks/pre-commit` runs gitleaks on what you are about to commit and blocks the commit if it finds a secret. Turn it on once per clone with `git config core.hooksPath scripts/hooks`; it needs [gitleaks](https://github.com/gitleaks/gitleaks) installed (`doctor.py` shows how).

## Track the repos you already have

The `scaffold` module is optional. It creates `scaffold/registro.md` (the project templates you start from, empty), `scaffold/profili/personal.md` and `scaffold/profili/lavoro.md` (what to do for your own projects and for work ones; work has no AI features and no remote repo), `scaffold/ignorati.md` (repos you said "ignore" or "not now" to) and `scaffold/hook-avvio.md`.

- `/adotta-repo` asks where to look, lists the git repos the vault does not know (repos with the same remote are grouped) and records your answer for each: track it, ignore it, ask again in 7 days, or "work". For a work repo only a hash of the path is saved, never the path or the name.
- `scripts/repo-non-tracciato.py` tells whether the current folder is an untracked git repo. It never writes by itself. With the hook in `scaffold/hook-avvio.md` Claude Code can remind you when you open such a repo. That hook touches your global `~/.claude` settings, so the wizard does **not** install it: the file shows the two lines to paste, and you decide.
- A repo is "tracked" when its path is in the `Repo:` field of a `projects/*/STATE.md`.

## Platform support

| Part | macOS | Linux | Windows |
|---|---|---|---|
| Vault, `scripts/verify`, `setup.py`, `doctor.py` | yes | CI tests pass | CI tests pass |
| Dashboard | yes | partly (no job status) | partly |
| Calendar: `macos` | yes | no | no |
| Calendar: `ics` and `caldav` | tested with fake data and a fake server | same | same |
| Scheduled jobs (`install_jobs.py`) | yes | files generated and tested, not registered for real yet | same |
| Morning job (`second-brain.morning`) | yes | not yet | file generated and tested, not registered for real yet |

"CI tests pass" means automated tests on a clean runner, not that someone used it. If you try it on Linux or Windows, please report what broke.

## Privacy

Claude Code sends the files it reads to the model. Put confidential notes in the folder the `riservata` module made (ignored by git and blocked by `deny` rules) and read [ADR-002](docs/adr/ADR-002-confidential-notes.md) for the limits of that block: the rules do not stop a script you run yourself. Your name, notes and memory files stay in your copy: `setup.py` writes them from the `*.example.md` files and git ignores them. Calendar addresses and passwords stay outside the vault. The dashboard listens only on `127.0.0.1`.

## Troubleshooting

- **`python3` not found on Windows**: use `py -3`.
- **Certificate error when fetching feeds on macOS**: the Python from python.org has no certificate store; the collector falls back to the system one. If it still fails, run `Install Certificates.command` from the Python folder in Applications.
- **`doctor.py` says Ollama is missing or not running**: start the Ollama app, or choose `none` for that step with `python3 setup.py --add radar`.
- **A model is missing**: `ollama pull <model>` (the name is in the `doctor.py` message).
- **The assistant says it does not know your appointments**: no calendar is connected, the calendar cannot be read, or the model is `claude` and you did not allow sending appointments. `config.json` shows `calendario.provider` and `moduli.assistente`.
- **"è leggibile da altri utenti" (the message is in Italian in v0.1)**: `chmod 600` on that file.
- **On Windows, `./scripts/verify` does not start inside Claude Code** (Git Bash cannot run the `python3` shebang): use `py -3 scripts/verify`. The commands and the permissions already allow it.
- **On Windows the jobs run without a window**: Task Scheduler starts them through `conhost.exe --headless`, so no empty CMD window appears. If a job registered before this change still opens one, run `py -3 install_jobs.py` again to re-register it.
- **`scripts/verify` complains**: the message names the file and line; fix that and run it again.
- **Jobs do not run on Linux when you are logged out**: `loginctl enable-linger $USER`.

## Update and uninstall

Update: `git pull`, then `python3 doctor.py` and `python3 scripts/verify`. Your files are ignored by git or untouched by the pull. Uninstall: `python3 install_jobs.py --uninstall`, then delete the folder. Claude Code and Ollama have their own uninstall guides.

## Licence

MIT, see `LICENSE`. To report personal data that ended up here by mistake, see `SECURITY.md`.
