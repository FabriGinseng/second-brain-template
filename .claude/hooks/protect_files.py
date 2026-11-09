#!/usr/bin/env python3
"""PreToolUse su Edit|Write: blocca la modifica dei guardrail stessi (hook, pre-commit, verify).

Solo questi: docs/adr/, CLAUDE.md, memory/ e il resto di .claude/ sono «con conferma» (ADR-004) e restano alle regole `ask`
di .claude/settings.json; un blocco duro li renderebbe non modificabili nemmeno con il sì dell'utente.
Il confronto ignora le maiuscole: su macOS (APFS) SCRIPTS/verify è lo stesso file di scripts/verify.
Per cambiare un guardrail si modifica il file a mano. Exit 2 = blocco, il messaggio su stderr arriva a Claude.
"""
import json
import os
import sys
from pathlib import Path

GUARDRAIL = (".claude/hooks", "scripts/hooks", "scripts/verify")

dati = json.load(sys.stdin)
file = (dati.get("tool_input") or {}).get("file_path")
if file:
    radice = Path(os.environ.get("CLAUDE_PROJECT_DIR") or dati.get("cwd") or ".").resolve()
    percorso = Path(file)
    try:
        rel = (percorso if percorso.is_absolute() else radice / percorso).resolve().relative_to(radice).as_posix()
    except ValueError:
        sys.exit(0)  # fuori dal vault
    chiave = rel.casefold()
    if any(chiave == g or chiave.startswith(g + "/") for g in GUARDRAIL):
        sys.stderr.write(f"{rel} è un guardrail del vault (hook, pre-commit o verify): non lo modifico. Se serve cambiarlo, lo fa l'utente a mano.\n")
        sys.exit(2)
