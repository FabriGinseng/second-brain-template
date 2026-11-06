#!/usr/bin/env python3
"""Attività dei repo dei progetti dall'ultima volta che il loro STATE è cambiato nel vault.

Uso: scripts/attivita-progetti.py [--giorni N]
Senza opzioni stampa solo i progetti con commit nuovi dall'ultimo cambio dello STATE (niente output = niente da
aggiornare). Con --giorni N guarda invece gli ultimi N giorni, per la revisione settimanale.
Sola lettura dei repo, tutti i branch (il lavoro sta anche in feat/* e nei worktree). Non tocca la cartella riservata:
cerca solo projects/<nome>/STATE.md (ADR-001, ADR-002).
"""
import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
REPO = re.compile(r"^- \*\*Repo:\*\* (.+)$", re.M)
MAX_COMMIT = 30
MAX_FILE = 15


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
    return r.stdout


def ultimo_cambio_state(nome, vault=VAULT):
    """Quando lo STATE del progetto è stato committato l'ultima volta nel vault (0 se mai)."""
    ts = _git(vault, "log", "-1", "--format=%ct", "--", "projects/%s/STATE.md" % nome).strip()
    return int(ts) if ts else 0


def attivita(repo, da_ts):
    """Commit (non di merge, tutti i branch) del repo dopo da_ts e file di wayfinder toccati. Righe di testo."""
    da = datetime.fromtimestamp(da_ts).isoformat(timespec="seconds")
    log = _git(repo, "log", "--branches", "--source", "--no-merges", "--since=" + da, "-%d" % MAX_COMMIT,
               "--format=%ct\t%S\t%s").splitlines()
    righe = []
    for r in log:
        ts, ramo, messaggio = r.split("\t", 2)
        righe.append("- %s %s: %s" % (datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M"),
                                      ramo.removeprefix("refs/heads/"), messaggio))
    if righe:
        file = sorted({f for f in _git(repo, "log", "--branches", "--no-merges", "--since=" + da, "--name-only",
                                       "--format=", "--", "docs/wayfinder").splitlines() if f})
        if file:
            righe.append("File di wayfinder toccati: " + ", ".join(file[:MAX_FILE]))
    return righe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giorni", type=int)
    giorni = ap.parse_args().giorni
    for stato in sorted((VAULT / "projects").glob("*/STATE.md")):
        nome = stato.parent.name
        m = REPO.search(stato.read_text(encoding="utf-8"))
        if not m or m.group(1).strip().lower() in ("nessuno", "none", "-", ""):  # «nessuno» è il segnaposto dei progetti senza repo
            continue
        try:
            righe = attivita(m.group(1).strip(), time.time() - giorni * 86400 if giorni else ultimo_cambio_state(nome))
        except (OSError, subprocess.SubprocessError) as e:
            print("%s: repo non leggibile (%s)" % (nome, e), file=sys.stderr)
            continue
        if righe:
            print("## %s (repo %s)" % (nome, m.group(1).strip()))
            print("\n".join(righe))


if __name__ == "__main__":
    # Callers read this output as UTF-8. Under -I PYTHONUTF8 is ignored, so on Windows a pipe would get the ANSI
    # code page: an accent in a commit message would break the reader, a character outside it would crash here.
    sys.stdout.reconfigure(encoding="utf-8")
    main()
