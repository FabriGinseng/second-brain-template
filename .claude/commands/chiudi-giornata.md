---
description: Chiude la giornata: riscrive gli STATE toccati, aggiorna l'indice, verifica e committa in locale
---

Chiudi la giornata di lavoro nel vault. Scrivi in italiano.

1. **Cosa è stato fatto.** Fonti, in quest'ordine:
   - *Attività dei repo*: i commit dei repo dei progetti dall'ultimo cambio del loro STATE, tutti i branch, con i file di wayfinder toccati. Sta in `$ARGUMENTS`. Se `$ARGUMENTS` è vuoto e c'è qualcuno davanti, ricavala con `python3 -I scripts/attivita-progetti.py` (su Windows `py -3 -I scripts/attivita-progetti.py`). Se la sezione dice "nessuna", non ci sono commit nuovi.
   - `git log` del vault di oggi e la conversazione.
   Se restano dubbi su un punto, chiedi all'utente prima di scrivere.
   **Se la sessione è non presidiata** (lanciata da uno script, senza nessuno davanti): non fare domande. L'attività dei repo conta come dato nuovo. Senza attività dei repo e senza altri dati non toccare gli STATE. Dopo il punto 4 fermati: verifica e commit li fa `scripts/chiudi-giornata.py`, perché nelle run non presidiate Bash è negato e il tentativo di lanciarli si perde in un errore.
2. **STATE.** Per ogni progetto con attività dei repo riscrivi `projects/<nome>/STATE.md` da zero, usando `templates/STATE.md`, e metti sempre la data di oggi in *Aggiornato*. Massimo 20 righe. Tieni tutte le righe `Repo:`, una per repo, così come sono: con più repo l'attività ha ogni riga preceduta da `[nome-del-repo]`. Ciò che non è più attuale va in `projects/<nome>/decisions.md`, con la data.
   - *Dove sono*: riassumi cosa mostrano i commit e i ticket di wayfinder chiusi o aperti. Non inventare.
   - *Prossimi passi*: togli quelli che i commit mostrano chiusi e aggiungi solo quelli che i ticket aperti indicano con chiarezza. Altrimenti lasciali come sono.
   - *Blocchi aperti*: lasciali com'erano, salvo un commit che li risolve in modo evidente.
   - Se un punto è dubbio, non indovinare: scrivilo in *Da confermare* del `daily/` di oggi.
   - Non toccare mai la cartella riservata dei progetti (ADR-001, ADR-002): lì lo STATE si scrive a mano.
3. **Decisioni.** Appendi a `decisions.md` di ogni progetto le decisioni prese oggi, con la data.
4. **Indice.** Aggiorna la riga di ogni progetto toccato in `projects/INDEX.md`, con la data di oggi nell'ultima colonna.
5. **Verifica** (solo con qualcuno davanti). Esegui `./scripts/verify` (su Windows `py -3 scripts/verify`, perché lo shebang non vale). Se esce con 1, leggi l'elenco, correggi i file indicati e rilancia. Al massimo tre tentativi in tutto.
6. **Commit** (solo con qualcuno davanti). Solo se `scripts/verify` è passato (exit 0):
   ```bash
   git add -A && git commit -m "chiusura YYYY-MM-DD" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"
   ```
   Con la data di oggi. Non fare push.
7. **Se la verifica non passa dopo tre tentativi.** Non committare. Scrivi il problema, con i file interessati, nella sezione "Da confermare" del `daily/` di oggi, e fermati.

Non toccare `CLAUDE.md`, `memory/` e `docs/adr/`: non rientrano in questa routine.
