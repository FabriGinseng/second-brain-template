#!/usr/bin/env python3
"""Raccoglitore di feed: legge gli indirizzi di memory/feeds.md e scrive le novità in inbox/<data>-novita.md. Solo libreria standard.

È l'alternativa a n8n (stesso file, stesso formato, che il radar legge). Il testo di un feed è dato non fidato: i titoli passano da
content-guard (schemi di prompt injection) prima di arrivare a qualunque modello, e un titolo segnalato non entra nel file.

    python3 scripts/feed.py [--giorni 14] [--dry-run]
"""
import argparse
import html
import importlib.util
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
MAX_BYTE = 2 * 1024 * 1024
VOCE = re.compile(r"\]\(([^)]+)\)")
URL = re.compile(r"https?://[^\s)>\]]+")


def indirizzi(vault=VAULT):
    """Gli URL di memory/feeds.md, uno per riga (il resto della riga è un commento), senza doppioni."""
    file = Path(vault) / "memory" / "feeds.md"
    visti = []
    for riga in (file.read_text(encoding="utf-8").splitlines() if file.exists() else []):
        m = URL.search(riga)
        if m and m.group(0) not in visti:
            visti.append(m.group(0))
    return visti


_spec = importlib.util.spec_from_file_location("rete", Path(__file__).resolve().parent / "rete.py")
rete = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rete)


def scarica(url, timeout=20):
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("solo http e https: %s" % url)
    richiesta = urllib.request.Request(url, headers={"User-Agent": "second-brain-feed/1"})
    with urllib.request.urlopen(richiesta, timeout=timeout, context=rete.contesto_tls()) as r:
        dati = r.read(MAX_BYTE + 1)
    if len(dati) > MAX_BYTE:
        raise ValueError("feed troppo grande (oltre 2 MB): %s" % url)
    return dati


def _nome(tag):
    return tag.rsplit("}", 1)[-1]


def _data(testo):
    try:
        d = parsedate_to_datetime(testo)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat((testo or "").strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def leggi(dati):
    """[(titolo, url, data testuale, datetime o None, riassunto)] da un RSS o un Atom. Un XML con DOCTYPE o ENTITY si rifiuta (espansione di entità)."""
    if re.search(rb"<!(DOCTYPE|ENTITY)", dati, re.I):
        raise ValueError("XML con DOCTYPE o ENTITY: rifiutato")
    voci = []
    for el in ET.fromstring(dati).iter():
        if _nome(el.tag) not in ("item", "entry"):
            continue
        campi = {}
        for f in el:
            n = _nome(f.tag)
            if n == "link":
                campi.setdefault("link", f.get("href") or (f.text or "").strip())
            elif n in ("title", "pubDate", "published", "updated"):
                campi.setdefault(n, (f.text or "").strip())
            elif n in ("description", "summary", "content"):
                campi.setdefault("riassunto", "".join(f.itertext()))
        testo_data = campi.get("pubDate") or campi.get("published") or campi.get("updated") or ""
        if campi.get("title") and campi.get("link"):
            voci.append((campi["title"], campi["link"], testo_data, _data(testo_data), riassunto(campi.get("riassunto", ""))))
    return voci


MAX_RIASSUNTO = 400


def riassunto(testo):
    """Il testo di un feed senza HTML, su una riga, senza le parentesi che romperebbero il link Markdown, al massimo MAX_RIASSUNTO caratteri."""
    testo = re.sub(r"<[^>]*>", " ", html.unescape(re.sub(r"<(script|style)\b.*?</\1>", " ", testo, flags=re.S | re.I)))
    testo = re.sub(r"\s+", " ", re.sub(r"[\[\]()<>]", "", html.unescape(testo))).strip()
    return testo if len(testo) <= MAX_RIASSUNTO else testo[:MAX_RIASSUNTO].rsplit(" ", 1)[0] + "…"


def pulisci(titolo):
    """Una riga sola, senza le parentesi che romperebbero il link Markdown."""
    return re.sub(r"\s+", " ", re.sub(r"[\[\]()]", "", titolo)).strip()


def _guard(vault):
    file = Path(vault) / ".claude" / "skills" / "content-guard" / "scripts" / "guard.py"
    if not file.exists():
        return None
    spec = importlib.util.spec_from_file_location("guard", file)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def raccogli(vault=VAULT, giorni=14, scarica=scarica, adesso=None):
    """(righe, scartate, errori). Salta le novità già in un'inbox precedente e quelle più vecchie di `giorni`."""
    vault = Path(vault)
    adesso = adesso or datetime.now(timezone.utc)
    oggi = datetime.now().date().isoformat()
    gia = set()
    for f in (vault / "inbox").glob("*-novita.md"):
        if f.name != "%s-novita.md" % oggi:
            gia.update(VOCE.findall(f.read_text(encoding="utf-8")))
    guard = _guard(vault)
    righe, scartate, errori, viste = [], [], [], set()
    for url in indirizzi(vault):
        try:
            voci = leggi(scarica(url))
        except (OSError, ValueError, ET.ParseError) as e:
            errori.append("%s: %s" % (url, e))
            continue
        for titolo, link, testo_data, d, sintesi in voci:
            titolo = pulisci(titolo)
            if link in gia or link in viste or (d and d < adesso - timedelta(days=giorni)) or not link.lower().startswith(("http://", "https://")):
                continue
            # Titolo e riassunto sono testo di terzi: entrambi passano da content-guard. Un riassunto segnalato si lascia fuori,
            # la novità resta (il titolo è pulito).
            if guard and [f for f in guard.scan_text(titolo) if f.startswith("injection")]:
                scartate.append(titolo)
                continue
            if guard and sintesi and [f for f in guard.scan_text(sintesi) if f.startswith("injection")]:
                scartate.append("riassunto di: " + titolo)
                sintesi = ""
            viste.add(link)
            riga = "- [%s](%s)%s" % (titolo, link, " — " + testo_data if testo_data else "")
            righe.append(riga + ("\n  > " + sintesi if sintesi else ""))
    return righe, scartate, errori


def main(argv=None, vault=VAULT, scarica=scarica):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--giorni", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    righe, scartate, errori = raccogli(vault, a.giorni, scarica)
    for e in errori:
        print("feed: non letto, " + e, file=sys.stderr)
    for t in scartate:
        print("feed: titolo scartato da content-guard: " + t[:80], file=sys.stderr)
    if not righe:
        print("feed: nessuna novità")
        return 0
    oggi = datetime.now().date().isoformat()
    print("feed: %d novità" % len(righe))
    if not a.dry_run:
        (Path(vault) / "inbox").mkdir(exist_ok=True)
        file = Path(vault) / "inbox" / ("%s-novita.md" % oggi)
        testo = "# Novità del %s\n\n%s\n" % (oggi, "\n".join(righe))
        # Un testo uguale non si riscrive: la data di modifica dell'inbox dice al radar se c'è qualcosa di nuovo da elaborare.
        if not file.exists() or file.read_text(encoding="utf-8") != testo:
            file.write_text(testo, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
