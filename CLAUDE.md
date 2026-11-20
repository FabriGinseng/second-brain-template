# Second brain: instructions for the orchestrator

## Who I am

<your name>, <your role>. Who I am, my skills and tone: [memory/about-me.md](memory/about-me.md). How I want you to work: [memory/preferences.md](memory/preferences.md). They are loaded at every session (a file that does not exist yet is skipped):

@memory/about-me.md
@memory/preferences.md

Language: reply in the language set in `config.json` (`language`). The system files (STATE, daily, commands) are written in Italian in v0.1.

## How to read the vault

Start from the minimum and open more only if needed:

1. `projects/INDEX.md`: one line per project.
2. Only the `STATE.md` files of the projects relevant to the question.
3. The project's `decisions.md`, only if you really need it.

Today's date is in `OGGI.md` when the system writes it. If the session does not tell you the date, do not trust data from days ago.

Architecture decisions live in `docs/adr/`. The vocabulary is in `GLOSSARY.md`.

## Commands

Run them from the vault root. Python 3.9 or later; on Windows write `py -3` in place of `python3`.

| Command | What it does |
|---|---|
| `python3 scripts/check` | The single check before a commit or a pull request: `verify`, ruff, both test suites, gitleaks. Stops at the first red step and names it |
| `python3 scripts/verify` | Checks the vault rules (STATE, INDEX, links, README). Must print `OK` |
| `python3 -m unittest discover -s scripts -p "test_*.py"` | Tests of the scripts, the dashboard and the hooks, about a minute |
| `python3 -m unittest discover -s tests` | Tests of the wizard, the prerequisites check and the jobs |
| `python3 doctor.py` | Says what is missing on this computer and how to install it |

A commit runs gitleaks on the staged changes and `scripts/verify` by itself, plus the script tests when it touches `scripts/` or `.claude/`, through `scripts/hooks/pre-commit`. Ruff and the template tests run only in `scripts/check`.

## Where things are

- `projects/`, `daily/`, `inbox/`, `radar/`, `content/`: the notes. This is where you write.
- `memory/`, `docs/adr/` and this file: who the user is, the decisions, the rules. A change needs a yes.
- `docs/piano.md`, `docs/obiettivi.md`, `docs/scadenze.md`: the plan, the goals and the deadlines the dashboard and the map read. `docs/calendari.md` and `docs/servizi.md` feed two dashboard sections; the other `docs/*.md` are optional guides. Specs and plans written with superpowers go in `docs/specs/` and `docs/superpowers/plans/`.
- `kit/`: lists of plugins and skills that `/kit <name>` proposes, one at a time, after `scan-before-install`.
- `scripts/`: the routines, each with its `test_` file next to it. `scripts/dashboard/` is the local dashboard, `scripts/hooks/` the commit hook.
- `.claude/`: commands, subagents, rules loaded by path, hooks and permissions.
- `modules/` and the Python files at the root: the first-run wizard, the prerequisites check and the scheduled jobs. `tests/` holds their tests.
- `templates/`, `scaffold/`: what a new project starts from.

## Writing rules

- `STATE.md` is rewritten from scratch, never appended, and stays under about 20 lines.
- What is no longer current moves to the project's `decisions.md`, with the date.
- Every change to a `STATE.md` updates the matching row in `projects/INDEX.md`.
- After any change to a `STATE.md` or to `INDEX.md`, run `scripts/verify`.
- Documentation is part of the work: when a routine, job, command, page or rule changes, update `README.md` in the same commit. `scripts/verify` flags a command the README does not cite.
- Notes in `projects/_private/` never go to a cloud model (ADR-002): high-level state only, no client details.

## Autonomy limits

From [ADR-004](docs/adr/ADR-004-autonomy-level.md):

- **Autonomous:** write in the vault, create new files in `inbox/`, `radar/`, `daily/`, `projects/`, make local commits.
- **With confirmation:** push, email, publishing, deleting, changes to `docs/adr/`, `CLAUDE.md`, `memory/`, adding an MCP server.
- **Never:** force-push, `git reset --hard`, rewriting history.

The push ban in `.claude/settings.json` is a guardrail, not a boundary. Make local commits only after `scripts/verify` passes, one commit per routine. In unattended runs, actions that need confirmation are not executed: they go in the "Da confermare" section of the day's `daily/` file.

## Delegation

Delegate from the main session. Subagents do not start others (enforced by leaving `Agent` out of their `tools`).

- **`researcher`**: reads `inbox/`, `projects/INDEX.md`, the `STATE.md` of active projects. Writes only new files in `radar/`.
- **`reviewer`**: reviews the week. Does not write files.
- **`writer`**: writes post drafts. Only with `/post`, never unattended.

## Recurring errors

The log of corrected mistakes ([ADR-015](docs/adr/ADR-015-learning-loop.md)). One dated line per mistake, proposed by `/chiudi-giornata` and written only after a yes:

`- YYYY-MM-DD · what happened · causa: why · layer: nessuno | regola <file> | check <name>`

The first time a cause shows up it gets the line. The second time `/weekly-review` proposes a rule in `.claude/rules/` with `paths`, or a check when it can be verified. No secrets, names or client details here. In unattended runs the proposal goes to "Da confermare" in the day's `daily/` file. Any other change to this file needs confirmation.
