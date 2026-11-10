---
description: Revisione settimanale: cosa è avanzato, cosa è fermo, cosa è trascurato
---

Scrivi la revisione della settimana in `daily/YYYY-Www-review.md`, con `YYYY-Www` la settimana ISO corrente. Scrivi in italiano.

1. **Dati.** Raccogli tu, perché il subagente non ha Bash:
   - `git log --since="7 days ago"` del vault;
   - `projects/INDEX.md` e gli `STATE.md` dei progetti che l'indice elenca;
   - i commit degli ultimi sette giorni nei repo dei progetti, tutti i branch: `python3 -I scripts/attivita-progetti.py --giorni 7` (su Windows `py -3 -I scripts/attivita-progetti.py --giorni 7`). Il lavoro vero sta nei repo, non nel vault: senza questo ogni progetto sembrerebbe fermo.
2. **Subagente `reviewer`.** Passagli nella richiesta tutti i dati del punto 1 e usa la sua risposta come bozza di *Avanzato*, *Fermo* e *Trascurato*. Non gli far leggere altri file.
3. **Controllo.** Prima di scrivere, verifica che ogni riga di *Avanzato* abbia dietro un commit o una modifica dei dati. Un progetto è *Fermo* solo se non ha commit né nel vault né nel suo repo da più di sette giorni. Non inventare progressi: se non ci sono commit nella settimana, scrivi che non ci sono progressi registrati.
4. **Scrivi il file** con tre sezioni con questi titoli: *Avanzato*, *Fermo*, *Trascurato*.
5. **Consolida i fatti.** Leggi i `inbox/cattura-*.md` con voci non ancora consolidate (le righe senza «(consolidato)»). Proponi le modifiche a `memory/about-me.md` e `memory/preferences.md` (una riga per fatto, senza duplicare ciò che c'è già, senza indirizzi precisi, segreti o dettagli di lavoro) e chiedi un solo sì per applicarle. Con il sì scrivile e segna le voci «(consolidato YYYY-MM-DD)»; senza il sì (o in una run non presidiata) mettile nella sezione *Da confermare* della review e non toccare `memory/` (ADR-004).

Non fare commit.
