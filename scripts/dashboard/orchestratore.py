"""Scheda Orchestratore: parla con lo smistatore solo lanciando il suo eseguibile, il cui percorso sta in config.json
({"smistatore": "~/.../bin/smistatore"}, la stessa chiave di scripts/morning.py). Mai una shell; l'uscita è JSON e ha un tetto.
Senza la chiave la scheda non esiste. Nessun percorso personale in questo file (template pubblico)."""
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

MASSIMO_USCITA = 200_000
TIMEOUT = 30


class OrchestratoreErrore(Exception):
    """`codice` è uno fra assente, timeout, uscita, smistatore; `testo` è l'errore stampato dallo smistatore, se c'è (un dato suo)."""

    def __init__(self, codice, testo=None):
        super().__init__(codice)
        self.codice, self.testo = codice, testo


def percorso_smistatore(vault):
    """L'eseguibile indicato da config.json, o None: chiave assente, percorso non assoluto, non un file, non eseguibile."""
    try:
        config = json.loads((Path(vault) / "config.json").read_text(encoding="utf-8-sig"))  # -sig: un BOM di un editor Windows
        valore = config.get("smistatore") if isinstance(config, dict) else None
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(valore, str) or not valore.strip():
        return None
    p = Path(os.path.expanduser(valore.strip()))
    return p if p.is_absolute() and p.is_file() and os.access(p, os.X_OK) else None


def chiama(vault, argv, run=subprocess.run, timeout=TIMEOUT):
    """Lancia `smistatore *argv` (lista, senza shell) e dà il JSON che stampa; OrchestratoreErrore su ogni altro esito."""
    p = percorso_smistatore(vault)
    if p is None:
        raise OrchestratoreErrore("assente")
    try:
        r = run([str(p), *argv], capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise OrchestratoreErrore("timeout") from None
    except OSError:
        raise OrchestratoreErrore("assente") from None
    if len(r.stdout) > MASSIMO_USCITA:  # ponytail: l'uscita è già in memoria; il tetto evita di girarla al browser
        raise OrchestratoreErrore("uscita")
    try:
        dati = json.loads(r.stdout)
    except ValueError:
        raise OrchestratoreErrore("uscita") from None
    if r.returncode != 0:
        testo = dati.get("errore") or dati.get("motivo") if isinstance(dati, dict) else None
        raise OrchestratoreErrore("smistatore", testo if isinstance(testo, str) else None)
    return dati


def dati(vault, run=subprocess.run, repo=lambda: {}):
    """Quello che la scheda mostra. `repo`: funzione che dà {nome breve: cartella}; al browser vanno solo i nomi."""
    if percorso_smistatore(vault) is None:
        return {"attivo": False}
    try:
        return {"attivo": True, "config": chiama(vault, ["config", "mostra"], run), "storico": chiama(vault, ["storico", "--limite", "50"], run),
                "repo": sorted(repo()), "sistema": sys.platform}
    except OrchestratoreErrore as e:
        return {"attivo": True, "errore": e.codice}


# azione -> (parole del comando, campi posizionali in ordine, {campo facoltativo: opzione}). I repo riservati NON ci sono:
# si cambiano solo dal terminale, così una pagina non può togliere la protezione.
AZIONI = {
    "tipo": (["tipo"], ["nome"], {"descrizione": "--descrizione", "livello": "--livello", "modello": "--modello"}),
    "tipo-rimuovi": (["tipo-rimuovi"], ["nome"], {}),
    "frontiera": (["frontiera"], ["modello"], {}),
    "modello-aperto": (["modello-aperto"], ["verbo", "id"], {}),
    "classificatore": (["classificatore"], [], {"backend": "--backend", "modello": "--modello", "ollama": "--ollama"}),
}
VERBI = {"aggiungi", "togli"}
MASSIMO_CAMPO = 200


def _campo(valore, vuoto=False):
    """Un testo corto senza a capo né byte nulli che non inizia con «-» (diventerebbe un'opzione dello smistatore)."""
    if (not isinstance(valore, str) or len(valore) > MASSIMO_CAMPO or (not valore and not vuoto) or valore.startswith("-")
            or any(c in valore for c in "\n\r\x00")):
        raise ValueError("richiesta")
    return valore


def config_argv(corpo):
    """Gli argomenti di `smistatore config ...` per una richiesta del browser, o ValueError("richiesta")."""
    if not isinstance(corpo, dict) or corpo.get("azione") not in AZIONI:
        raise ValueError("richiesta")
    parole, posizionali, facoltativi = AZIONI[corpo["azione"]]
    if set(corpo) - {"azione", *posizionali, *facoltativi}:
        raise ValueError("richiesta")
    argv = list(parole)
    for campo in posizionali:
        argv.append(_campo(corpo.get(campo)))
    if corpo["azione"] == "modello-aperto" and corpo["verbo"] not in VERBI:
        raise ValueError("richiesta")
    for campo, opzione in facoltativi.items():
        if campo in corpo:
            argv += [opzione, _campo(corpo[campo], vuoto=campo == "descrizione")]
    return argv


def senza_home(testo):
    """Il testo di un errore dello smistatore può nominare un file dell'utente: la cartella di casa diventa «~»."""
    return testo.replace(str(Path.home()), "~") if isinstance(testo, str) else testo


def cambia_config(vault, argv, run=subprocess.run):
    """Applica un cambio con `smistatore config *argv` e dà la configurazione risultante."""
    return chiama(vault, ["config", *argv], run)


MASSIMO_RICHIESTA = 4000
DEBOUNCE = 10  # secondi: un doppio clic su «Avvia» è un lancio solo
ULTIMI = {}
BLOCCO = threading.Lock()


def _richiesta(testo):
    """Il testo da dare allo smistatore: 1-4000 caratteri senza byte nulli. Se inizia con «-» si antepone uno spazio, così non
    può diventare un'opzione né dello smistatore né di claude."""
    if not isinstance(testo, str) or not testo.strip() or len(testo) > MASSIMO_RICHIESTA or "\x00" in testo:
        raise ValueError("richiesta")
    return " " + testo if testo.startswith("-") else testo


def _cartella(repo, elenco):
    """La cartella di un repo dell'elenco costruito dal server: il nome non è mai un percorso, solo una chiave."""
    if not isinstance(repo, str) or repo not in elenco:
        raise LookupError("repo")
    return Path(elenco[repo])


def classifica(vault, richiesta, repo, elenco, tipo=None, livello=None, run=subprocess.run):
    """La scelta dello smistatore per una richiesta, senza lanciare niente. `tipo`/`livello`: la correzione dell'utente, che lo
    smistatore applica salvo che il repo sia riservato (allora alto)."""
    testo, cartella = _richiesta(richiesta), _cartella(repo, elenco)
    argv = ["chiedi", testo, "--repo", str(cartella), "--solo-classifica"]
    if tipo is not None:
        argv += ["--tipo", _campo(tipo)]
    elif livello is not None:
        argv += ["--livello", _campo(livello)]
    return chiama(vault, argv, run)


def _apri_terminale(cartella, smistatore, scelta, richiesta, cartella_avvii, run):
    """Un terminale che lancia `smistatore chiedi` nella cartella del repo (e lo smistatore avvia claude: un solo motore, che scrive
    la sua riga di registro). La richiesta sta in un file 0600 letto da `cat`: non finisce mai in una stringa di shell. Percorsi e
    argomenti della scelta sono quotati."""
    cartella_avvii.mkdir(mode=0o700, parents=True, exist_ok=True)
    for f in cartella_avvii.iterdir():  # file di avvii vecchi di una settimana
        if f.is_file() and f.stat().st_mtime < time.time() - 7 * 86400:
            f.unlink()
    base = cartella_avvii / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + os.urandom(4).hex())
    file_prompt, file_comando = base.with_suffix(".txt"), base.with_suffix(".command")
    comando = "#!/bin/zsh -l\ncd %s && exec %s chiedi \"$(cat %s)\" --repo %s %s\n" % (
        shlex.quote(str(cartella)), shlex.quote(str(smistatore)), shlex.quote(str(file_prompt)), shlex.quote(str(cartella)),
        " ".join(shlex.quote(a) for a in scelta))
    for file, contenuto, modo in ((file_prompt, richiesta, 0o600), (file_comando, comando, 0o700)):
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, modo)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenuto)
    try:
        r = run(["/usr/bin/open", "-a", "Terminal", str(file_comando)], check=False, timeout=10)
    except (subprocess.SubprocessError, OSError):
        raise RuntimeError("apertura") from None
    if r.returncode != 0:
        raise RuntimeError("apertura")


