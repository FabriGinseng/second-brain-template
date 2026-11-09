---
description: Passaggio una tantum sui repo git che esistono già e il vault non conosce: li elenca e registra le tue risposte
---

Aiuta l'utente a decidere cosa fare dei repo che esistono già sul computer e il second brain non conosce. Scrivi in italiano. Non decidi mai tu se un repo è di lavoro o personale, e non scrivi nulla prima del riepilogo confermato.

1. **Dove cercare.** Chiedi ogni volta dove scansionare. Proponi, tra le cartelle della home che esistono, quelle dove di solito stanno i progetti: Developer, Desktop, Documents, AndroidStudioProjects (tre livelli di profondità; sono saltati `node_modules`, `.claude`, `.worktrees` e le cartelle nascoste). Aspetta la risposta.
2. **Elenco.** Lancia `python3 scripts/elenca-repo.py <cartelle scelte>` (su Windows `py -3`) (aggiungi `--profondita N` solo se l'utente lo chiede) e mostra l'output così com'è. Non legge né tocca il contenuto dei repo. I repo con lo stesso remote sono raggruppati: per le copie suggerisci «ignora».
3. **Risposta in un colpo.** Chiedi per ogni numero una di queste scelte, in una sola risposta (per esempio «1 sì, 2 ignora, 3-5 non ora, 6 lavoro»):
   - **sì**: lo traccio nel vault;
   - **ignora**: non chiedere più;
   - **non ora**: richiedi tra 7 giorni;
   - **lavoro**: è un repo di lavoro, non va nel vault.
   Un numero senza scelta resta da decidere. Se l'utente non sa se un repo è di lavoro, non dedurlo: lascialo da decidere.
4. **Riepilogo e conferma.** Prima di scrivere, elenca cosa farai per ogni numero e chiedi conferma. Per «sì» chiedi anche se è un progetto nuovo o un repo in più di un progetto che esiste già (per esempio il frontend di un progetto che ha già il backend): proponi i nomi di `projects/INDEX.md`. Per un progetto nuovo chiedi il nome (minuscolo con trattini; proponine uno dal nome della cartella).
5. **Scrittura**, solo dopo la conferma:
   - **sì**, progetto nuovo: segui `/nuovo-progetto <nome> <percorso>` (cartella, `STATE.md` col campo `Repo:`, riga in `projects/INDEX.md`);
   - **sì**, progetto esistente: in `projects/<nome>/STATE.md` aggiungi la riga `- **Repo:** <percorso assoluto>` subito sotto l'ultima riga `Repo:`; se l'unica riga `Repo:` è il segnaposto o `nessuno`, sostituiscila. Metti la data di oggi in *Aggiornato* e nell'ultima colonna della riga del progetto in `projects/INDEX.md` (`scripts/verify` le confronta); non cambiare altro dello STATE e resta sotto le 20 righe. Mai nella cartella riservata (ADR-001, ADR-002);
   - **ignora**, **non ora**, **lavoro**: `python3 scripts/repo-non-tracciato.py --registra ignora|non-ora|lavoro --cwd <percorso del repo>`. Per «lavoro» finisce nel vault solo l'impronta del percorso, mai il percorso né il nome: non scriverli altrove (ADR-001, ADR-002).
6. **Verifica.** Esegui `./scripts/verify` (su Windows `py -3 scripts/verify`, perché lo shebang non vale). Expected: `OK`. Se non passa, correggi solo ciò che hai scritto tu.

Il comando si può ripetere: i repo già decisi non ricompaiono. Non fare commit: lo fa `/chiudi-giornata`.
