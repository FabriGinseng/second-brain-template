# ADR-005 – Relevance filter for the radar

- **Status:** Accepted (template default: edit it to match your own situation)
- **Date:** <YYYY-MM-DD>

## Context

The radar reads the news from your feeds and keeps what matters for your projects. Sending every title to a cloud model costs money and sends your project names out of the computer. You need a filter that decides what is worth a model call.

## Decision

1. **Two stages.** Stage 1 compares each title with your projects, by embeddings (or by keywords when no embedding model is chosen), with a similarity threshold (`0.5` to start, to be tuned on your own data). Stage 2 asks a model to judge only what passed stage 1.
2. **The model is chosen per step in `config.json`.** `modelli.radar_embedding` (stage 1) accepts `none` or `ollama:<model>`; `modelli.radar_giudizio` (stage 2) accepts `none`, `claude` or `ollama:<model>`. `none` is the default: no model, no cloud, no download. `scripts/modello.py` reads the choice; the radar never calls a provider directly.
3. **Local means local.** With `ollama:<model>` nothing leaves the computer. With `claude` (stage 2 only), the titles and your project summaries go to the cloud; choose it knowingly.
4. **Tune it.** The votes "false discard" and "right discard" in the dashboard feed the tuning script; change the threshold only with data.

## Consequences

- With `none` for the judgment step, the radar still runs: stage 2 is skipped and the cards come from stage 1 only.
- Stage 2 needs a model: a local one (`python3 scripts/modello.py --ram` suggests one for your RAM) or Claude.
- If you add a provider, add it in `scripts/modello.py` and write a new ADR.

## Action items

- [ ] Pick the model for each radar step in `config.json`.
- [ ] After a few weeks, tune the threshold with your votes.
