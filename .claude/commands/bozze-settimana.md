---
description: Prepara 3 bozze di post per la settimana, LinkedIn e Instagram, dal lavoro dei progetti
---

Prepara le bozze di post della settimana. Scrivi in italiano, in prima persona, con il tono di `memory/about-me.md`: caldo, curioso, concreto.

**Fonti, solo queste.** L'attività dei repo degli ultimi sette giorni sta in `$ARGUMENTS`. Se `$ARGUMENTS` è vuoto o dice "nessuna", leggi `projects/INDEX.md` e gli `STATE.md` dei progetti, ma non la cartella riservata (ADR-001, ADR-002): niente progetti di lavoro, niente nomi di clienti. Guarda anche i nomi dei file già presenti in `content/linkedin/` e `content/instagram/`, per non ripetere un tema già trattato.

**Social attivi.** Se esiste `config.json`, leggi `moduli.bozze.social`: `linkedin` o `instagram` vuol dire scrivere solo per quel social, `both` (o chiave assente, o nessun `config.json`) per entrambi. Negli altri passi di questo comando, ignora il social non attivo: niente file per lui.

**Scegli 3 temi diversi** tra loro (una decisione presa, una cosa costruita, una cosa imparata). Per ogni tema crea due file nuovi con lo stesso nome `YYYY-MM-DD-<tema>.md`, con la data di oggi: uno in `content/linkedin/`, uno in `content/instagram/`.

**Progetto.** Se la bozza parla di un progetto di `projects/INDEX.md` (mai uno del lavoro), scrivi subito sotto il titolo la riga `Progetto: <nome>`, con il nome esatto dell'INDEX. La dashboard la usa per mostrare la bozza anche sul nodo di quel progetto. Se non riguarda un progetto, niente riga.

**LinkedIn.** Titolo `# Bozza LinkedIn: ...`. Apertura forte nelle prime due righe, una storia con un punto preciso, una conclusione utile, una domanda finale alla community, al massimo tre hashtag. Testo da 900 a 1.300 caratteri circa.

**Instagram.** Titolo `# Bozza Instagram: ...`. Didascalia corta (al massimo 600 caratteri), l'idea da mostrare in un carosello di 4-6 immagini elencate una per riga, al massimo tre hashtag. Nessun link nella didascalia.

**Immagine.** L'ultima riga di ogni file è `Immagine: <titolo breve> | <riga 1> | <riga 2> | <riga 3>`, con al massimo 4 righe, ognuna con un fatto o una cifra che sta già nei dati. Lo script la disegna in PNG.

**Regole.**
- Usa solo fatti che stanno nelle fonti. Non inventare difficoltà, risultati, numeri, durate o clienti. Se un dato non c'è, non scriverlo.
- Racconta quello che hai costruito e imparato: niente vendita, niente appelli a chi assume.
- Se le fonti non bastano per tre temi, scrivine meno e dì quanti.
- Non pubblicare, non fare commit, non modificare file esistenti. Verifica e commit li fa `scripts/prepara-bozze.py`.

Alla fine elenca i file creati, uno per riga.
