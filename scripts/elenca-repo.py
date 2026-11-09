#!/usr/bin/env python3
"""Elenca i repo git sotto le cartelle indicate che il vault non conosce (serve a /adotta-repo).

Uso: scripts/elenca-repo.py CARTELLA [CARTELLA ...] [--profondita 3]

Stampa un elenco numerato, con i repo che hanno lo stesso remote raggruppati. Salta i repo già tracciati
(una riga «Repo:» di un projects/*/STATE.md) e quelli già decisi (ignora, lavoro, non ora in corso). Non scrive
mai e non decide mai se un repo è di lavoro o personale. Le risposte si salvano con
`repo-non-tracciato.py --registra` (una cartella alla volta, con --cwd).
"""
import argparse
import importlib.util
import os
import subprocess
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
SALTA = {"node_modules", ".claude", ".worktrees"}

_spec = importlib.util.spec_from_file_location("repo_non_tracciato", Path(__file__).with_name("repo-non-tracciato.py"))
rnt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rnt)


def trova_repo(radice, profondita, casa):
    """I repo git (cartelle con una .git che è una cartella) fino a `profondita` livelli sotto radice."""
    radice = Path(radice).resolve()
    trovati = []
    base = len(radice.parts)
    for cartella, sotto, _ in os.walk(radice):
        livello = len(Path(cartella).parts) - base
        repo = (Path(cartella) / ".git").is_dir()  # la .git dei worktree è un file: non è un repo a parte
        if repo:
            trovati.append(Path(cartella))
        # Dentro un repo non si scende, tranne nella home, che può essere essa stessa un repo.
        if livello >= profondita or (repo and Path(cartella) != casa):
            sotto[:] = []
        else:
            sotto[:] = sorted(d for d in sotto if d not in SALTA and not d.startswith("."))
    return trovati


def remote(repo):
    try:
        r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True, encoding="utf-8",
                           timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def elenco(radici, vault, oggi, profondita, casa=None):
    vault = Path(vault).resolve()
    casa = Path(casa or Path.home()).resolve()
    visti, gruppi, tracciati = set(), {}, 0
    for radice in radici:
        for repo in trova_repo(radice, profondita, casa):
            if repo in visti or repo in (vault, casa):
                continue
            visti.add(repo)
            if rnt.tracciato(repo, vault):
                tracciati += 1
            elif not rnt.deciso(repo, vault, oggi):
                gruppi.setdefault(remote(repo), []).append(repo)
    return {"tracciati": tracciati,
            "gruppi": [{"remote": r, "repo": sorted(p)} for r, p in sorted(gruppi.items(), key=lambda kv: min(kv[1]))]}


def formatta(out):
    righe, n = [], 0
    for g in out["gruppi"]:
        copie = len(g["repo"]) > 1 and g["remote"]
        if copie:
            righe.append(f"Stesso remote ({g['remote']}): probabili copie, suggerisco «ignora» per quelle in più")
        for repo in g["repo"]:
            n += 1
            righe.append(f"{n}. {repo.name}  ({repo})" + ("" if g["remote"] else "  [nessun remote]"))
    righe.append(f"Già tracciati: {out['tracciati']}. Da decidere: {n}.")
    return "\n".join(righe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartelle", nargs="+")
    ap.add_argument("--profondita", type=int, default=3)
    args = ap.parse_args()
    cartelle = [Path(c).expanduser() for c in args.cartelle]
    print(formatta(elenco(cartelle, VAULT, date.today().isoformat(), args.profondita)))


if __name__ == "__main__":
    main()
