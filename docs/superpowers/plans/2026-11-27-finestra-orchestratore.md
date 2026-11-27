# Finestra Orchestratore nella dashboard: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una scheda «Orchestratore» nella dashboard locale per gestire i modelli aperti, la frontiera, i tipi di task e per lanciare una richiesta con scelta correggibile, usando lo smistatore come unico motore (`smistatore chiedi` e `smistatore config`).

**Architecture:** un modulo backend autonomo `scripts/dashboard/orchestratore.py` che parla con lo smistatore solo lanciando il suo eseguibile (percorso in `config.json`, chiave `"smistatore"`, come `scripts/morning.py`), e un modulo frontend autonomo `orchestratore.js`. `server.py` ottiene solo le rotte e una riga di tabella. La scheda esiste solo se la chiave c'è. Niente build, niente framework (ADR-011: template pubblico, nessun percorso o nome personale nei file).

**Tech Stack:** Python 3.9 solo libreria standard, JavaScript senza dipendenze, `unittest`; lo smistatore (fase A, ramo `feat/orchestratore` del suo repo) per `chiedi`, `config`, `storico`.

**Spec:** nel repo dello smistatore, `docs/superpowers/specs/2026-11-26-orchestratore-design.md`, sezione «Finestra Orchestratore»; guida dei comandi: `docs/orchestratore.md` dello stesso repo. Il piano della fase A è `docs/superpowers/plans/2026-11-26-orchestratore-fase-a.md` (fatto).

## Global Constraints

- Python 3.9, solo libreria standard; tutto in italiano come il resto della dashboard; i test girano con `python3 -m unittest discover -s scripts -p "test_*.py"` dal vault; `python3 scripts/check` verde prima di ogni PR.
- La scheda compare solo se `config.json` ha `"smistatore"` e il file esiste ed è eseguibile. Senza, `GET /api/orchestratore` risponde `{"attivo": false}` e il menu non mostra niente.
- Le rotte `POST` passano da `do_POST`: `Host` in `HOST_OK` e intestazione `X-Azione: conferma` (già applicati a tutte). Nessuna rotta nuova li aggira.
- Mai una shell: lo smistatore e `claude` si lanciano con una lista di argomenti. Il testo della richiesta è un dato: nei comandi sta in un argomento o in un file letto da `cat`, mai dentro una stringa di shell o di AppleScript.
- Nessun percorso dal browser: il repo si sceglie da un elenco costruito dal server (i `Repo:` degli `STATE.md` non riservati), e passa per `_cartella_avviabile`. Livello e modello del lancio li ricalcola il server: il browser manda solo richiesta, repo e un tipo o livello facoltativi.
- Il lancio da dashboard funziona solo su macOS (lo smistatore usa `sandbox-exec`). Su altri sistemi la scheda dice che non è disponibile.
- Nessun segreto nei file, nelle risposte o nei log. La chiave OpenRouter resta dove la tiene lo smistatore.
- Il template non legge il registro dello smistatore direttamente: lo storico viene dal comando `smistatore storico`.
- La finestra costruisce il DOM con `textContent` e `createElement`, mai `innerHTML` con dati.
- Documentazione nello stesso commit: `README.md` cita ogni comando e rotta nuovi (`scripts/verify` lo controlla).

## Review Focus

