#!/usr/bin/env python3
"""Dice se la cartella corrente è un repo git che il vault non conosce, e salva la risposta dell'utente.

Uso: scripts/repo-non-tracciato.py [--cwd DIR]
         Senza opzioni (è il comando dell'hook SessionStart) stampa due righe solo se il repo non è tracciato,
         altrimenti niente. Non scrive mai e non fallisce mai in modo visibile: nel dubbio tace.
     scripts/repo-non-tracciato.py --registra ignora|non-ora|lavoro [--cwd DIR]
         Salva la risposta in scaffold/ignorati.md. Per «lavoro» salva solo l'impronta del percorso, mai il
         percorso (ADR-002: nel vault non devono finire nomi di clienti).

Un repo è tracciato se il suo percorso è in una riga «Repo:» di un projects/*/STATE.md (un progetto può averne più
d'una, una per repo). La cartella riservata del
lavoro non si legge (ADR-001, ADR-002). Un worktree conta come il suo repo principale.
"""
import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
PRIVATE_DIRS = {"lavoro", "_private"}
REPO = re.compile(r"^- \*\*Repo:\*\* (.+)$", re.M)
PAUSA_GIORNI = 7
SCELTE = {"ignora": "ignora", "lavoro": "lavoro", "non-ora": "non ora"}
INTESTAZIONE = "# Repo ignorati o in pausa\n\n| Repo | Scelta | Fino al | Data |\n|---|---|---|---|\n"


def escludi_di_default():
    """Cartelle in cui un repo non è un progetto: temporanee di sistema e la cartella di Claude."""
    return (Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve(), Path.home() / ".claude")


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", timeout=5, check=True)
    return r.stdout.strip()


def repo_principale(cwd):
    """Il repo git che contiene cwd (un worktree è ricondotto al repo principale), o None."""
    try:
        comune = Path(_git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        radice = Path(_git(cwd, "rev-parse", "--show-toplevel"))
    except (OSError, subprocess.SubprocessError):
        return None
    return (comune.parent if comune.name == ".git" else radice).resolve()


def impronta(repo):
    return "sha256:" + hashlib.sha256(str(Path(repo).resolve()).encode()).hexdigest()[:16]


def tracciato(repo, vault):
    for stato in (vault / "projects").glob("*/STATE.md"):
        if stato.parent.name in PRIVATE_DIRS:
            continue
        # A project can span several repos, one `Repo:` line each: any of them makes the repo tracked.
        for percorso in REPO.findall(stato.read_text(encoding="utf-8", errors="replace")):
            if Path(percorso.strip()).expanduser().resolve() == repo:
                return True
    return False


def deciso(repo, vault, oggi):
    """True se l'utente ha già risposto ignora o lavoro, o ha messo in pausa e la pausa non è scaduta."""
    ignorati = vault / "scaffold" / "ignorati.md"
    if not ignorati.is_file():
        return False
    chiavi = {str(repo), impronta(repo)}
    for riga in ignorati.read_text(encoding="utf-8", errors="replace").splitlines():
        celle = [c.strip() for c in riga.strip().strip("|").split("|")]
        if riga.startswith("|") and len(celle) == 4 and celle[0] in chiavi:
            if celle[1] in ("ignora", "lavoro") or (celle[1] == "non ora" and celle[2] >= oggi):
                return True
    return False


def messaggio(cwd, vault, oggi, escludi=None, casa=None):
    """Il testo da mostrare a Claude, o stringa vuota se non serve."""
    vault = Path(vault).resolve()
    if not (vault / "projects").is_dir():
        return ""
    repo = repo_principale(cwd)
    # La home può essere essa stessa un repo git: ogni cartella sotto ~ senza un repo suo ricadrebbe lì.
    if repo is None or repo in (vault, Path(casa or Path.home()).resolve()):
        return ""
    if any(repo.is_relative_to(Path(p).resolve()) for p in (escludi_di_default() if escludi is None else escludi)):
        return ""
    if tracciato(repo, vault) or deciso(repo, vault, oggi):
        return ""
    return (f"Il repo «{repo.name}» ({repo}) non è nel second brain.\n"
            f"Chiedi all'utente, una volta, se tracciarlo: sì, non ora, ignora o lavoro. Salva la risposta con "
            f"`python3 {Path(__file__).resolve()} --registra ignora|non-ora|lavoro` (per «sì» usa `/nuovo-progetto <nome> {repo}`, "
            f"o aggiungi `- **Repo:** {repo}` sotto le righe Repo dello STATE di un progetto esistente).")


def registra(repo, vault, scelta, oggi):
    if scelta not in SCELTE:
        raise ValueError(f"scelta non valida: {scelta} (ammesse: {', '.join(SCELTE)})")
    ignorati = Path(vault) / "scaffold" / "ignorati.md"
    testo = ignorati.read_text(encoding="utf-8") if ignorati.is_file() else INTESTAZIONE
    chiave = impronta(repo) if scelta == "lavoro" else str(repo)
    fino = (date.fromisoformat(oggi) + timedelta(days=PAUSA_GIORNI)).isoformat() if scelta == "non-ora" else ""
    ignorati.parent.mkdir(parents=True, exist_ok=True)
    ignorati.write_text(testo.rstrip("\n") + f"\n| {chiave} | {SCELTE[scelta]} | {fino} | {oggi} |\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--registra", choices=sorted(SCELTE))
    args = ap.parse_args()
    oggi = date.today().isoformat()
    if args.registra:
        repo = repo_principale(args.cwd)
        if repo is None:
            sys.exit("non è un repo git")
        registra(repo, VAULT, args.registra, oggi)
        print(f"Registrato: {SCELTE[args.registra]}")
        return
    try:
        testo = messaggio(args.cwd, VAULT, oggi)
    except Exception:  # un hook di avvio non deve mai rompere la sessione
        return
    if testo:
        print(testo)


if __name__ == "__main__":
    main()
