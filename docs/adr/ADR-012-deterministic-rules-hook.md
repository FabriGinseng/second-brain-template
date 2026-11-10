# ADR-012 – Deterministic rules through a hook

- **Status:** Accepted (template default: edit `.claude/hooks/regole.json` to match your own rules)
- **Date:** <YYYY-MM-DD>
- **Revises:** [ADR-004](ADR-004-autonomy-level.md), point 3 (enforcement)

## Context

Rules written in `CLAUDE.md` are instructions, not checks. `deny`/`ask` rules in `settings.json` compare the command text, so `git -C . push` or `sh -c 'git push'` gets past them. Another hook that rewrites commands (for example one that prefixes `git` with a wrapper) can turn a confirmed action into an allowed one.

## Decision

1. **One list, one hook.** `.claude/hooks/regole.json` lists the rules and `.claude/hooks/regole.py` applies them to Bash and to Edit|Write. `scripts/installa-regole.py` copies both to `~/.claude/hooks/` and registers the hook in `~/.claude/settings.json`, so the rules apply in every repo. `setup.py` offers this step and asks first.
2. **Refused:** force-push, `reset --hard`, `clean`, rewriting history, commits that skip hooks, and changes to the guardrails themselves. **Ask first:** push, pull requests, releases, publishing, deploys, `ssh`/`scp`/remote `rsync`, `rm`, `launchctl`.
3. **The command is parsed, not matched as text.** Wrappers (`env`, `sudo`, `xargs`, absolute paths, `sh -c`, `eval`, `$(…)`) and git's global options are removed first.
4. **Fails closed.** On any internal error the hook asks. It never answers "allow".
5. **Unattended runs.** "Ask" is a no in `claude -p`, so those actions land in "Da confermare" (ADR-004).

## Trade-off

It is a guardrail against mistakes, not a boundary against someone determined to bypass it. Known gaps: git aliases, scripts in files (`bash x.sh`), inline code (`python -c`), MCP tools.