def avvia(vault, richiesta, repo, elenco, tipo=None, livello=None, prima=None, run=subprocess.run, lancia=subprocess.Popen,
          cartella_avvii=None, cartella_log=None, adesso=time.monotonic, sistema=None):
    """Lancia la richiesta dove la decisione dello smistatore dice. La decisione la ricalcola sempre il server: del browser
    contano solo richiesta, repo e un tipo o livello scelti, che lo smistatore può scavalcare (repo riservato → alto).
    basso/medio: `smistatore chiedi` staccato (su Paseo); alto: Terminale che lancia `smistatore chiedi` (che avvia claude). Solo macOS.
    NotImplementedError: altro sistema. ValueError: richiesta. LookupError: repo. RuntimeError con codice: ripetuto, apertura."""
    sistema = sistema or sys.platform
    if sistema != "darwin":
        raise NotImplementedError("solo macOS")
    testo, cartella = _richiesta(richiesta), _cartella(repo, elenco)
    d = classifica(vault, richiesta, repo, elenco, tipo=tipo, livello=livello, run=run)
    if not isinstance(d, dict) or d.get("esecutore") not in ("paseo", "sessione") or not isinstance(d.get("modello"), str):
        raise OrchestratoreErrore("uscita")
    with BLOCCO:
        chiave = (repo, testo)
        if chiave in ULTIMI and adesso() - ULTIMI[chiave] < DEBOUNCE:
            raise RuntimeError("ripetuto")
        ULTIMI[chiave] = adesso()
    scelta = ["--tipo", d["tipo"]] if d.get("tipo") else ["--livello", d["livello"]]  # la decisione è del server, non del browser
    if prima is not None:
        scelta += ["--prima", _campo(prima)]
    smistatore = percorso_smistatore(vault)
    if d["esecutore"] == "sessione":
        _apri_terminale(cartella, smistatore, scelta, testo, Path(cartella_avvii), run)
    else:
        cartella_log = Path(cartella_log or cartella_avvii)
        cartella_log.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(cartella_log / ("orchestratore-%s.log" % datetime.now().strftime("%Y%m%d-%H%M%S-%f")), "ab") as f:
            lancia([str(smistatore), "chiedi", testo, "--repo", str(cartella), *scelta], stdin=subprocess.DEVNULL, stdout=f,
                   stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    return {"ok": True, "tipo": d.get("tipo"), "livello": d.get("livello"), "modello": d["modello"], "esecutore": d["esecutore"]}
