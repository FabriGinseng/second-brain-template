# ADR-001 – Vault boundaries

- **Status:** Accepted (template default: edit it to match your own situation)
- **Date:** <YYYY-MM-DD>

## Context

The system keeps memory, projects, daily notes and the radar in one place. Some of what you write is private (clients, health, money). You have to decide whether that lives in the same vault or in a separate one.

## Decision

1. **One vault.** Memory, projects, daily notes and radar sit together, so the agent can answer "where am I?" with one read of `projects/INDEX.md`.
2. **A private remote.** If you put the vault on GitHub, the repository is private.
3. **Confidential notes in one folder.** `projects/_private/` holds notes that must not reach a cloud model. How it is kept out of the agent's reach, and how much detail is allowed there, is decided in [ADR-002](ADR-002-confidential-notes.md).
4. **Everything else is open to the agent.** A Claude Code session can read and write the rest of the vault within the limits of [ADR-004](ADR-004-autonomy-level.md).

## Consequences

- One `scripts/verify`, one `INDEX.md`, one history: simple to keep correct.
- A mistake in the deny rules exposes the confidential folder, because it is in the same repository. If that risk is too high for you, use a second vault and write a new ADR that supersedes this one.

## Action items

- [ ] Decide what counts as confidential for you, and record it in ADR-002.
