#!/usr/bin/env python3
"""Stop: se il vault ha modifiche, `scripts/verify` deve passare prima che Claude chiuda il turno.

Se verify fallisce, exit 2 con il suo output su stderr: Claude lo legge e corregge. Dopo due blocchi nella stessa sessione
lascia chiudere, perché un controllo che non finisce mai è peggio di nessun controllo. Albero pulito o niente verify: non fa nulla.
Le run `claude -p` che non possono correggere nulla (richieste di post, bozze, morning, modello) impostano SB_NO_STOP_VERIFY=1:
un blocco cambierebbe la loro risposta in una frase di scuse e la richiesta risulterebbe rifiutata.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BLOCCHI_MASSIMI = 2

dati = json.load(sys.stdin)
if os.environ.get("SB_NO_STOP_VERIFY"):
    sys.exit(0)
radice = Path(os.environ.get("CLAUDE_PROJECT_DIR") or dati.get("cwd") or ".").resolve()
verify = radice / "scripts" / "verify"
if not verify.is_file():
    sys.exit(0)
if not subprocess.run(["git", "status", "--porcelain"], cwd=radice, capture_output=True, text=True).stdout.strip():
    sys.exit(0)

contatore = Path(tempfile.gettempdir()) / ("sb-stop-" + re.sub(r"\W", "", str(dati.get("session_id", "x"))))
r = subprocess.run([sys.executable, "-I", str(verify)], cwd=radice, capture_output=True, text=True)
if r.returncode == 0:
    contatore.unlink(missing_ok=True)
    sys.exit(0)
n = int(contatore.read_text()) if contatore.is_file() else 0
if n >= BLOCCHI_MASSIMI:
    sys.exit(0)
contatore.write_text(str(n + 1))
sys.stderr.write("scripts/verify non passa, correggi prima di chiudere:\n" + (r.stdout + r.stderr)[-1500:])
sys.exit(2)
