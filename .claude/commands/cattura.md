---
description: Smista ciò che dici (più cose insieme) in piano, aree, decisioni e fatti da consolidare
argument-hint: <testo libero>
---

Registra nel vault questo, scritto a ruota libera: $ARGUMENTS

Scrivi in italiano. Spezza il testo in voci e mettine ognuna nel posto giusto:

1. **Da fare** → una riga `- [ ] [data —] #tag testo` in `docs/piano.md`, con `#tag` uguale al nome del progetto in `projects/INDEX.md` (o un argomento esistente come `#second-brain`); senza progetto chiaro, senza tag. Non duplicare una riga già presente.
2. **Anime, manga, film, libri** («ho visto la puntata 5 di X») → aggiorna o aggiungi la riga in `aree/anime-manga-film.md` (titolo, tipo, stato, dove sono, voto, note).
3. **Decisione su un progetto** → riga datata in `projects/<nome>/decisions.md` e, se cambia lo stato, riscrivi lo `STATE.md` (sotto circa 20 righe) e la riga in `projects/INDEX.md`.
4. **Fatto su di me, routine, preferenza, persona** → NON in `memory/`: aggiungi una riga datata in `inbox/cattura-YYYY-MM-DD.md` (file nuovo se manca, titolo `# Da consolidare`). Il passo di `/weekly-review` li porta in `memory/` con la tua conferma (ADR-004).
5. **Se una voce non sta in nessuno di questi** → chiedimi dove metterla, in una riga, senza indovinare.

Regole: non scrivere segreti, token o indirizzi precisi. Progetti e dettagli di lavoro non entrano nel vault (ADR-001, ADR-002): se una voce è di lavoro, non scriverla e dimmelo. Dopo le modifiche lancia `scripts/verify`, poi commit locale, solo in `docs/`, `aree/`, `projects/` e `inbox/`. Chiudi con una riga per voce: cosa e dove.
