# second-brain-template

Un kit di partenza per un "second brain" personale: un vault Obsidian di Markdown semplice, tenuto aggiornato da un agente di programmazione ([Claude Code](https://claude.com/claude-code)) secondo regole che controlli tu. Versione inglese: [README.md](README.md).

> **Stato: v0.1.** La struttura del vault, il wizard di installazione, i controlli e la dashboard locale funzionano. I job pianificati si generano per macOS, Linux e Windows. Usato ogni giorno su macOS. Su Linux e Windows i test automatici passano in CI, ma nessuno ha ancora usato davvero l'installer lì: vedi «Sistemi supportati». Niente di questo è stato provato con un account iCloud, Nextcloud o Fastmail vero.

> **Lingue.** La documentazione è bilingue: questo file in italiano, [README.md](README.md) in inglese. I file che il sistema scrive e legge (`STATE.md`, note del giorno, testi dei comandi, messaggi di `scripts/verify`) sono in italiano nella v0.1; gli ADR di partenza sono in inglese. Tradurli non è previsto per ora.

## Cosa ottieni

- **Progetti**: un breve `STATE.md` per progetto, riscritto (mai appeso), un `decisions.md` datato e una riga in `projects/INDEX.md`.
- **Regole che l'agente segue**: un `CLAUDE.md` corto, le decisioni in `docs/adr/` (note riservate, livello di autonomia), un glossario.
- **Regole applicate da un hook**: `.claude/hooks/regole.py` con l'elenco `regole.json` (ADR-012) chiede conferma per push, PR, deploy e `rm` e rifiuta force-push e riscrittura della storia, in ogni repo dopo `scripts/installa-regole.py` (il setup lo propone). `.claude/settings.json` protegge la cartella riservata.
- **Un controllo**: `scripts/verify` verifica le regole del vault. Nessun modello, solo file.
- **Comandi e subagenti** in `.claude/`: vedi «Comandi». I testi dei comandi sono in italiano nella v0.1.
- **Una dashboard locale** (libreria standard di Python, solo `127.0.0.1`): progetti, piano, oggi, radar, servizi e limiti, post e un pannello dell'assistente. Mostra solo le pagine dei moduli che hai scelto.
- **`setup.py` e `doctor.py`**: un wizard di prima installazione fatto di moduli e un controllo di ciò che le tue scelte richiedono.

## Requisiti

- Python 3.9 o più recente e git.
- [Claude Code](https://code.claude.com/docs/en/setup) con un piano Claude a pagamento (il piano gratuito non lo include). L'agente, le bozze settimanali e la scelta del modello `claude` lo usano e consumano la quota del tuo piano.
- Facoltativi, solo se scegli la funzione che li richiede: [Ollama](https://ollama.com) per i modelli locali; Chrome, Chromium o Edge per le immagini dei post; [Obsidian](https://obsidian.md) per leggere le note con un'interfaccia comoda; n8n solo se lo preferisci al raccoglitore di novità incluso.

`python3 doctor.py` ti dice cosa manca e stampa il comando ufficiale di installazione per il tuo sistema. Non installa mai niente da solo.

## Installazione passo per passo

Gli stessi quattro passi su ogni sistema; cambiano i dettagli solo del primo.

1. **Installa Python, git e Claude Code.** Controlla con `python3 --version`, `git --version`, `claude --version` (su Windows `py -3 --version`).
2. **Prendi il template.** `git clone https://github.com/FabriGinseng/second-brain-template.git my-second-brain`, poi `cd my-second-brain`. Puoi aprire la cartella come vault in Obsidian.
3. **Lancia il wizard.** `python3 setup.py` (Windows: `py -3 setup.py`). Chiede la lingua, il tuo nome e ruolo, poi propone ogni modulo facoltativo con un sì o un no. Prima di scrivere qualcosa mostra un riepilogo e aspetta il tuo sì. Non sovrascrive mai un file che esiste.
4. **Controlla.** `python3 doctor.py`, poi `python3 scripts/verify`, che deve stampare `OK`.

Poi segui [INIZIA.md](INIZIA.md): circa 15 minuti, ogni passo dice cosa devi vedere.

### macOS

Python: `brew install python`, oppure l'installer di python.org (vedi la nota in «Se qualcosa non va»). git: `xcode-select --install`. Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`. Qui funziona tutto ciò che descrive questa guida, compreso il calendario dall'app Calendario.

### Linux

Python e git dal gestore pacchetti (per esempio `sudo apt install python3 git`). Claude Code: lo stesso comando `curl` di sopra. I job pianificati usano i timer utente di systemd: lancia una volta `loginctl enable-linger $USER` perché girino anche quando non hai una sessione aperta. Per le immagini dei post installa Chromium o Chrome.

### Windows

Scrivi `py -3` dove questa guida dice `python3`. Python: `winget install Python.Python.3.12`. git: `winget install Git.Git`. Claude Code: `irm https://claude.ai/install.ps1 | iex` in PowerShell. Windows nativo è il percorso meno provato: WSL 2 è la scelta più sicura per Claude Code finché non sarà provato davvero.

## Il wizard e i suoi moduli

`python3 setup.py --list` mostra i moduli e cosa fa ciascuno; `python3 setup.py --add <modulo>` ne aggiunge uno dopo, senza toccare ciò che hai già. Un modulo può solo farti domande e poi fare poche cose fisse (scrivere un'impostazione, creare una cartella o un file che non esiste, aggiungere una riga a `.gitignore`, aggiungere regole `deny`). Non può eseguire comandi.

| Modulo | Cosa chiede | Cosa fa |
|---|---|---|
| `core` (sempre) | nome, ruolo, lingua | `config.json`, i file di `memory/`, il tuo nome in `CLAUDE.md` |
| `riservata` | il nome di una cartella riservata | la crea, la esclude da git, vieta a Claude Code di leggerla e modificarla |
| `radar` | temi, indirizzi dei feed, chi raccoglie le novità, quale modello per ogni passo | il radar del lunedì: novità dai tuoi feed, filtrate per i tuoi progetti, una breve scheda ciascuna in `radar/` |
| `bozze` | LinkedIn, Instagram o entrambi | le bozze del lunedì in `content/`; non pubblica mai |
| `servizi` | niente | la pagina Servizi della dashboard |
| `assistente` | quale modello risponde, quale calendario, e se gli appuntamenti possono andare a Claude | il pannello dell'assistente in «Oggi» |
| `scaffold` | niente | un registro dei template di progetto, due profili (`personal`, `lavoro`) e un promemoria per i repo che il vault non conosce: vedi «Traccia i repo che hai già» |

**Dopo le domande, il wizard prepara il computer.** Rileva RAM, disco libero, CPU e scheda grafica (solo questo, e non viene inviato da nessuna parte) e con quei dati propone un modello locale: con circa 8 GB di RAM uno da 4B, con 16 GB o più `qwen3:8b`, sotto Claude o nessun modello, e non offre scaricamenti se il disco è quasi pieno. Poi, un passo alla volta, chiede prima di fare ciascuna di queste cose e mostra il comando che lancerebbe: installare Ollama o Obsidian se hai scelto qualcosa che li richiede (con `brew` su macOS, `winget` su Windows, `flatpak` su Linux), scaricare i modelli locali scelti (`ollama pull`), attivare il controllo dei segreti prima dei commit, aggiungere la barra di stato dell'uso di Claude a `~/.claude/settings.json` (se ne tiene una copia), registrare i job pianificati e lanciare il radar una volta perché la sua pagina abbia qualcosa da mostrare. Puoi dire no a qualunque passo e farlo dopo a mano. **Non** esegue gli installatori che si scaricano da internet e si passano a una shell: per Claude Code (e per Ollama su Linux) stampa il comando ufficiale e lo lanci tu. Con `--yes` o `--answers` non installa mai niente.

Puoi anche lanciare il wizard senza domande: `python3 setup.py --answers answers.json --yes`. `tests/risposte-tutti.json` è un esempio completo. `python3 setup.py --dry-run` mostra cosa succederebbe e non cambia niente. `python3 setup.py --clean-example` toglie il progetto d'esempio quando hai i tuoi.

## In locale o con Claude: chi risponde a cosa

Ogni passo che ha bisogno di un modello ha la sua impostazione in `config.json` (`modelli`), e di fabbrica è `none`: nessun modello, niente esce dal tuo computer, niente da scaricare.

| Scelta | Cosa succede | Costo |
|---|---|---|
| `none` | il radar confronta parole chiave e leggi tu ogni candidata; il pannello dell'assistente resta spento | niente |
| `ollama:<modello>` | tutto resta sul tuo computer; più lento e meno preciso | spazio su disco e RAM |
| `claude` | più preciso; il testo di quel passo esce dal tuo computer verso Anthropic | la quota del tuo piano |

Cosa viene inviato con `claude`: per il radar, i titoli delle novità e lo stack e l'obiettivo dei tuoi progetti; per l'assistente, la tua domanda e, solo se l'hai permesso al setup, i titoli e gli orari dei tuoi appuntamenti. La cartella riservata non viene inviata da nessun passo. Date, giorni della settimana e ore libere le calcola il codice, non il modello, perché un modello sbaglia.

`python3 scripts/modello.py --ram` suggerisce un modello locale per la tua RAM (circa 8 GB: un modello da 4B; 16 GB o più: `qwen3:8b`). Sono soglie, non misure sul tuo computer. `python3 scripts/modello.py --check-model <passo>` lancia tre richieste di prova fisse e ti dice se il modello scelto è adatto. Per scaricare un modello: `ollama pull <modello>`.

## L'assistente e il tuo calendario

Il pannello in «Oggi» risponde a domande sulla tua giornata («cosa scade questa settimana?», «quando sono libero domani?») e può proporre un appuntamento che confermi con un clic. Non ha strumenti né web: vede solo un testo che prepara il codice. Il modello può sbagliare, e la pagina lo dice.

Il calendario passa da `scripts/calendario.py`. Scegli un provider in `config.json` (`calendario.provider`) o nel wizard:

| Provider | Sistemi | Legge | Scrive | Serve |
|---|---|---|---|---|
| `macos` | macOS | sì | sì | l'app Calendario (con gli account Google e iCloud già dentro) |
| `ics` | tutti | sì (anche gli eventi ripetuti) | no | l'indirizzo iCal segreto di un calendario, o un file `.ics` |
| `caldav` | tutti | sì | sì | server, utente e una password per app (iCloud, Nextcloud, Fastmail) |
| `none` | tutti | no | no | niente: l'assistente dice che non conosce i tuoi appuntamenti |

Gli indirizzi e le password sono credenziali. Stanno **fuori** dal vault, che finisce in git: in `~/.config/second-brain/` su macOS e Linux, in `%APPDATA%\second-brain\` su Windows, in file leggibili solo da te (`chmod 600`; altrimenti il provider rifiuta di leggerli).

- `calendari.json` per `ics`: `{"calendari": [{"nome": "Personale", "url": "https://..."}, {"nome": "Festività", "file": "/percorso/festivita.ics"}]}`. In Google Calendar l'indirizzo sta nelle impostazioni del calendario, «Indirizzo segreto in formato iCal». Si accettano solo indirizzi `https://`.
- `caldav.json` per `caldav`: `{"server": "https://caldav.icloud.com", "utente": "tu@example.com", "password": "password per app"}`. Solo `https://`, i reindirizzamenti non si seguono, un server che indica un altro dominio è rifiutato e nessun messaggio d'errore mostra la password.

Se un calendario non si legge, l'assistente non risponde sulle ore libere, invece di dirti che sei libero quando non lo sei. Se il modello è `claude` e non l'hai permesso al setup (`moduli.assistente.calendario_al_cloud`), l'assistente non riceve i tuoi appuntamenti. Scrivere su Google Calendar fuori dal Mac non è supportato; la lettura funziona con l'indirizzo iCal segreto. Le regole di ripetizione che il lettore non capisce (per esempio «secondo martedì e quarto giovedì») compaiono come avviso in «Oggi», non sono ignorate in silenzio.

## La dashboard

`python3 scripts/dashboard/server.py`, poi apri http://127.0.0.1:8765. Ascolta solo sul tuo computer. Il menu mostra le pagine dei moduli che hai scelto; una pagina che non hai scelto non c'è. `second-brain.dashboard` (vedi «Job pianificati») la tiene in esecuzione: se si ferma, anche senza errori, riparte da sola (KeepAlive di launchd, `Restart=always` di systemd, su Windows un controllo ogni 10 minuti). Su Linux e Windows i pulsanti con lo stato dei job restano vuoti perché usano launchd.

**Icona nella barra** (`second-brain.tray`, Windows e macOS, parte al login): un pallino nell'area di notifica (Windows) o nella barra dei menu (macOS), verde quando la dashboard risponde e rosso quando no (controllo ogni 30 secondi). Il menu ha tre parti. **Dashboard**: aprila, avviala o riavviala, fermala (su Windows il controllo ogni 10 minuti la fa ripartire; su macOS resta ferma finché non la avvii o rientri). **Avvia job**: lancia subito `morning`, `feed + radar` (radar parte quando feed ha finito), `chiusura`, `bozze` o `pulizia`; un job non registrato non compare. **Notifiche**: un avviso quando la dashboard cade o torna e quando un job finisce con un errore (una volta per esecuzione), con un interruttore che le spegne finché non chiudi l'icona. **Esci** chiude solo l'icona. Solo codice nativo: `scripts/tray/tray.ps1` (Windows PowerShell 5.1 e Windows Forms) e `scripts/tray/SecondBrainTray.swift` (AppKit; `install_jobs.py` lo compila con `swiftc` in `~/Library/Application Support/second-brain/`, servono gli Xcode Command Line Tools). `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tray/tray.ps1 -SelfTest` stampa il controllo della dashboard, il menu e il comando esatto di ogni voce senza mostrare nulla. La versione macOS non è ancora stata compilata né provata. Su Windows l'icona compare al prossimo login; per vederla subito: `schtasks /run /tn second-brain.tray`.

## Quando una pagina è vuota

Un'installazione nuova parte con pagine vuote di proposito: si riempiono quando qualcosa è girato almeno una volta. Se le vedi così, non è rotto niente.

| Pagina | Si riempie quando | Cosa fare |
|---|---|---|
| Radar | il radar è girato una volta | metti i tuoi feed in `memory/feeds.md`, poi lancia `python3 scripts/feed.py` e `python3 scripts/radar.py` (Windows: `py -3`), oppure premi Radar nella pagina Avvii. Dopo ci pensano i job ogni lunedì. |
| Modello locale | Ollama è acceso e c'è un modello scaricato | avvia l'app Ollama (o `ollama serve`), poi `ollama pull <modello>`; l'elenco delle chiamate si riempie man mano che radar e assistente lo usano. Swap ed elenco dei processi esistono solo su macOS. |
| Uso di Claude | Claude Code ha salvato le percentuali d'uso e l'hai usato | aggiungi la barra di stato qui sotto a `~/.claude/settings.json`; i token al giorno vengono dalle tue sessioni di Claude Code e compaiono da soli. |
| Oggi, parte del calendario | un provider di calendario è collegato | vedi «L'assistente e il tuo calendario». |
| Avvii | i job sono registrati | `install_jobs.py`; lo stato dei job (in esecuzione, caricato) si legge da launchd, quindi lo mostra solo macOS. |

La barra di stato per la pagina dell'uso di Claude (metti il percorso vero del vault; su Windows usa `py -3 -I C:\percorso\del\vault\scripts\statusline-uso.py`):

```json
{ "statusLine": { "type": "command", "command": "python3 -I /percorso/del/vault/scripts/statusline-uso.py" } }
```

Salva solo le due percentuali d'uso e il momento del rinnovo, non il contenuto delle sessioni. Tocca il tuo `~/.claude` globale, quindi il wizard non lo fa al posto tuo.

## Comandi

Avvia `claude` nella cartella del vault e scrivi:

| Comando | Cosa fa |
|---|---|
| `/nuovo-progetto <nome> [percorso]` | crea la cartella del progetto, il suo `STATE.md` e la riga in `projects/INDEX.md`; con un percorso scrive anche il campo `Repo:` (una riga per repo, per un progetto con più repo) |
| `/morning` | il brief del mattino: progetti, novità, priorità |
| `/chiudi-giornata` | riscrive gli STATE dai tuoi commit, lancia i controlli e committa in locale; non fa mai push |
| `/weekly-review` | cosa è avanzato, cosa è fermo, cosa è trascurato |
| `/post` | trasforma una nota in una bozza LinkedIn in `content/linkedin/` |
| `/bozze-settimana` | tre bozze di post per la settimana (LinkedIn e Instagram, come hai scelto) |
| `/commit-push-pr` | commit, push e apertura di una PR per un repo di codice, chiedendoti conferma prima del push |
| `/adotta-repo` | una tantum: elenca i repo git del computer che il vault non conosce e registra le tue risposte |

Subagenti: `researcher` (legge le novità e scrive schede in `radar/`), `reviewer` (rivede la settimana, non scrive), `writer` (bozze, solo con `/post`). Nessuno può lanciarne un altro.

## Job pianificati

`scripts/jobs.json` definisce i job una volta sola; `python3 install_jobs.py` li registra nello scheduler del tuo sistema: launchd su macOS, timer utente di systemd su Linux, Utilità di pianificazione su Windows. Comincia con `python3 install_jobs.py --dry-run` per leggere cosa farebbe. `python3 install_jobs.py --uninstall` li toglie. Ogni job si può lanciare due volte senza danni, quindi recuperare dopo che il computer era spento non fa male. I job di un modulo che hai scelto si registrano; gli altri facoltativi vogliono `--all`.

| Job | Quando | Cosa fa |
|---|---|---|
| `second-brain.morning` | feriali 08:00 e al login (macOS e Windows; su Linux non ancora) | l'avvio del mattino: chiude il lavoro in sospeso, crea la nota del giorno |
| `second-brain.chiusura` | feriali 18:30 | `/chiudi-giornata`: riscrive gli STATE dai tuoi commit |
| `second-brain.pulizia` | venerdì 18:00 | controllo settimanale e rapporto |
| `second-brain.dashboard` | al login, sempre acceso | la dashboard locale |
| `second-brain.feed` (facoltativo, scelto al setup) | lunedì 07:00 | `scripts/feed.py`: raccoglie le novità di `memory/feeds.md` in `inbox/` (raccoglitore incluso; saltalo se usi n8n) |
| `second-brain.radar` (facoltativo, scelto al setup) | lunedì 07:30 | filtra le novità in `inbox/` per i tuoi progetti, con i modelli che hai scelto |
| `second-brain.bozze` (facoltativo, scelto al setup) | lunedì 08:30 | `/bozze-settimana`: tre bozze di post |
| `second-brain.tray` | al login (macOS e Windows) | l'icona nella barra (vedi «La dashboard»); «Esci» la chiude fino al prossimo login |

Il testo di una novità non è fidato: ogni titolo passa da `content-guard` (schemi di istruzioni nascoste) prima che un modello lo veda. I log stanno in `~/Library/Logs` (macOS), `$XDG_STATE_HOME/second-brain` o `~/.local/state/second-brain` (Linux), `%LOCALAPPDATA%\second-brain\logs` (Windows).

## Controlli

- `python3 scripts/verify` controlla le regole del vault: STATE corti, `INDEX` coerente, link validi, che questo README citi ogni job e ogni comando, e il registro `scaffold/` se ce l'hai. Lancialo dopo ogni modifica a uno STATE o all'indice; `/chiudi-giornata` lo lancia per te.
- `python3 doctor.py` controlla Python, git, Claude Code, `verify` e ciò che le tue scelte richiedono (Ollama acceso, ogni modello locale scaricato, RAM sufficiente, n8n se l'hai scelto). `--ci` controlla solo il necessario.
- Controllo dei segreti: `scripts/hooks/pre-commit` lancia gitleaks su ciò che stai per committare e blocca il commit se trova un segreto. Si attiva una volta per clone con `git config core.hooksPath scripts/hooks`; serve [gitleaks](https://github.com/gitleaks/gitleaks) installato (`doctor.py` mostra come).

## Traccia i repo che hai già

Il modulo `scaffold` è facoltativo. Crea `scaffold/registro.md` (i template di progetto da cui parti, vuoto), `scaffold/profili/personal.md` e `scaffold/profili/lavoro.md` (cosa fare per i progetti tuoi e per quelli di lavoro; il lavoro non ha funzionalità AI né repo remoto), `scaffold/ignorati.md` (i repo a cui hai detto «ignora» o «non ora») e `scaffold/hook-avvio.md`.

- `/adotta-repo` chiede dove cercare, elenca i repo git che il vault non conosce (quelli con lo stesso remote sono raggruppati) e registra la tua risposta per ciascuno: tracciarlo, ignorarlo, richiederlo tra 7 giorni, oppure «lavoro». Per un repo di lavoro si salva solo l'impronta del percorso, mai il percorso né il nome.
- `scripts/repo-non-tracciato.py` dice se la cartella corrente è un repo git non tracciato. Non scrive mai da solo. Con l'hook di `scaffold/hook-avvio.md` Claude Code può ricordartelo quando apri un repo così. Quell'hook tocca le impostazioni globali `~/.claude`, quindi il wizard **non** lo installa: il file mostra le due righe da incollare e decidi tu.
- Un repo è «tracciato» quando il suo percorso sta in una riga `Repo:` di un `projects/*/STATE.md`.
- Un progetto può comprendere più repo (per esempio backend, app e frontend): scrivi una riga `- **Repo:** <percorso>` per ogni repo, una sotto l'altra, un percorso assoluto per riga. `/chiudi-giornata`, l'avvio del mattino, `/weekly-review` e la dashboard leggono i commit di tutti, e nessuno risulta non tracciato. In `/adotta-repo` un «sì» può aggiungere il repo a un progetto che esiste già invece di crearne uno nuovo.

  ```markdown
  - **Repo:** /srv/codice/negozio/backend
  - **Repo:** /srv/codice/negozio/app
  - **Repo:** /srv/codice/negozio/frontend
  ```

## Agenti da remoto dal telefono (facoltativo)

Con [Paseo](https://paseo.sh), un daemon open source con app iOS e Android, puoi avviare e seguire dal telefono agenti Claude Code sui tuoi progetti. Il second brain prepara il contesto e il prompt; tu avvii l'agente dall'app; la chiusura serale vede i suoi commit come sempre. Nel vault non cambia nulla. Leggi [docs/remote-agents-paseo.md](docs/remote-agents-paseo.md) (in inglese) **prima di installarlo**: le impostazioni predefinite di Paseo (nessuna password, strumenti di controllo degli agenti, aggiornamenti Windows non firmati) vanno irrobustite, e la guida elenca le impostazioni esatte per Windows, macOS e una VM Linux.

## Sistemi supportati

| Parte | macOS | Linux | Windows |
|---|---|---|---|
| Vault, `scripts/verify`, `setup.py`, `doctor.py` | sì | i test CI passano | i test CI passano |
| Dashboard | sì | in parte (niente stato dei job) | in parte |
| Calendario: `macos` | sì | no | no |
| Calendario: `ics` e `caldav` | provati con dati finti e un server finto | uguale | uguale |
| Job pianificati (`install_jobs.py`) | sì | file generati e testati, non ancora registrati davvero | uguale |
| Job del mattino (`second-brain.morning`) | sì | non ancora | file generato e testato, non ancora registrato davvero |
| Icona nella barra (`second-brain.tray`) | scritta, non provata (mai compilata) | no | provata: self-test e un avvio vero, voci del menu non ancora cliccate |

«I test CI passano» vuol dire test automatici su un computer pulito, non che qualcuno l'abbia usato. Se lo provi su Linux o Windows, segnala cosa si è rotto.

## Privacy

Claude Code invia al modello i file che legge. Metti le note riservate nella cartella creata dal modulo `riservata` (esclusa da git e bloccata da regole `deny`) e leggi [ADR-002](docs/adr/ADR-002-confidential-notes.md) per i limiti di quel blocco: le regole non fermano uno script che lanci tu. Il tuo nome, le note e i file di memoria restano nella tua copia: `setup.py` li scrive dai file `*.example.md` e git li ignora. Gli indirizzi dei calendari e le password stanno fuori dal vault. La dashboard ascolta solo su `127.0.0.1`.

## Se qualcosa non va

- **`python3` non trovato su Windows**: usa `py -3`.
- **Errore di certificato nel leggere i feed su macOS**: il Python di python.org non ha i certificati; il raccoglitore ripiega su quelli di sistema. Se ancora fallisce, lancia `Install Certificates.command` dalla cartella di Python in Applicazioni.
- **`doctor.py` dice che Ollama manca o non è acceso**: avvia l'app Ollama, oppure scegli `none` per quel passo con `python3 setup.py --add radar`.
- **Manca un modello**: `ollama pull <modello>` (il nome è nel messaggio di `doctor.py`).
- **L'assistente dice che non conosce i tuoi appuntamenti**: non c'è un calendario collegato, il calendario non si legge, oppure il modello è `claude` e non hai permesso di inviare gli appuntamenti. `config.json` mostra `calendario.provider` e `moduli.assistente`.
- **«è leggibile da altri utenti»**: `chmod 600` su quel file.
- **Su Windows `./scripts/verify` non parte dentro Claude Code** (Git Bash non riesce a lanciare il `python3` dello shebang): usa `py -3 scripts/verify`. I comandi e i permessi lo prevedono già.
- **Su Windows i job girano senza finestra**: l'Utilità di pianificazione li avvia con `conhost.exe --headless`, quindi non compare nessuna finestra CMD vuota. Se un job registrato prima di questa modifica ne apre ancora una, lancia di nuovo `py -3 install_jobs.py` per registrarlo di nuovo.
- **Perché il job della tray usa `-ExecutionPolicy Bypass`**: il criterio predefinito di Windows (Restricted) blocca ogni script, anche `tray.ps1`. Il bypass vale solo per quel processo PowerShell e solo per quel file di questo repo; non cambia il criterio del sistema. Firmare lo script lo eviterebbe, ma per ora è fuori dal perimetro. Se la tua organizzazione lo vieta, togli solo questo job: `py -3 install_jobs.py --uninstall --only tray`.
- **`scripts/verify` protesta**: il messaggio nomina il file e la riga; correggi e rilancialo.
- **I job non girano su Linux quando sei uscito**: `loginctl enable-linger $USER`.

## Aggiornare e disinstallare

Aggiornare: `git pull`, poi `python3 doctor.py` e `python3 scripts/verify`. I tuoi file sono ignorati da git o non toccati dal pull. Disinstallare: `python3 install_jobs.py --uninstall`, poi cancella la cartella. Su macOS cancella anche `~/Library/Application Support/second-brain/` (l'icona compilata). Claude Code e Ollama hanno le loro guide di disinstallazione.

## Licenza

MIT, vedi `LICENSE`. Per segnalare dati personali finiti qui per errore, vedi `SECURITY.md`.
