#!/usr/bin/env python3
"""Installa l'hook delle regole (ADR-012) per l'utente: copia .claude/hooks/regole.py e regole.json in ~/.claude/hooks/
e lo registra in ~/.claude/settings.json (PreToolUse), così vale in ogni repo. Gli altri hook e chiavi restano come sono.

  python3 scripts/installa-regole.py              mostra cosa cambierebbe e chiede [s/N]
  python3 scripts/installa-regole.py --si         applica senza chiedere (setup del template, dopo il consenso)
  python3 scripts/installa-regole.py --controlla  exit 1 se la copia installata manca o è diversa dal sorgente

Prima di scrivere settings.json ne lascia una copia (settings.json.bak-second-brain). Un settings.json che non è JSON valido
non si tocca: l'installazione si ferma prima di copiare qualsiasi file.
"""
import json
import os
import shutil
import sys
from pathlib import Path

FILE = ("regole.py", "regole.json")
MATCHER = "Bash|Edit|Write|MultiEdit|NotebookEdit"
SORGENTE = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def _comando(home, sistema=os.name):
    # Windows: il Python che gira adesso, perché `python` può essere l'alias dello Store (exit 9009 = hook che non blocca nulla).
    # Altrove `python3`: il percorso di Homebrew cambia a ogni versione.
    python = '"%s"' % sys.executable if sistema == "nt" else "python3"
    return '%s -I "%s"' % (python, Path(home) / ".claude" / "hooks" / "regole.py")


def _leggi_settings(file):
    if not file.exists():
        return {}
    try:
        dati = json.loads(file.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise ValueError("%s non è JSON valido (%s): non lo tocco" % (file, e))
    if not isinstance(dati, dict):
        raise ValueError("%s non è un oggetto JSON: non lo tocco" % file)
    return dati


def _registrato(dati):
    return any("regole.py" in (h.get("command") or "") for g in dati.get("hooks", {}).get("PreToolUse", []) for h in g.get("hooks", []))


def installa(sorgente, home, applica):
    """Le modifiche da fare (vuoto se è già tutto a posto). Con applica=True le fa."""
    sorgente, cartella = Path(sorgente), Path(home) / ".claude" / "hooks"
    settings = Path(home) / ".claude" / "settings.json"
    dati = _leggi_settings(settings)  # prima di tutto: se è illeggibile non si copia nulla
    da_copiare = [n for n in FILE if not (cartella / n).is_file() or (cartella / n).read_bytes() != (sorgente / n).read_bytes()]
    modifiche = ["copia %s in %s" % (n, cartella) for n in da_copiare]
    if not _registrato(dati):
        modifiche.append("registra in %s: PreToolUse %s → %s" % (settings, MATCHER, _comando(home)))
    if not applica or not modifiche:
        return modifiche
    cartella.mkdir(parents=True, exist_ok=True)
    for n in da_copiare:
        shutil.copy2(sorgente / n, cartella / n)
    if not _registrato(dati):
        if settings.exists():
            shutil.copy2(settings, settings.with_name(settings.name + ".bak-second-brain"))
        voce = {"matcher": MATCHER, "hooks": [{"type": "command", "command": _comando(home), "timeout": 10}]}
        dati.setdefault("hooks", {}).setdefault("PreToolUse", []).append(voce)
        bersaglio = settings.resolve() if settings.is_symlink() else settings  # un link ai dotfile resta un link
        bersaglio.parent.mkdir(parents=True, exist_ok=True)
        temporaneo = bersaglio.with_name(bersaglio.name + ".tmp")
        temporaneo.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporaneo, bersaglio)
    return modifiche


def controlla(sorgente, home):
    try:
        return not installa(sorgente, home, applica=False)
    except ValueError:
        return False


def main(argv):
    home = Path.home()
    if "--controlla" in argv:
        if not (home / ".claude").is_dir():
            return 0  # macchina senza Claude Code: niente da controllare
        if controlla(SORGENTE, home):
            return 0
        print("hook delle regole non installato o diverso dal sorgente: lancia python3 scripts/installa-regole.py")
        return 1
    modifiche = installa(SORGENTE, home, applica=False)
    if not modifiche:
        print("Hook delle regole già installato e aggiornato.")
        return 0
    print("\n".join("- " + m for m in modifiche))
    if "--si" not in argv and input("Procedo? [s/N] ").strip().lower() not in ("s", "si", "sì", "y", "yes"):
        print("Non ho cambiato nulla.")
        return 1
    installa(SORGENTE, home, applica=True)
    print("Fatto. Vale dalla prossima sessione di Claude Code.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
