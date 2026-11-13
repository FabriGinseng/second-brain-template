#!/usr/bin/env python3
"""Radar completo sull'ultima inbox: stadio 1 (embedding o parole chiave), stadio 2 (giudizio), output in radar/.
Con modelli.radar_giudizio = claude un solo passo, scripts/radar-claude.py, al posto dei due stadi.

I modelli si scelgono in config.json (modelli.radar_embedding, modelli.radar_giudizio; vedi scripts/modello.py). Con un embedding su Ollama
serve radar/.indice-progetti.json (scripts/indice-embedding.py).
"""
import importlib.util
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("modello", Path(__file__).resolve().parent / "modello.py")
modello = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(modello)


def _lancia(vault, *args):
    subprocess.run([sys.executable, "-I", *args], cwd=vault, check=True)


def _piu_recente(file):
    return max(file, key=lambda f: f.stat().st_mtime, default=None)


def _con_claude(vault):
    """Vero se il giudizio del radar lo dà Claude: allora il radar è un solo passo (scripts/radar-claude.py) e non due stadi."""
    try:
        return modello.scelta("radar_giudizio", vault)[0] == "claude"
    except modello.ModelloNonDisponibile:
        return False


def _n8n(vault):
    """Vero se la raccolta è affidata a n8n (config.json, moduli.radar.automazione): allora feed.py non deve scrivere la stessa inbox."""
    try:
        return json.loads((vault / "config.json").read_text(encoding="utf-8"))["moduli"]["radar"]["automazione"] == "n8n"
    except (OSError, ValueError, KeyError, TypeError):
        return False


def raccogli_se_manca(vault, lancia, oggi=None):
    """n8n parte alle 7:00 ma non recupera un giro perso (Mac in sospensione o spento): se questa settimana non c'è un'inbox,
    la raccoglie scripts/feed.py dagli indirizzi di memory/feeds.md. Senza quel file non fa niente (la raccolta resta a n8n)."""
    oggi = oggi or date.today()
    lunedi = (oggi - timedelta(days=oggi.weekday())).isoformat()
    if not (vault / "memory" / "feeds.md").is_file():
        return
    # Con Claude (e senza n8n) raccoglie sempre feed.py: l'inbox di n8n ha solo i titoli, quella di feed.py anche il riassunto.
    # feed.py non riscrive un'inbox uguale, quindi un secondo giro lo stesso giorno non rielabora niente.
    if not (_con_claude(vault) and not _n8n(vault)) and any(f.name[:10] >= lunedi for f in (vault / "inbox").glob("*-novita.md")):
        return
    lancia(vault, "scripts/feed.py")


def radar(vault=VAULT, lancia=_lancia, oggi=None):
    raccogli_se_manca(vault, lancia, oggi)
    # Il job settimanale gira anche se n8n non ha consegnato una inbox nuova: in quel caso non rifare l'ultima.
    novita = _piu_recente((vault / "inbox").glob("*-novita.md"))
    if novita is None:
        print("radar: nessuna inbox, salto")
        return
    # Fatta = esiste la scheda finale radar/<data>.md più recente dell'inbox. I candidati dello stadio 1 non bastano:
    # se lo stadio 2 fallisce, il giro dopo deve riprovare.
    data = novita.name[:-len("-novita.md")]
    scheda = vault / "radar" / f"{data}.md"
    if scheda.is_file() and scheda.stat().st_mtime > novita.stat().st_mtime:
        print(f"radar: inbox/{novita.name} già elaborata, salto")
        return
    if _con_claude(vault):
        lancia(vault, "scripts/radar-claude.py", f"inbox/{novita.name}")
        return
    if modello.scelta("radar_embedding", vault)[0] != "none":  # senza embedding lo stadio 1 confronta le parole chiave e non serve l'indice
        lancia(vault, "scripts/indice-embedding.py")
    lancia(vault, "scripts/radar-stadio1.py")
    candidati = f"radar/.candidati-{data}.json"
    lancia(vault, "scripts/radar-stadio2.py", candidati)
    lancia(vault, "scripts/radar-output.py", candidati)


if __name__ == "__main__":
    radar()
