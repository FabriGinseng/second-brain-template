#!/usr/bin/env python3
"""Brief del mattino senza nessuno davanti: lancia /morning con dontAsk
(le azioni con conferma vengono negate e finiscono in "Da confermare").
Uso: scripts/morning.py   (MORNING_DRY_RUN=1 stampa il comando senza eseguirlo)
"""
import json
import os
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avviso  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
CMD = ["claude", "--permission-mode", "dontAsk", "--allowedTools", "Bash(git log *)", "Bash(git status *)", "-p", "/morning"]


def pronti_smistatore(vault=VAULT, run=subprocess.run):
    """Task pronti dei piani approvati, letti qui e passati nel prompt: nella run non presidiata Bash è negato e il PATH del
    job non ha ~/.local/bin (errore ricorrente del 2026-10-27). Lo smistatore è facoltativo: il suo percorso sta in
    config.json ({"smistatore": "~/Developer/smistatore/bin/smistatore"}); senza la chiave non si lancia niente."""
    file = Path(vault) / "config.json"
    percorso = json.loads(file.read_text(encoding="utf-8-sig")).get("smistatore") if file.is_file() else None  # -sig: a BOM from a Windows editor
    if not percorso:
        return ""
    r = run(["/usr/bin/python3", "-I", str(Path(percorso).expanduser()), "pronti", "--markdown"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    return r.stdout.strip() if r.returncode == 0 else ""


def morning(vault=VAULT, run=subprocess.run, env=os.environ, oggi=None, obsidian=Path("/Applications/Obsidian.app"), segnala=avviso.segnala,
            pronti=pronti_smistatore):
    if env.get("MORNING_DRY_RUN") == "1":
        print(shlex.join(CMD))
        return 0
    try:
        testo = pronti()
    except Exception:  # lo smistatore non deve mai fermare il brief
        testo = ""
    cmd = CMD[:-1] + [f"/morning Task pronti dallo smistatore:\n{testo}" if testo else "/morning"]
    try:
        r = run(cmd, cwd=vault, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                env={**env, "SB_NO_STOP_VERIFY": "1"})  # lo Stop hook non deve rimandare indietro una run non presidiata
    except FileNotFoundError:
        print("morning: claude non trovato nel PATH", file=sys.stderr)
        return 127
    print(r.stdout or "", end="")
    if avviso.non_autenticato(r.stdout):
        segnala(vault, "il brief del mattino")
        return r.returncode or 1
    if r.returncode:
        return r.returncode
    # Il brief può contenere wikilink rotti: il controllo finisce nel log.
    ok = run([sys.executable, "-I", "scripts/verify"], cwd=vault).returncode == 0
    print("verify: OK" if ok else "verify: problemi, vedi sopra")
    # Apre la nota del giorno in Obsidian solo se l'app è installata.
    if obsidian.is_dir():
        run(["open", f"obsidian://open?vault={vault.name}&file=daily/{oggi or date.today():%F}"])
    return 0


if __name__ == "__main__":
    sys.exit(morning())