1. Richiesta con virgolette, `«»`, `$()`, backtick, newline, `--flag` iniziale o lunghissima: arriva intatta a `smistatore`/`claude`, mai interpretata (Task 4).
2. Repo scelto fuori dall'elenco, con `..`, link simbolico verso una cartella riservata o di lavoro: rifiutato prima di toccare il disco e di chiamare lo smistatore (Task 4).
3. Il browser manda `livello: "basso"` o un modello per un repo riservato o non tracciato: il server ricalcola e la decisione dello smistatore vince (Task 4).
4. Doppio clic su «Avvia», o due schede aperte: un solo lancio (debounce come `ULTIMI_AVVII`) e niente ramo o terminale doppi (Task 4).
5. Smistatore assente, spento, lento o che stampa JSON rotto o enorme: la scheda mostra un errore chiaro, il server non va in traceback e non resta appeso (timeout, limite sull'uscita) (Task 1).

---

### Task 1: lettura dello smistatore (backend)

**Effort:** medio

**Files:**
- Create: `scripts/dashboard/orchestratore.py`, `scripts/test_orchestratore.py`
- Modify: `scripts/dashboard/server.py` (una riga in `ROTTE_GET`: `"/api/orchestratore"`)

**Interfaces:**
- Produces: `percorso_smistatore(vault: Path) -> Optional[Path]` (legge `config.json` tollerante al BOM, `expanduser`, deve essere un file eseguibile assoluto; altrimenti `None`).
- Produces: `chiama(vault: Path, argv: List[str], run=subprocess.run, timeout: int = 30) -> dict`: lancia `[percorso, *argv]` senza shell, uscita limitata a 200 KB, ritorna il JSON stampato. Errori → `OrchestratoreErrore(codice)` con codici fissi `assente`, `timeout`, `uscita` (non JSON o troppo grande), `smistatore` (esce con 2 e `{"errore": ...}`: il testo dell'errore è un dato dello smistatore e si inoltra).
- Produces: `dati(vault: Path, run=subprocess.run) -> dict`: `{"attivo": False}` se il percorso manca, altrimenti `{"attivo": True, "config": <config mostra>, "storico": <storico --limite 20>, "repo": [<nome breve>...], "sistema": sys.platform}`; un errore dello smistatore dà `{"attivo": True, "errore": <codice>}`.

- [ ] **Step 1: test che falliscono** in `scripts/test_orchestratore.py` con un eseguibile finto in una cartella temporanea. `test_senza_chiave_non_e_attivo`, `test_percorso_non_eseguibile_non_e_attivo`, `test_bom_nel_config_json`, `test_chiama_senza_shell` (la lista di argomenti arriva intatta, anche con `$(x)` e newline), `test_timeout_da_errore_timeout`, `test_uscita_non_json_da_errore_uscita`, `test_uscita_troppo_grande_da_errore_uscita`, `test_errore_dello_smistatore_si_inoltra` (esce 2 con `{"errore": "x"}`), `test_dati_attivo_con_config_e_storico`, `test_rotta_get_risponde_attivo_falso_senza_chiave` (stile di `test_dashboard_rotte.py`).
- [ ] **Step 2:** `python3 -m unittest scripts.test_orchestratore`. Expected: FAIL (modulo assente).
- [ ] **Step 3:** implementa. L'elenco `repo` è `{nome breve: cartella}` ricavato dagli `STATE.md` con le funzioni già presenti in `server.py` (`repo_di`, `_basi_riservate`, `_cartella_avviabile`); scarta chi non è avviabile. Il server tiene la mappa, il browser riceve solo i nomi.
- [ ] **Step 4:** test del modulo e suite completa. Expected: PASS.
- [ ] **Step 5: commit** `feat(dashboard): lettura dello smistatore per la scheda Orchestratore`.

### Task 2: comandi di storico nello smistatore (altro repo)

**Effort:** basso

**Files:** (repo dello smistatore, ramo `feat/orchestratore`)
- Modify: `smistatore/__main__.py`
- Create: `smistatore/storico.py`, `tests/test_storico.py`

**Interfaces:**
- Produces: `storico.ultime(log: Path = LOG, limite: int = 20) -> List[dict]`: le ultime righe `classifica` (più recenti prima) con `quando`, `repo` (solo il nome della cartella, non il percorso), `richiesta` (troncata a 200), `tipo_task`, `livello`, `backend`, `incerto`; a ogni riga si aggiunge `corretto_in` se segue una riga `correzione` della stessa richiesta e dello stesso repo. Ignora righe di altro tipo o illeggibili, mai eccezioni.
- CLI: `smistatore storico [--limite N]` (N da 1 a 100), JSON su stdout.

- [ ] **Step 1: test che falliscono.** `test_ordine_e_limite`, `test_correzione_si_aggancia_alla_sua_richiesta`, `test_non_espone_il_percorso_del_repo`, `test_righe_rotte_e_di_altro_tipo_ignorate`, `test_registro_assente_da_lista_vuota`, `test_limite_fuori_scala_da_errore`.
- [ ] **Step 2:** `... -p test_storico.py`. Expected: FAIL.
- [ ] **Step 3:** implementa; il sottocomando esce con 2 su un limite non valido.
- [ ] **Step 4:** suite completa dello smistatore. Expected: PASS.
- [ ] **Step 5: commit** `feat: smistatore storico, le ultime scelte dell'orchestratore`.

### Task 3: modifica della configurazione (rotte POST)

**Effort:** medio

**Files:**
- Modify: `scripts/dashboard/orchestratore.py`, `scripts/dashboard/server.py` (`do_POST`, un gestore `_orchestratore_config`), `scripts/test_orchestratore.py`

**Interfaces:**
- Consumes: `chiama`.
- Produces: `config_argv(corpo: dict) -> List[str]`: tabella fissa azione → argv di `smistatore config`: `tipo` (nome, descrizione, livello, modello), `tipo-rimuovi`, `frontiera`, `modello-aperto` (aggiungi/togli), `classificatore` (backend, modello, ollama). `ValueError("richiesta")` se l'azione non è in tabella, un campo non è testo, supera 200 caratteri, contiene newline o inizia con `-`. L'azione `riservato` NON è esposta: i repo riservati si cambiano solo dal terminale.
- Route: `POST /api/orchestratore/config` → 200 col JSON di `config mostra`; 400 su `ValueError`; 409 con `{"errore": <codice o testo dello smistatore>}`.

- [ ] **Step 1: test che falliscono.** `test_azioni_in_tabella_producono_l_argv_giusto`, `test_azione_sconosciuta_e_400`, `test_riservato_non_e_esposto`, `test_campo_con_trattino_iniziale_o_newline_e_400`, `test_errore_dello_smistatore_e_409_e_non_scrive`, `test_post_senza_x_azione_e_403` (come gli altri test di gestore).
- [ ] **Step 2:** i test girano. Expected: FAIL.
- [ ] **Step 3:** implementa; il corpo si legge con `_corpo_json` (4096 byte).
- [ ] **Step 4:** test del modulo e suite. Expected: PASS.
- [ ] **Step 5: commit** `feat(dashboard): modifica delle impostazioni dell'orchestratore`.

### Task 4: classificazione e lancio (superficie di esecuzione)

**Effort:** alto

**Files:**
- Modify: `scripts/dashboard/orchestratore.py`, `scripts/dashboard/server.py` (`do_POST`, due gestori), `scripts/test_orchestratore.py`

**Interfaces:**
- Consumes: `chiama`, `_cartella_avviabile`, il modo in cui `avvia_claude` apre il Terminale (file del prompt `0o600` letto da `cat`, file `.command` `0o700`, `/usr/bin/open -a Terminal`).
- Produces: `classifica(vault, richiesta, repo, run) -> dict`: valida (testo 1-4000 caratteri senza byte nulli; `repo` ∈ elenco del server), lancia `smistatore chiedi <richiesta> --repo <cartella> --solo-classifica --json` e ritorna `{tipo, livello, modello, esecutore, motivo, incerto, riservato}`.
- Produces: `avvia(vault, richiesta, repo, tipo=None, livello=None, prima=None, run, apri, adesso) -> dict`: richiama la decisione dal server con `--tipo`/`--livello` (mai quella del browser), poi: `esecutore == "paseo"` → `Popen` staccato (`start_new_session=True`, `shell=False`, uscita su un file in `percorsi.cartella_log()`) di `smistatore chiedi ... --tipo/--livello --prima`; `esecutore == "sessione"` → Terminale con `claude --model <modello> "$(cat file)"` nella cartella del repo, richiesta preceduta da uno spazio se inizia con `-`. Debounce 10 s per (repo, richiesta) con lo stesso blocco di `ULTIMI_AVVII`. Ritorna `{ok, livello, modello, esecutore}`; `RuntimeError(codice)` con codici fissi `ripetuto`, `repo`, `non_disponibile` (non macOS), `apertura`.
- Routes: `POST /api/orchestratore/classifica` e `POST /api/orchestratore/avvia`: 400 su corpo non valido, 404 `repo`, 409 sui `RuntimeError`, 501 su sistema non supportato.

- [ ] **Step 1: test che falliscono** (smistatore finto che registra gli argv; `apri` finto). `test_il_testo_arriva_intatto_come_argomento` (richiesta con `"`, `«»`, `$(touch x)`, backtick, newline, accenti: l'argv la contiene identica e il file `x` non esiste), `test_richiesta_con_trattino_non_diventa_un_flag`, `test_richiesta_vuota_o_oltre_4000_e_400`, `test_repo_fuori_elenco_e_404`, `test_repo_con_link_verso_riservato_e_404`, `test_il_livello_del_browser_non_vale` (il browser manda `livello: "basso"` per un repo riservato: parte `alto`/sessione), `test_basso_parte_staccato_senza_shell`, `test_alto_apre_il_terminale_con_il_modello_di_frontiera`, `test_doppio_clic_lancia_una_volta`, `test_non_macos_e_501`, `test_il_file_del_prompt_ha_permessi_600`.
- [ ] **Step 2:** i test girano. Expected: FAIL.
- [ ] **Step 3:** implementa. Niente copia del codice di `avvia_claude`: se serve riusare un pezzo (scrittura dei due file e apertura del Terminale), estrailo in una funzione comune in `orchestratore.py` o in `server.py` solo se i test esistenti restano verdi; altrimenti un piccolo duplicato con commento.
- [ ] **Step 4:** test del modulo e suite completa. Expected: PASS.
- [ ] **Step 5: commit** `feat(dashboard): classificazione e lancio delle richieste dell'orchestratore`.

### Task 5: la scheda (frontend)

**Effort:** medio

**Files:**
- Create: `scripts/dashboard/orchestratore.js`
- Modify: `scripts/dashboard/index.html` (voce di menu nascosta e sezione), `scripts/dashboard/dashboard.css`, `scripts/dashboard/dashboard.js` (`TITOLI`, tabella delle viste), `scripts/dashboard/server.py` (`STATICI`), `scripts/test_dashboard_html.py`

**Interfaces:**
- Consumes: le tre rotte dei Task 1, 3 e 4.
- Produces: la vista `orchestratore` con blocchi **Modelli aperti** (elenco, aggiungi/togli), **Frontiera** (campo e salva), **Tipi** (tabella con descrizione, livello, modello, salva per riga, aggiungi/rimuovi), **Richiesta** (casella, scelta del repo dall'elenco, «Classifica» che mostra tipo, livello, modello e motivo con due menu per correggerli, poi «Avvia»), **Storico** (ultime scelte; «Usa questo tipo» riempie la casella e il menu). Se `attivo` è falso il menu resta nascosto; se c'è `errore` la scheda lo dice in una riga.

- [ ] **Step 1: test che falliscono** in `scripts/test_dashboard_html.py`: la voce di menu e la sezione ci sono e il menu parte `hidden`; `/orchestratore.js` è servito; nessun `innerHTML` nel nuovo file; ogni id usato da `orchestratore.js` esiste in `index.html`; nessun percorso personale nel file.
- [ ] **Step 2:** i test girano. Expected: FAIL.
- [ ] **Step 3:** implementa il file JS (DOM con `createElement`/`textContent`, i bottoni si disattivano durante la chiamata, «Avvia» disattivato finché non c'è una classificazione) e collega vista, titolo e statico.
- [ ] **Step 4:** test della pagina e suite. Expected: PASS. Poi apri la dashboard con Playwright e controlla a mano: scheda assente senza la chiave, presente con la chiave, modifica di un tipo, classificazione senza lancio.
- [ ] **Step 5: commit** `feat(dashboard): scheda Orchestratore`.

### Task 6: documentazione, sicurezza e prova reale

**Effort:** medio

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** `README.md`: la scheda, la chiave `"smistatore"`, che il lancio è solo macOS, cosa non si può fare da dashboard (i repo riservati) e i comandi/rotte nuovi. `python3 scripts/verify` stampa `OK`.
- [ ] **Step 2:** lancia la skill `security-review` sul diff del ramo, con attenzione a Task 4; correggi i problemi Critical/Important con un test ciascuno.
- [ ] **Step 3:** `python3 scripts/check` completo. Expected: tutto verde.
- [ ] **Step 4:** prova reale con il via dell'utente: dalla scheda classifica una richiesta, cambia il tipo, avviane una `basso` (Paseo) e una `alto` (Terminale). Expected: ramo `da_rivedere` visibile, riga `classifica` e `correzione` nello storico.
- [ ] **Step 5: commit** `docs: scheda Orchestratore nel README`. La PR si apre solo con il sì dell'utente (nessun push senza).
