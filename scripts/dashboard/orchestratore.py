"""Scheda Orchestratore: parla con lo smistatore solo lanciando il suo eseguibile, il cui percorso sta in config.json
({"smistatore": "~/.../bin/smistatore"}, la stessa chiave di scripts/morning.py). Mai una shell; l'uscita è JSON e ha un tetto.
Senza la chiave la scheda non esiste. Nessun percorso personale in questo file (template pubblico)."""
import json
import os
import subprocess
import sys
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
        return {"attivo": True, "config": chiama(vault, ["config", "mostra"], run), "storico": chiama(vault, ["storico", "--limite", "20"], run),
                "repo": sorted(repo()), "sistema": sys.platform}
    except OrchestratoreErrore as e:
        return {"attivo": True, "errore": e.codice}
