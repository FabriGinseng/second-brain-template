#!/usr/bin/env python3
"""Bozze della settimana: /bozze-settimana scrive 3 post (LinkedIn e Instagram), lo script disegna le immagini,
lancia scripts/verify e committa in locale solo se passa. Non pubblica niente e non fa push.
Con --forza prepara anche se questa settimana (lunedì-domenica, ISO) l'ha già fatto.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avviso  # noqa: E402
import percorsi  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
LOGS = percorsi.cartella_log()
LOCK_SCADUTO = 30 * 60  # un lock più vecchio di 30 minuti è di una run morta


def _lock(lock):
    try:
        if time.time() - lock.stat().st_mtime > LOCK_SCADUTO:
            lock.rmdir()
    except OSError:
        pass
    try:
        lock.mkdir()
        return True
    except FileExistsError:
        return False


def bozze(forza=False, vault=VAULT, log=LOGS / "second-brain-bozze.log", lock=LOGS / "second-brain-bozze.lock",
          run=subprocess.run, adesso=None, sospese=LOGS / "second-brain-bozze.sospese", segnala=avviso.segnala):
    adesso = adesso or datetime.now()
    oggi = f"{adesso:%F}"

    def scrivi(riga):
        with open(log, "a", encoding="utf-8") as f:
            f.write(riga + "\n")

    def py(*args, **kw):
        """Uno script Python del vault con l'output nel log; True se riesce."""
        with open(log, "a", encoding="utf-8") as f:
            return run([sys.executable, "-I", *args], cwd=vault, stdout=f, stderr=subprocess.STDOUT, **kw).returncode == 0

    if not _lock(lock):
        scrivi(f"{adesso:%F %T} bozze già in corso: salto")
        return 0
    try:
        scrivi(f"=== {adesso:%F %T} ===")
        anno, settimana, _ = adesso.isocalendar()
        chiave = f"{anno}-{settimana:02d}"
        ultima = run(["git", "log", "-1", "--grep=^bozze settimana", "--format=%cd", "--date=format:%G-%V"],
                     cwd=vault, capture_output=True, text=True, encoding="utf-8").stdout.strip()
        if not forza and ultima == chiave:
            scrivi("già preparate questa settimana: salto")
            return 0

        try:  # bozze scritte da un giro con verify fallito: si riprende da quelle, non se ne scrivono altre
            precedente = json.loads(sospese.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            precedente = {}
        if precedente.get("settimana") == chiave and not forza:
            nuove = [n for n in precedente["file"] if (vault / n).is_file()]
            scrivi("riprendo le bozze del giro precedente (verify non era passato): non ne scrivo altre")
        else:
            with open(log, "a", encoding="utf-8") as f:
                attivita = run([sys.executable, "-I", "scripts/attivita-progetti.py", "--giorni", "7"], cwd=vault,
                               stdout=subprocess.PIPE, stderr=f, text=True, encoding="utf-8").stdout.rstrip("\n")
            prompt = f"/bozze-settimana\nAttività dei repo degli ultimi sette giorni:\n{attivita or 'nessuna'}"
            r = run(["claude", "--permission-mode", "dontAsk", "--allowedTools", "Read", "Write", "Glob", "Grep", "-p", prompt],
                    cwd=vault, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    env={**os.environ, "SB_NO_STOP_VERIFY": "1"})  # lo Stop hook non deve rimandare indietro una run non presidiata
            with open(log, "a", encoding="utf-8") as f:
                f.write(r.stdout or "")
            if avviso.non_autenticato(r.stdout):
                scrivi("claude non autenticato: bozze non scritte. Lancia /login.")
                segnala(vault, "le bozze della settimana", adesso)
                return 0
            nuove = [n for n in run(["git", "ls-files", "--others", "--exclude-standard", "--", "content/*/*.md"],
                                    cwd=vault, capture_output=True, text=True, encoding="utf-8").stdout.split("\n") if n]
        if not nuove:
            sospese.unlink(missing_ok=True)  # il promemoria puntava a file che non ci sono più
            scrivi("nessuna bozza nuova")
            return 0

        # Le bozze della settimana scorsa non pubblicate passano a "scartata" (i file restano, cambia content/stato.json).
        if not py("scripts/scarta-bozze.py", oggi):
            scrivi("scarto delle vecchie non riuscito")

        # Le immagini si disegnano qui: nelle run non presidiate Bash è negato.
        for file in nuove:
            if not py("scripts/immagine-bozza.py", file):
                scrivi(f"immagine non riuscita: {file}")

        if py("scripts/verify"):
            run(["git", "add", "content"], cwd=vault)
            with open(log, "a", encoding="utf-8") as f:  # l'hook pre-commit può rifiutare (gitleaks): il motivo resta nel log
                rc = run(["git", "commit", "-q", "-m", f"bozze settimana {oggi}", "-m", "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"],
                         cwd=vault, stdout=f, stderr=subprocess.STDOUT).returncode
            if rc == 0:
                sospese.unlink(missing_ok=True)
                scrivi(f"commit: bozze settimana {oggi}")
            else:  # come per il verify fallito: il giro dopo riprende le stesse bozze
                sospese.write_text(json.dumps({"settimana": chiave, "file": nuove}), encoding="utf-8")
                scrivi("commit bloccato (hook pre-commit o git): vedi sopra, le bozze restano non committate")
        else:
            sospese.write_text(json.dumps({"settimana": chiave, "file": nuove}), encoding="utf-8")
            scrivi("verify non passa: nessun commit. Vedi il log.")
        return 0
    finally:
        lock.rmdir()


if __name__ == "__main__":
    sys.exit(bozze(forza="--forza" in sys.argv[1:2]))
