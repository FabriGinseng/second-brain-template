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

Dated lines, added by the agent when a correction repeats. Any other change to this file needs confirmation.
