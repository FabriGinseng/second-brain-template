---
description: Crea un nuovo progetto nel vault: cartella, STATE dal template e riga in INDEX
argument-hint: <nome-in-minuscolo-con-trattini> [percorso-del-repo]
---

Crea il progetto `$ARGUMENTS` nel vault. Scrivi in italiano.

Gli argomenti sono il nome (prima parola) e, facoltativo, il percorso di un repo (seconda parola).

1. **Nome.** Il nome deve contenere solo lettere minuscole, cifre e trattini, e non deve iniziare con un trattino. Se non rispetta questa regola, fermati, dillo e proponi una versione corretta. Non creare nulla.
   **Percorso, se c'è.** Espandi `~` e risolvi il percorso in assoluto. Deve essere una cartella che contiene un repo git (`git -C <percorso> rev-parse --show-toplevel`): se non lo è, fermati e dillo, senza creare nulla. Se l'utente dice che è un repo di lavoro, fermati: i percorsi di lavoro non si scrivono nel vault (ADR-001, ADR-002).
2. **Esistenza.** Se `projects/<nome>/` esiste già, fermati e dillo. Non toccare né lo `STATE.md` né la riga in `projects/INDEX.md`.
3. **STATE.** Crea `projects/<nome>/STATE.md` (la cartella nasce con il file) a partire da `templates/STATE.md`: sostituisci `{{title}}` con il nome del progetto e `{{date:YYYY-MM-DD}}` con la data di oggi. Se c'è il percorso, scrivilo assoluto nel campo `Repo:` (la riga `- **Repo:** <percorso>`); senza percorso lascia il segnaposto. Un progetto fatto di più repo (per esempio backend, app e frontend) ha una riga `- **Repo:**` per ognuno, una sotto l'altra, un percorso assoluto per riga: se l'utente ne nomina altri, controlla ognuno come al punto 1 (repo git, non di lavoro) e aggiungi le sue righe sotto la prima. Lascia vuoti gli altri campi da compilare. Non creare altre sottocartelle: `decisions.md` nasce quando c'è la prima decisione.
4. **Indice.** Aggiungi in fondo alla tabella di `projects/INDEX.md` una riga costruita da `templates/project-index-row.md`, con la data di oggi.
5. **Verifica.** Esegui `./scripts/verify` (su Windows `py -3 scripts/verify`, perché lo shebang non vale). Expected: `OK`. Se non passa, correggi solo ciò che hai creato tu.

Non fare commit: lo fa `/chiudi-giornata`.
