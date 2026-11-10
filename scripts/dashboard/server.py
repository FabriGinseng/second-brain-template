#!/usr/bin/env python3
"""Dashboard locale del second brain: inbox, radar, progetti e job launchd.

Uso: scripts/dashboard/server.py [porta]   (default 8765, ascolta solo su 127.0.0.1)
Ogni dato viene letto dai file del vault a ogni richiesta. Scrive solo le caselle di docs/piano.md
e docs/scadenze.md (imposta_stato), le voci nuove di docs/piano.md (aggiungi_voce), i voti sulle scartate del radar in radar/feedback.jsonl (vota_scartata)
e avvia le azioni previste (avvia).
"""
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent

def _modulo(percorso):
    """Carica un modulo da file: con 'python3 -I' la cartella dello script non è nel path e il nome ha un trattino."""
    percorso = Path(percorso)
    spec = importlib.util.spec_from_file_location(percorso.stem.replace("-", "_"), percorso)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


configurazione = _modulo(HERE / "configurazione.py")
controllo_skill = _modulo(HERE.parent / "controllo-skill.py")
avvii_modulo = _modulo(HERE / "avvii.py")
genera_plist = _modulo(HERE.parent / "genera_plist.py") if (HERE.parent / "genera_plist.py").exists() else None  # nel template non c'è: i job li registra install_jobs.py
servizi_modulo = _modulo(HERE / "servizi.py")
post_modulo = _modulo(HERE / "post.py")
richieste_modulo = _modulo(HERE / "richieste.py")
agenda_modulo = _modulo(HERE / "agenda.py")
assistente_modulo = _modulo(HERE / "assistente.py")
limiti_modulo = _modulo(HERE / "limiti.py")
modello_modulo = _modulo(HERE.parent / "modello.py")
percorsi = _modulo(HERE.parent / "percorsi.py")
calendario_modulo = _modulo(HERE.parent / "calendario.py")
BLOCCO_RICHIESTE = threading.Lock()  # una scrittura alla volta sul file delle richieste
BLOCCO_PIANO = threading.Lock()  # lettura, modifica e scrittura di piano.md e scadenze.md: due clic veloci sono due thread
BLOCCO_CONFIG = threading.Lock()  # un solo cambio alla volta ai file globali di Claude
PORTA = 8765
HOST_OK = {"127.0.0.1:%d" % PORTA, "localhost:%d" % PORTA}
JOB = ["morning", "chiusura", "n8n", "pulizia", "ollama"]
RIGA_PROGETTO = re.compile(r"^\| \[\[projects/([^/\\|]+)/STATE")
VOCE_INBOX = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)")
SEZIONE = re.compile(r"^## (.+)$")
SCARTATA = re.compile(r"^- (.+) \(score ([\d.]+), ([^)]*)\): (.*)$")
LINK_NOVITA = re.compile(r"^\[(.+)\]\((https?://[^)\s]+)\)$")  # "### [Titolo](https://...)": solo http e https, mai javascript:
GIUDIZI = {"falso-scarto", "scarto-giusto"}
BLOCCO_FEEDBACK = threading.Lock()


def progetti():
    """Righe di INDEX.md con stack, stato, data e obiettivo dello STATE."""
    out = []
    for riga in (VAULT / "projects" / "INDEX.md").read_text(encoding="utf-8").splitlines():
        m = RIGA_PROGETTO.match(riga)
        if not m:
            continue
        # Il pipe nel wikilink è escapato (\|), quindi la prima cella occupa due posizioni dello split.
        celle = [c.strip() for c in riga.split("|")]
        nome = m.group(1)
        state = (VAULT / "projects" / nome / "STATE.md").read_text(encoding="utf-8")
        obiettivo = re.search(r"## Obiettivo attuale\n(.*?)(?=\n## |\Z)", state, re.S)
        out.append({
            "nome": nome,
            "stack": celle[3],
            "stato": celle[4],
            "aggiornato": celle[6],
            "obiettivo": obiettivo.group(1).strip() if obiettivo else "",
            "primoPasso": primo_passo(state),
            "doveSono": testo_sezione(state, "Dove sono"),
            "passi": voci_sezione(state, "Prossimi 3 passi", NUMERATA),
            "blocchi": voci_sezione(state, "Blocchi aperti", PUNTO),
            "attivita": attivita_progetto(repo_di(state)),
            "avanzamento": avanzamento_progetto(repo_di(state)),
        })
    return out


NUMERATA = re.compile(r"^\d+\. (.+)$", re.M)
PUNTO = re.compile(r"^- (.+)$", re.M)
REPO = re.compile(r"^- \*\*Repo:\*\* (.+)$", re.M)


def testo_sezione(stato, titolo):
    """Testo di una sezione '## titolo' di uno STATE, vuoto se manca."""
    m = re.search(r"## " + titolo + r"\n(.*?)(?=\n## |\Z)", stato, re.S)
    return m.group(1).strip() if m else ""


def voci_sezione(stato, titolo, voce):
    return [m.strip() for m in voce.findall(testo_sezione(stato, titolo))]


def repo_di(stato):
    """Percorsi delle righe `Repo:` di uno STATE, in ordine e senza doppioni: un progetto può avere più repo."""
    return list(dict.fromkeys(p.strip() for p in REPO.findall(stato) if p.strip()))


def attivita_progetto(repo_progetto):
    """attivita() di tutti i repo del progetto, unita nella stessa forma. None se nessuno si legge.
    Con un solo repo è identica a attivita() di quel repo."""
    letti = [(r, a) for r in repo_progetto if (a := attivita(r))]
    if not letti:
        return None
    if len(repo_progetto) == 1:
        return letti[0][1]
    commit = [{**c, "ramo": "%s %s" % (Path(r).name, c["ramo"])} for r, a in letti for c in a["commit"]]
    return {
        "ultimoCommit": max(a["ultimoCommit"] for _, a in letti),
        "giorni": [{"data": g["data"], "n": sum(a["giorni"][i]["n"] for _, a in letti)} for i, g in enumerate(letti[0][1]["giorni"])],
        "branch": " · ".join("%s: %s" % (Path(r).name, a["branch"]) for r, a in letti),
        "nonCommittate": sum(a["nonCommittate"] for _, a in letti),
        "commit": sorted(commit, key=lambda c: c["quando"], reverse=True)[:4],
    }


def avanzamento_progetto(repo_progetto):
    """avanzamento() di tutti i repo del progetto, sommato; con più repo ogni mappa porta il nome del repo."""
    letti = [(r, a) for r in repo_progetto if (a := avanzamento(r))]
    if not letti:
        return None
    if len(repo_progetto) == 1:
        return letti[0][1]
    mappe = [{**m, "nome": "%s %s" % (Path(r).name, m["nome"])} for r, a in letti for m in a["mappe"]]
    return {"chiusi": sum(a["chiusi"] for _, a in letti), "totale": sum(a["totale"] for _, a in letti), "mappe": mappe,
            "aperti": [t for _, a in letti for t in a["aperti"]]}


def _commit(riga):
    quando, ramo, messaggio = riga.split("\t", 2)
    return {"quando": int(quando), "ramo": ramo.removeprefix("refs/heads/"), "messaggio": messaggio}


def attivita(repo):
    """Branch, modifiche non committate e ultimi commit (quando come timestamp, e messaggio) del repo del progetto; None se non si legge."""
    if not repo or not (Path(repo) / ".git").exists():
        return None
    try:
        # --branches: il lavoro sta anche su feat/* e in worktree, non solo sul branch corrente.
        log = _git_in(repo, "log", "--branches", "--source", "-4", "--format=%ct\t%S\t%s", check=True)
        giorni = _git_in(repo, "log", "--branches", "--since=14 days ago", "--format=%cs", check=True).split()
        oggi = datetime.now().date()
        return {
            "ultimoCommit": int(_git_in(repo, "log", "-1", "--branches", "--format=%ct", check=True) or 0),
            "giorni": [{"data": str(oggi - timedelta(days=d)), "n": giorni.count(str(oggi - timedelta(days=d)))} for d in range(13, -1, -1)],
            "branch": _git_in(repo, "branch", "--show-current", check=True),
            "nonCommittate": len([r for r in _git_in(repo, "status", "--porcelain", check=True).splitlines() if r.strip()]),
            "commit": [_commit(r) for r in log.splitlines() if r.count("\t") >= 2],
        }
    except (OSError, subprocess.SubprocessError):
        return None


STATO_TICKET = re.compile(r"^status:\s*(\w+)", re.M)


def avanzamento(repo):
    """Ticket di wayfinder del repo, chiusi su totali, per mappa: docs/**/tickets/*.md e docs/wayfinder/NNN-*.md. None se non ce ne sono."""
    docs = Path(repo) / "docs" if repo else None
    if not docs or not docs.is_dir():
        return None
    mappe, aperti = {}, []
    for file in sorted(set(docs.rglob("tickets/*.md")) | set((docs / "wayfinder").glob("[0-9]*-*.md"))):
        try:
            m = STATO_TICKET.search(file.read_text(encoding="utf-8", errors="replace")[:600])
        except OSError:
            continue
        if not m:
            continue
        rel = file.relative_to(docs).parts
        nome = rel[rel.index("tickets") - 1] if "tickets" in rel and rel.index("tickets") > 0 else "wayfinder"
        nome = "principale" if nome == "wayfinder" and "tickets" in rel else nome
        voce = mappe.setdefault(nome, {"nome": nome, "chiusi": 0, "totale": 0})
        voce["totale"] += 1
        if m.group(1).lower() == "closed":
            voce["chiusi"] += 1
        else:
            aperti.append(re.sub(r"^\d+-", "", file.stem).replace("-", " "))
    if not mappe:
        return None
    lista = sorted(mappe.values(), key=lambda x: x["nome"])
    return {"chiusi": sum(x["chiusi"] for x in lista), "totale": sum(x["totale"] for x in lista), "mappe": lista, "aperti": aperti}


PASSI = re.compile(r"## Prossimi 3 passi\n(.*?)(?=\n## |\Z)", re.S)
PRIMO_PASSO = re.compile(r"^1\. (.+)$", re.M)


def primo_passo(stato):
    """Primo passo della sezione 'Prossimi 3 passi' di uno STATE, o None."""
    sezione = PASSI.search(stato)
    primo = PRIMO_PASSO.search(sezione.group(1)) if sezione else None
    return primo.group(1).strip() if primo else None


def inbox():
    """File di novità in inbox/, dal più recente, con il numero di voci."""
    file = sorted((VAULT / "inbox").glob("*-novita.md"), reverse=True)
    return [
        {"file": f.name, "voci": sum(1 for r in f.read_text(encoding="utf-8").splitlines() if VOCE_INBOX.match(r))}
        for f in file
    ]


def voti(file=None):
    """Ultimo giudizio per titolo da radar/feedback.jsonl (l'ultima riga vale): titolo -> giudizio."""
    file = file or VAULT / "radar" / "feedback.jsonl"
    if not file.exists():
        return {}
    out = {}
    for riga in file.read_text(encoding="utf-8").splitlines():
        try:
            v = json.loads(riga)
            out[v["titolo"]] = v["giudizio"]
        except (ValueError, KeyError, TypeError):
            continue  # una riga rovinata non deve spegnere la dashboard
    return out


def radar(cartella=None, feedback=None):
    """Ultimo report del radar: schede da leggere (titolo, link) e scartate (titolo, score, progetto, motivo, giudizio) con il riepilogo dei voti."""
    cartella = cartella or VAULT / "radar"
    file = sorted(cartella.glob("20*.md"), reverse=True)
    if not file:
        return None
    da_leggere, scartate, sezione = [], [], None
    for riga in file[0].read_text(encoding="utf-8").splitlines():
        s = SEZIONE.match(riga)
        if s:
            sezione = s.group(1)
            continue
        if sezione == "Da leggere" and riga.startswith("### "):
            m = LINK_NOVITA.match(riga[4:].strip())
            da_leggere.append({"titolo": m.group(1), "link": m.group(2)} if m else {"titolo": riga[4:], "link": None})
        elif sezione and sezione.startswith("Scartate") and riga.startswith("- "):
            m = SCARTATA.match(riga)
            scartate.append(
                {"titolo": m.group(1), "score": float(m.group(2)), "progetto": m.group(3), "motivo": m.group(4)}
                if m else {"titolo": riga[2:], "score": None, "progetto": None, "motivo": None}
            )
    giudizi = voti(feedback)
    for c in scartate:
        c["giudizio"] = giudizi.get(c["titolo"])
    return {
        "data": file[0].stem, "daLeggere": da_leggere, "scartate": scartate,
        "valutate": len(giudizi), "falsiScarti": sum(1 for g in giudizi.values() if g == "falso-scarto"),
    }


def vota_scartata(titolo, giudizio, cartella=None, feedback=None):
    """Registra il voto su una scartata dell'ultimo report: ValueError se il giudizio non è valido, LookupError se il titolo non c'è."""
    if giudizio not in GIUDIZI:
        raise ValueError(giudizio)
    r = radar(cartella, feedback)
    scartata = next((c for c in (r["scartate"] if r else []) if c["titolo"] == titolo), None)
    if scartata is None:
        raise LookupError(titolo)
    riga = {
        "data": datetime.now().isoformat(timespec="seconds"), "titolo": titolo, "score": scartata["score"],
        "progetto": scartata["progetto"], "motivo": scartata["motivo"], "giudizio": giudizio,
    }
    with BLOCCO_FEEDBACK, (feedback or VAULT / "radar" / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(riga, ensure_ascii=False) + "\n")


def jobs_pianificati(vault=VAULT):
    """{nome: dati nel formato dei plist} dei job di scripts/jobs.json. Nel vault completo li legge genera_plist; nel template
    (formato neutro di install_jobs.py) li porta allo stesso formato, così «Avvii» funziona con gli stessi orari."""
    if genera_plist is not None:
        return genera_plist.carica(vault)
    vault = Path(vault)
    try:
        etichetta = json.loads((vault / "config.json").read_text(encoding="utf-8")).get("etichetta", "second-brain")
        jobs = json.loads((vault / "scripts" / "jobs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for nome, j in jobs.items():
        voce = {"Label": "%s.%s" % (etichetta, nome), "StandardOutPath": str(percorsi.cartella_log() / ("second-brain-%s.log" % j.get("log", nome)))}
        if j.get("time") and j.get("days"):
            ora, minuto = (int(x) for x in j["time"].split(":"))
            voce["StartCalendarInterval"] = [{"Weekday": g % 7, "Hour": ora, "Minute": minuto} for g in sorted(j["days"])]
        out[nome] = voce
    return out


def job():
    """Stato di ogni job launchd del second brain: running, loaded o assente. Fuori da macOS non c'è launchd: nessuno stato."""
    out = {}
    if sys.platform != "darwin":
        return out
    jobs = jobs_pianificati(VAULT)
    for nome in JOB:
        if nome not in jobs:
            continue
        etichetta = "gui/%d/%s" % (_uid(), jobs[nome]["Label"])
        r = subprocess.run(["launchctl", "print", etichetta], capture_output=True, text=True, encoding="utf-8", timeout=10)
        if r.returncode != 0:
            out[nome] = "non caricato"
            continue
        stato = re.search(r"state = (.+)", r.stdout)
        out[nome] = stato.group(1) if stato else "caricato"
    return out


def _uid():
    import os
    return os.getuid()


def _git_in(repo, *args, check=False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", timeout=10, check=check)
    return r.stdout.strip()


def _git(*args):
    return _git_in(VAULT, *args)


def vault():
    """Branch corrente, ultimi commit, modifiche non committate e branch non ancora uniti al main."""
    non_uniti = [b for b in _git("branch", "--no-merged", "main").splitlines() if b.strip()]
    return {
        "branch": _git("branch", "--show-current"),
        "ultimiCommit": _git("log", "-4", "--format=%h %s").splitlines(),
        "nonCommittate": len([r for r in _git("status", "--porcelain").splitlines() if r.strip()]),
        "branchNonUniti": [b.strip() for b in non_uniti],
    }


def ollama():
    """Modelli caricati in memoria da Ollama, o None se il server non risponde."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except OSError:
        return None


def prossimo_radar(oggi):
    """Il prossimo lunedì alle 07:00, quando n8n scrive la nuova inbox."""
    giorni = (7 - oggi.weekday()) % 7 or 7
    return (oggi + timedelta(days=giorni)).strftime("%Y-%m-%d") + " 07:00"


def log_avvio():
    """Ultime righe del log di avvio al login."""
    file = percorsi.cartella_log() / "second-brain-avvio.log"
    if not file.exists():
        return []
    return file.read_text(encoding="utf-8", errors="replace").splitlines()[-4:]


def stato():
    oggi = datetime.now()
    return {
        "generato": oggi.isoformat(timespec="seconds"),
        "progetti": progetti(),
        "inbox": inbox(),
        "radar": radar(),
        "job": job(),
        "vault": vault(),
        "ollama": ollama(),
        "prossimoRadar": prossimo_radar(oggi),
        "logAvvio": log_avvio(),
    }


def swap_usato_mb(testo):
    """Swap in uso in MB dall'output di `sysctl vm.swapusage`, es. 'total = 2048.00M  used = 3906.56M'."""
    m = re.search(r"used = ([\d.]+)([MG])", testo)
    if not m:
        return None
    return float(m.group(1)) * (1024 if m.group(2) == "G" else 1)


def memoria(piattaforma=None, ram=None):
    """RAM totale e swap in uso. La RAM la legge modello.py su ogni sistema; lo swap lo sa leggere solo macOS (sysctl): altrove None."""
    totale = (ram or modello_modulo.ram_gb)()
    swap = None
    if (piattaforma or sys.platform) == "darwin":
        try:
            c = {**os.environ, "LC_ALL": "C"}  # come per ps: con la locale italiana i decimali hanno la virgola
            swap = swap_usato_mb(subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, encoding="utf-8", timeout=5, env=c).stdout)
        except (OSError, subprocess.SubprocessError):
            pass
    return {"totaleGb": round(totale, 1) if totale else None, "swapUsatoMb": swap}


def processi_ollama():
    """Processi Ollama in esecuzione: memoria residente in MB e CPU in percentuale. Su Windows (niente `ps`) l'elenco è vuoto."""
    # LC_ALL=C: con la locale italiana ps scrive la CPU con la virgola e il float non la legge.
    try:
        r = subprocess.run(["ps", "-axo", "pid=,rss=,%cpu=,command="], capture_output=True, text=True, encoding="utf-8", timeout=5,
                           env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for riga in r.stdout.splitlines():
        if "ollama" not in riga or "ps -axo" in riga:
            continue
        try:
            pid, rss, cpu, comando = riga.split(None, 3)
            out.append({"pid": int(pid), "rssMb": round(int(rss) / 1024), "cpu": float(cpu), "comando": comando[:60]})
        except ValueError:
            continue
    return out


def ollama_modelli():
    """Modelli caricati in memoria da Ollama, con quanta parte gira sulla GPU."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            modelli = json.load(r).get("models", [])
    except OSError:
        return None
    return [
        {
            "nome": m["name"],
            "gb": round(m["size"] / 1024**3, 2),
            "gpuPct": round(100 * m.get("size_vram", 0) / m["size"]) if m.get("size") else None,
        }
        for m in modelli
    ]


def schede_modelli(tags, in_memoria, usi):
    """Le schede dei modelli scaricati: nome, dimensioni, quantizzazione, data, se sono in memoria e da cosa sono usati.

    tags: elenco di /api/tags; in_memoria: nomi in /api/ps; usi: {nome modello: a cosa serve nel radar}."""
    def uso(nome):
        return next((v for k, v in usi.items() if nome == k or nome.startswith(k + ":")), None)
    return [{
        "nome": m["name"], "gb": round(m["size"] / 1024**3, 2), "parametri": m.get("details", {}).get("parameter_size", ""),
        "quantizzazione": m.get("details", {}).get("quantization_level", ""), "famiglia": m.get("details", {}).get("family", ""),
        "scaricato": m.get("modified_at", "")[:10], "inMemoria": m["name"] in in_memoria, "usatoDa": uso(m["name"]),
    } for m in sorted(tags, key=lambda x: -x["size"])]


def ollama_installati():
    """Modelli scaricati in Ollama, o None se non risponde. Il radar usa un modello per l'embedding e uno per il giudizio."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            tags = json.load(r).get("models", [])
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            in_memoria = {m["name"] for m in json.load(r).get("models", [])}
    except (OSError, ValueError):
        return None
    usi = {n: u for n, u in ((modello_modulo.scelta("radar_embedding", VAULT)[1] or None, "embedding del radar"), (modello_modulo.scelta("radar_giudizio", VAULT)[1] or None, "giudizio del radar")) if n}
    return schede_modelli(tags, in_memoria, usi)


def chiamate(ultime=200):
    """Riepilogo delle chiamate ai modelli registrate dal radar: per operazione, con medie."""
    file = VAULT / "radar" / ".prestazioni.jsonl"
    if not file.exists():
        return {"totale": 0, "perOperazione": {}, "ultime": []}
    righe = [json.loads(r) for r in file.read_text(encoding="utf-8").splitlines() if r.strip()]
    per_op = {}
    for r in righe:
        g = per_op.setdefault(r["operazione"], {"chiamate": 0, "durataMedia": 0.0, "tokenAlSecondo": []})
        g["chiamate"] += 1
        g["durataMedia"] += r["durata_s"]
        if r.get("token_al_secondo"):
            g["tokenAlSecondo"].append(r["token_al_secondo"])
    for g in per_op.values():
        g["durataMedia"] = round(g["durataMedia"] / g["chiamate"], 2)
        velocita = g.pop("tokenAlSecondo")
        g["tokenAlSecondoMedia"] = round(sum(velocita) / len(velocita), 1) if velocita else None
    return {"totale": len(righe), "perOperazione": per_op, "ultime": righe[-ultime:][::-1][:20]}


VOCE_PIANO = re.compile(r"^- \[( |x|X|~)\] (.+?)\s*$")
TAG = re.compile(r"(?:^|\s)#([A-Za-z][\w-]*)")
STATI = {"da_fare": " ", "in_corso": "~", "fatto": "x"}
STATO_DA_CASELLA = {" ": "da_fare", "~": "in_corso", "x": "fatto", "X": "fatto"}
DATA_PIANO = re.compile(r"^(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?) — (.+)$")


def piano():
    """Sezioni e voci di docs/piano.md."""
    return leggi_sezioni(VAULT / "docs" / "piano.md")


def scadenze(file=None):
    """Voci piatte di docs/scadenze.md, stesso formato del piano."""
    sezioni = leggi_sezioni(file or VAULT / "docs" / "scadenze.md")
    return [v for s in sezioni for v in s["voci"]]


def leggi_sezioni(file):
    """Sezioni e voci di un file con checkbox: fatto o no, data se c'è, testo."""
    if not file.exists():
        return []
    sezioni = []
    for riga in file.read_text(encoding="utf-8").splitlines():
        s = SEZIONE.match(riga)
        if s:
            sezioni.append({"titolo": s.group(1), "voci": []})
            continue
        v = VOCE_PIANO.match(riga)
        if v and sezioni:
            testo = v.group(2)
            d = DATA_PIANO.match(testo)
            grezzo = d.group(2) if d else testo
            t = TAG.search(grezzo)
            stato = STATO_DA_CASELLA[v.group(1)]
            sezioni[-1]["voci"].append({
                "fatto": stato == "fatto",
                "stato": stato,
                "data": d.group(1) if d else None,
                "testo": grezzo,
                "grezzo": grezzo,
                "tag": t.group(1).lower() if t else None,
                # testo senza il primo tag, spazi compattati
                "vista": " ".join((grezzo[:t.start(1) - 1] + grezzo[t.end(1):]).split()) if t else grezzo,
            })
    return sezioni


FILE_SPUNTE = {"piano": "piano.md", "scadenze": "scadenze.md"}


def imposta_fatto(fonte, data, testo, fatto, cartella=None):
    imposta_stato(fonte, data, testo, "fatto" if fatto else "da_fare", cartella)


def _trova_voce(righe, data, testo):
    """Indice della riga della voce (anche già fatta, anche senza tag). LookupError: assente. RuntimeError("doppia"): più voci uguali."""
    trovate = []
    for i, riga in enumerate(righe):
        v = VOCE_PIANO.match(riga.rstrip("\r\n"))
        if not v:
            continue
        d = DATA_PIANO.match(v.group(2))
        if (d.group(1) if d else None) == data and (d.group(2) if d else v.group(2)) == testo:
            trovate.append(i)
    if not trovate:
        raise LookupError(testo)
    if len(trovate) > 1:
        raise RuntimeError("doppia")
    return trovate[0]


def imposta_stato(fonte, data, testo, stato, cartella=None):
    """Mette la voce di docs/<fonte>.md con questa data e questo testo in stato da_fare, in_corso o fatto; cambia solo la casella.
    ValueError: fonte o stato non previsti. LookupError: voce non trovata. RuntimeError: più voci uguali."""
    if fonte not in FILE_SPUNTE or stato not in STATI:
        raise ValueError(fonte if fonte not in FILE_SPUNTE else stato)
    file = (cartella or VAULT / "docs") / FILE_SPUNTE[fonte]
    with BLOCCO_PIANO:  # senza, due spunte insieme si cancellano a vicenda (o cancellano il file temporaneo dell'altra)
        with open(file, encoding="utf-8", newline="") as f:  # newline="": CRLF resta com'è
            righe = f.read().splitlines(keepends=True)
        i = _trova_voce(righe, data, testo)
        righe[i] = righe[i][:3] + STATI[stato] + righe[i][4:]
        _scrivi_atomico(file, righe)


def _scrivi_atomico(file, righe):
    """Scrittura atomica: un file temporaneo per chiamata e os.replace, così un errore a metà non lascia un piano troncato.
    Da chiamare con BLOCCO_PIANO già preso."""
    fd, nome_tmp = tempfile.mkstemp(dir=str(file.parent), suffix=".tmp")
    tmp = Path(nome_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("".join(righe))
        os.chmod(tmp, file.stat().st_mode & 0o777)  # mkstemp crea 0600: il piano resta leggibile come prima
        os.replace(tmp, file)
    finally:
        tmp.unlink(missing_ok=True)


TAG_NUOVO = re.compile(r"[A-Za-z][\w-]*")
CATEGORIE_VIETATE = ("Cc", "Cf", "Zl", "Zp", "Cs")  # controllo, formato (bidi, zero-width), separatori di riga, surrogati
TESTO_MASSIMO = 200


def aggiungi_voce(tag, testo, vault=None):
    """Aggiunge `- [ ] #tag testo` a docs/piano.md e ritorna la riga: dopo l'ultima voce APERTA con lo stesso tag (le fatte stanno
    magari in «Fatti»), altrimenti in fondo a «Prossimi giorni», altrimenti in fondo al file (con «## Prossimi giorni» se il file non ha sezioni). ValueError: tag o testo non validi, o tag di un progetto del lavoro.
    RuntimeError("doppia"): la voce c'è già."""
    vault = vault or VAULT
    if not (isinstance(tag, str) and TAG_NUOVO.fullmatch(tag) and isinstance(testo, str)):
        raise ValueError("tag o testo")
    testo = testo.strip()
    if (not testo or len(testo) > TESTO_MASSIMO or "<" in testo or ">" in testo
            or any(unicodedata.category(c) in CATEGORIE_VIETATE for c in testo)):
        raise ValueError("testo")
    if progetti_indice(vault).get(tag.lower(), {}).get("lavoro"):
        raise ValueError("lavoro")
    file = vault / "docs" / "piano.md"
    grezzo = "#%s %s" % (tag, testo)
    with BLOCCO_PIANO:
        with open(file, encoding="utf-8", newline="") as f:
            righe = f.read().splitlines(keepends=True)
        eol = "\r\n" if righe and righe[0].endswith("\r\n") else "\n"
        voci = [(i, m.group(1), m.group(2)) for i, r in enumerate(righe) if (m := VOCE_PIANO.match(r.rstrip("\r\n")))]
        if any(t.lower() == grezzo.lower() for _, _, t in voci):  # il tag conta senza maiuscole, come nel parser
            raise RuntimeError("doppia")
        stessa = [i for i, c, t in voci if c in " ~" and (m := TAG.search(t)) and m.group(1).lower() == tag.lower()]
        if stessa:
            pos = stessa[-1] + 1
        else:
            sez = next((i for i, r in enumerate(righe) if r.strip() == "## Prossimi giorni"), None)
            pos = len(righe)
            if sez is None and not any(SEZIONE.match(r.rstrip("\r\n")) for r in righe):  # senza sezioni il parser ignora le voci
                if righe and not righe[-1].endswith("\n"):
                    righe[-1] += eol
                righe.append("## Prossimi giorni" + eol)
                pos = len(righe)
            if sez is not None:
                pos = sez + 1
                for i in range(sez + 1, len(righe)):
                    if SEZIONE.match(righe[i].rstrip("\r\n")):
                        break
                    if VOCE_PIANO.match(righe[i].rstrip("\r\n")):
                        pos = i + 1
        if pos and not righe[pos - 1].endswith("\n"):
            righe[pos - 1] += eol
        righe.insert(pos, "- [ ] %s%s" % (grezzo, eol))
        _scrivi_atomico(file, righe)
    return "- [ ] " + grezzo


def _momento(data):
    """(momento, ora_nota) di 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM'; senza ora conta la fine della giornata. None se la data non è valida."""
    try:
        if len(data) == 16:
            return datetime.strptime(data, "%Y-%m-%d %H:%M"), True
        return datetime.strptime(data, "%Y-%m-%d").replace(hour=23, minute=59), False
    except ValueError:
        return None


def oggi(data, piano_file=None, scadenze_file=None):
    """Cosa fare alla data indicata: voci con data (ordinate, con ritardo), voci senza data e primo passo di ogni progetto."""
    voci = [("piano", v) for s in leggi_sezioni(piano_file or VAULT / "docs" / "piano.md") for v in s["voci"]]
    voci += [("scadenze", v) for v in scadenze(scadenze_file)]
    con_data, senza_data = [], []
    for fonte, v in voci:
        if v["fatto"]:
            continue
        momento = _momento(v["data"]) if v["data"] else None
        if momento is None:
            senza_data.append({"fonte": fonte, "testo": v["testo"]})
            continue
        con_data.append((momento[0], {
            "fonte": fonte,
            "testo": v["testo"],
            "data": v["data"],
            "oraNota": momento[1],
            "inRitardo": momento[0] < data,
        }))
    for p in progetti():
        if p["primoPasso"]:
            senza_data.append({"fonte": "progetto:" + p["nome"], "testo": p["primoPasso"]})
    con_data.sort(key=lambda c: c[0])
    return {"conData": [c for _, c in con_data], "senzaData": senza_data}


MESI = "gen feb mar apr mag giu lug ago set ott nov dic".split()
GIORNI = "lun mar mer gio ven sab dom".split()


RIGA_LAVORO = re.compile(r"^\| \[\[projects" "/" "lavoro" r"/([^/\\|]+)/STATE")  # percorso spezzato: il template non lo contiene per intero


def progetti_indice(vault):
    """Nome minuscolo -> {nome, priorita, cartelle} dalle righe di INDEX e dalle righe `Repo:` degli STATE.
    Decide dal percorso nell'INDEX: la cartella del lavoro non si legge mai."""
    out = {}
    for riga in (vault / "projects" / "INDEX.md").read_text(encoding="utf-8").splitlines():
        celle = [c.strip() for c in riga.split("|")]  # il pipe del wikilink è escapato (\|): la priorità è la cella 5
        w = RIGA_LAVORO.match(riga)
        if w:  # solo il nome dalla riga dell'INDEX: nessun file del lavoro viene letto
            out[w.group(1).lower()] = {"nome": w.group(1), "priorita": celle[5] if len(celle) > 5 else None, "cartelle": [], "lavoro": True}
            continue
        m = RIGA_PROGETTO.match(riga)
        if not m or m.group(1) == "lavoro":
            continue
        nome = m.group(1)
        stato = vault / "projects" / nome / "STATE.md"
        repo = repo_di(stato.read_text(encoding="utf-8")) if stato.exists() else []
        out[nome.lower()] = {"nome": nome, "priorita": celle[5] if len(celle) > 5 else None,
                             "cartelle": [Path(r) for r in repo if r != "nessuno"]}
    return out


def _cartella_di(tipo, info, vault):
    """Cartella di un nodo: prima del progetto che esiste, altrimenti il vault; None per i progetti del lavoro o se risolve nella loro cartella."""
    lavoro = (vault / "projects" / "lavoro").resolve()
    if (info or {}).get("lavoro"):
        return None
    scelta = vault if tipo != "progetto" else next((c for c in (info or {}).get("cartelle", []) if c.exists()), vault)
    if scelta.resolve().is_relative_to(lavoro):  # resolve(): un symlink verso lavoro non passa
        return None
    return scelta


def cartella_nodo(nodo, vault):
    info = progetti_indice(vault).get(nodo["nome"].lower()) if nodo["tipo"] == "progetto" else None
    return _cartella_di(nodo["tipo"], info, vault)


def _str_o_none(p):
    return None if p is None else str(p)


def _prossima(aperte, adesso):
    """Prima azione da fare: (nodo, voce, motivo) dal primo gradino che trova qualcosa, o None."""
    for filtro, chiave, motivo in (
        (lambda r: r[2], lambda r: r[3], lambda mo: "in ritardo dal %d %s" % (mo.day, MESI[mo.month - 1])),
        (lambda r: r[1]["stato"] == "in_corso", None, lambda mo: "in corso"),
        (lambda r: r[3] and r[3].date() <= adesso.date() + timedelta(days=7), lambda r: r[3],
         lambda mo: "scade %s %d" % (GIORNI[mo.weekday()], mo.day)),
        (lambda r: r[4], None, lambda mo: "priorità alta"),
        (lambda r: True, None, lambda mo: "primo passo aperto"),
    ):
        trovate = [r for r in aperte if filtro(r)]
        if trovate:
            r = min(trovate, key=chiave) if chiave else trovate[0]  # min è stabile: a pari data vince l'ordine di file
            return r[0], r[1], motivo(r[3])
    return None


def mappa(adesso, piano_file=None, vault=None):
    """Nodi (progetti, argomenti, «Senza nodo») con i loro task di piano.md, prossima azione e conteggi."""
    vault = vault or VAULT
    indice = progetti_indice(vault)
    def nuovo(i):
        return {"nome": i["nome"], "tipo": "progetto", "priorita": i["priorita"],
                "haCartella": _cartella_di("progetto", i, vault) is not None,
                "cartella": _str_o_none(_cartella_di("progetto", i, vault)), "task": []}
    nodi = {n: nuovo(i) for n, i in indice.items() if not i.get("lavoro")}  # i progetti del lavoro senza voci non compaiono
    aperte = []  # (nome nodo, task, ritardo, momento, progetto alta), in ordine di file
    for sez in leggi_sezioni(piano_file or vault / "docs" / "piano.md"):
        for v in sez["voci"]:
            if v["tag"] is None and v["stato"] == "fatto":
                continue
            chiave = v["tag"] or "senza nodo"
            if chiave not in nodi and chiave in indice:  # progetto del lavoro con almeno una voce
                nodi[chiave] = nuovo(indice[chiave])
            if chiave not in nodi:
                nodi[chiave] = {"nome": v["tag"] or "Senza nodo", "tipo": "argomento" if v["tag"] else "senza",
                                "priorita": None, "haCartella": True, "cartella": str(vault), "task": []}
            nodo = nodi[chiave]
            momento = _momento(v["data"]) if v["data"] else None
            momento = momento[0] if momento else None
            aperta = v["stato"] != "fatto"
            ritardo = bool(aperta and momento and momento < adesso)
            t = {"data": v["data"], "testo": v["testo"], "vista": v["vista"], "stato": v["stato"], "ritardo": ritardo}
            nodo["task"].append(t)
            if aperta:
                aperte.append((nodo, t, ritardo, momento, nodo["priorita"] == "alta"))
    scelta = _prossima(aperte, adesso)
    prossima = None
    if scelta:
        n, t, motivo = scelta
        prossima = {"nodo": n["nome"], "data": t["data"], "testo": t["testo"], "vista": t["vista"], "stato": t["stato"], "motivo": motivo}
    conta = lambda f: sum(1 for r in aperte if f(r))
    aperti = lambda n: sum(1 for t in n["task"] if t["stato"] != "fatto")
    ordinati = sorted(nodi.values(), key=lambda n: (not (scelta and n is scelta[0]), -aperti(n), n["nome"].lower()))
    return {"nodi": ordinati, "prossima": prossima,
            "conteggi": {"da_fare": conta(lambda r: r[1]["stato"] == "da_fare"),
                         "in_corso": conta(lambda r: r[1]["stato"] == "in_corso"),
                         "in_ritardo": conta(lambda r: r[2])}}


def ultimo_controllo_skill():
    """Contenuto dell'ultimo daily/<settimana>-skill.json scritto dal controllo del venerdì, o None."""
    file = sorted((VAULT / "daily").glob("*-skill.json"), reverse=True)
    try:
        return json.loads(file[0].read_text(encoding="utf-8")) if file else None
    except (OSError, ValueError):
        return None


MODULI_NOTI = ("riservata", "radar", "bozze", "servizi", "assistente")


def moduli_attivi(vault=VAULT):
    """{modulo: vero/falso} dalle scelte di setup.py in config.json. Un vault senza la chiave `moduli` (nato prima del wizard) li mostra tutti;
    con la chiave (anche vuota) solo i moduli scelti: la pagina di un modulo non scelto non compare."""
    try:
        scelti = json.loads((Path(vault) / "config.json").read_text(encoding="utf-8")).get("moduli")
    except (OSError, ValueError):
        scelti = None
    if not isinstance(scelti, dict):
        return {m: True for m in MODULI_NOTI}
    return {m: bool(isinstance(scelti.get(m), dict) and scelti[m].get("attivo")) for m in MODULI_NOTI}


def modello_assistente(vault=VAULT):
    """{nome, locale} del modello scelto per l'assistente in config.json: la pagina lo scrive così com'è, senza dare per scontato che sia locale.
    locale è None se nessun modello è scelto (o la scelta non è valida)."""
    try:
        provider, nome = modello_modulo.scelta("assistente", vault)
    except (ValueError, modello_modulo.ModelloNonDisponibile):
        return {"nome": "nessuno", "locale": None}
    if provider == "ollama":
        return {"nome": nome, "locale": True}
    if provider == "claude":
        return {"nome": "Claude", "locale": False}
    return {"nome": "nessuno", "locale": None}


def calendario_al_modello(vault=VAULT):
    """Vero se l'assistente può ricevere gli appuntamenti. Con un modello locale sì; con Claude solo se l'hai permesso al setup
    (config.json, moduli.assistente.calendario_al_cloud): senza il consenso i titoli non lasciano il computer."""
    try:
        if modello_modulo.scelta("assistente", vault)[0] != "claude":
            return True
        cfg = json.loads((Path(vault) / "config.json").read_text(encoding="utf-8"))
        return cfg.get("moduli", {}).get("assistente", {}).get("calendario_al_cloud") is True
    except (OSError, ValueError, AttributeError, modello_modulo.ModelloNonDisponibile):
        return False


def configurazione_dati():
    """Skill, plugin, hook e MCP del globale, del vault e dei repo di projects/*/STATE.md (non la cartella riservata)."""
    progetti_repo = [("second-brain", VAULT)]
    for stato in sorted((VAULT / "projects").glob("*/STATE.md")):
        repo_progetto = repo_di(stato.read_text(encoding="utf-8"))
        for repo in repo_progetto:
            # With several repos the name says which one, so the panel has no two entries with the same name.
            nome = stato.parent.name + (" (%s)" % Path(repo).name if len(repo_progetto) > 1 else "")
            progetti_repo.append((nome, Path(repo)))
    return configurazione.raccogli(progetti_repo, ultimo_controllo_skill())


def prestazioni():
    return {
        "generato": datetime.now().isoformat(timespec="seconds"),
        "memoria": memoria(),
        "processiOllama": processi_ollama(),
        "modelli": ollama_modelli(),
        "chiamate": chiamate(),
        "claude": uso_claude(datetime.now()),
        "consumo": consumo_claude(datetime.now()),
        "installati": ollama_installati(),
        "discoLiberoGb": round(shutil.disk_usage("/").free / 1024**3),
    }


AZIONI = {"morning": "scripts/morning.py", "chiudi-giornata": "scripts/chiudi-giornata.py",
          "controllo-skill": "scripts/controllo-skill.py", "radar": "scripts/radar.py",
          "pulizia": "scripts/pulizia-settimanale.py", "bozze": "scripts/prepara-bozze.py",
          "richieste": "scripts/elabora-richieste.py"}
LOG_AZIONI = {"morning": "second-brain-morning.log", "chiudi-giornata": "second-brain-chiudi.log",
              "controllo-skill": "second-brain-skill.log", "radar": "second-brain-radar.log",
              "pulizia": "second-brain-pulizia.log", "bozze": "second-brain-bozze.log", "richieste": "second-brain-richieste.log"}
PROCESSI = {}  # azione -> processo avviato dalla dashboard
INIZI = {}  # azione -> quando la dashboard l'ha avviata (serve a decidere se il suo esito è più recente di quello di launchd)


def ambiente_azione():
    """Ambiente per gli script: il servizio launchd ha un PATH minimo, senza Homebrew né ~/.local/bin."""
    extra = [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    return {**os.environ, "PATH": os.pathsep.join(extra + [os.environ.get("PATH", "")])}  # «;» su Windows, «:» altrove


def avvia(nome, esegui=subprocess.Popen):
    """Lancia una delle azioni previste, in background, con il suo log. Il browser non passa argomenti."""
    if nome not in AZIONI:
        raise ValueError(nome)
    if nome in PROCESSI and PROCESSI[nome].poll() is None:
        raise RuntimeError(nome)
    with open(percorsi.cartella_log() / LOG_AZIONI[nome], "ab") as log:
        script = str(VAULT / AZIONI[nome])
        comando = [sys.executable, "-I", script] if script.endswith(".py") else ["/bin/bash", script]
        INIZI[nome] = datetime.now()
        PROCESSI[nome] = esegui(comando, cwd=str(VAULT), stdout=log,
                                stderr=subprocess.STDOUT, env=ambiente_azione(), start_new_session=True)
    return {"avviato": nome}


ULTIMI_AVVII = {}  # (data, testo) -> momento dell'ultimo avvio: ignora il doppio clic
BLOCCO_AVVII = threading.Lock()


def avvia_claude(data, testo, esegui=None, piano_file=None, vault=None, cartella_avvii=None, sistema=None, adesso=time.monotonic):
    """Apre il Terminale con `claude` nella cartella del nodo della voce e la mette in corso. Solo macOS.
    NotImplementedError: non è un Mac. LookupError: voce assente. RuntimeError con codice: doppia, cartella, ripetuto, apertura.
    Il testo della voce finisce solo in un file letto da `cat`: mai in una stringa di shell o di AppleScript."""
    if (sistema or sys.platform) != "darwin":
        raise NotImplementedError("solo macOS")
    esegui = esegui or subprocess.run
    vault = vault or VAULT
    piano_file = piano_file or vault / "docs" / "piano.md"
    trovati = [(n, t) for n in mappa(datetime.now(), piano_file, vault)["nodi"] for t in n["task"] if t["data"] == data and t["testo"] == testo]
    if not trovati:
        raise LookupError(testo)
    if len(trovati) > 1:
        raise RuntimeError("doppia")
    nodo, task = trovati[0]
    cartella = cartella_nodo(nodo, vault)
    if cartella is None:
        raise RuntimeError("cartella")
    with open(piano_file, encoding="utf-8", newline="") as f:  # prima di scrivere o aprire qualsiasi cosa: il file grezzo vede anche i [x] senza tag
        _trova_voce(f.read().splitlines(keepends=True), data, testo)
    chiave = (data, testo)
    with BLOCCO_AVVII:
        if chiave in ULTIMI_AVVII and adesso() - ULTIMI_AVVII[chiave] < 10:
            raise RuntimeError("ripetuto")
        ULTIMI_AVVII[chiave] = adesso()
    try:
        cartella_avvii = cartella_avvii or percorsi.cartella_log() / "avvii-claude"
        cartella_avvii.mkdir(mode=0o700, parents=True, exist_ok=True)
        for f in cartella_avvii.iterdir():  # file di avvii vecchi di una settimana
            if f.is_file() and f.stat().st_mtime < time.time() - 7 * 86400:
                f.unlink()
        base = cartella_avvii / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        file_prompt, file_comando = base.with_suffix(".txt"), base.with_suffix(".command")
        prompt = ("Task dal piano del vault (nodo #%s): %s. Lavoraci in questa cartella seguendo le regole del progetto; "
                  "quando hai finito dimmelo, la spunta la metto io dalla dashboard.") % (nodo["nome"], task["vista"])
        for file, contenuto, modo in (
                (file_prompt, prompt, 0o600),
                (file_comando, "#!/bin/zsh -l\ncd %s && exec claude \"$(cat %s)\"\n" % (shlex.quote(str(cartella)), shlex.quote(str(file_prompt))), 0o700)):
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, modo)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(contenuto)
        try:
            r = esegui(["/usr/bin/open", "-a", "Terminal", str(file_comando)], check=False, timeout=10)
        except subprocess.SubprocessError:
            raise RuntimeError("apertura")
        if r.returncode != 0:
            raise RuntimeError("apertura")
    except BaseException:
        ULTIMI_AVVII.pop(chiave, None)  # un avvio fallito si può riprovare subito
        raise
    out = {"avviato": True, "cartella": str(cartella)}
    try:
        imposta_stato("piano", data, testo, "in_corso", piano_file.parent)
    except (LookupError, RuntimeError, OSError):  # il Terminale è già aperto: il debounce resta, la spunta no
        out["avviso"] = "stato"
    return out


def esecuzioni():
    """Per ogni azione: se è in corso e le ultime righe del log. Poi gli ultimi commit del vault."""
    out = {}
    for nome, file in LOG_AZIONI.items():
        log = percorsi.cartella_log() / file
        righe = log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:] if log.exists() else []
        p = PROCESSI.get(nome)
        out[nome] = {"inCorso": p is not None and p.poll() is None, "ultimeRighe": righe}
    out["commit"] = _git("log", "-8", "--format=%h %s").splitlines()
    return out


def _uso_dal_vivo(file, cache):
    """Le percentuali che la barra di stato di Claude Code salva a ogni risposta (scripts/statusline-uso.py), se sono
    più fresche della copia in ~/.claude.json. Stessa forma della cache, così il resto del codice non cambia."""
    try:
        vivo = json.loads((file or Path.home() / ".claude" / "usage-live.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cache
    if cache and cache.get("fetchedAtMs", 0) >= vivo["salvato"] * 1000:
        return cache
    utilizzo = {}
    for chiave in ("five_hour", "seven_day"):
        f = vivo.get(chiave)
        if f and f.get("percentuale") is not None and f.get("rinnovo"):
            utilizzo[chiave] = {"utilization": f["percentuale"], "resets_at": datetime.fromtimestamp(f["rinnovo"], tz=timezone.utc).isoformat()}
    return {"fetchedAtMs": vivo["salvato"] * 1000, "utilization": utilizzo} if utilizzo else cache


FINESTRE_CLAUDE = {"five_hour": ("5 ore", timedelta(hours=5)), "seven_day": ("Settimana", timedelta(days=7))}


def uso_claude(adesso, file=None, live=None):
    """Percentuali d'uso di Claude Code, dalla copia che tiene in ~/.claude.json (legge solo quella chiave).

    Il file lo scrive Claude Code quando le chiede lui, non è un'interfaccia documentata: se la finestra è già
    stata rinnovata ('scaduto') la percentuale è di prima del rinnovo e non va letta come attuale.
    """
    try:
        cache = json.loads((file or Path.home() / ".claude.json").read_text(encoding="utf-8")).get("cachedUsageUtilization")
    except (OSError, ValueError):
        cache = None
    cache = _uso_dal_vivo(live, cache)
    if not cache:
        return {"finestre": [], "aggiornato": None}
    letto = datetime.fromtimestamp(cache["fetchedAtMs"] / 1000)
    finestre = []
    for chiave, (nome, durata) in FINESTRE_CLAUDE.items():
        f = (cache.get("utilization") or {}).get(chiave)
        if not f:
            continue
        rinnovo = datetime.fromisoformat(f["resets_at"]).astimezone().replace(tzinfo=None)
        inizio = rinnovo - durata
        finestre.append({"nome": nome, "percentuale": f["utilization"], "rinnovo": rinnovo.isoformat(timespec="minutes"),
                         "inizio": inizio.isoformat(timespec="minutes"), "scaduto": rinnovo <= adesso,
                         "trascorso": min(1, max(0, (adesso - inizio) / durata))})
    if finestre and finestre[0]["nome"] != "5 ore":  # nessuna finestra di 5 ore aperta: lo dice la pagina, non la nasconde
        finestre.insert(0, {"nome": "5 ore", "inattiva": True})
    return {"finestre": finestre, "aggiornato": letto.isoformat(timespec="minutes")}


CACHE_CONSUMO = {}  # chiave: (cartella, giorni) -> (momento, risultato): le sessioni sono grandi, si rileggono al massimo ogni 2 minuti


def consumo_claude(adesso, giorni=14, cartella=None):
    """Token per giorno di Claude Code, letti dalle sessioni locali (~/.claude/projects/*/*.jsonl).

    Conta input, output e scrittura in cache dei messaggi dell'assistente, senza la cache letta e una volta sola per
    messaggio. Non è il limite del piano: è quanto lavoro ha fatto Claude Code ogni giorno su questo Mac.
    """
    base = cartella or Path.home() / ".claude" / "projects"
    chiave = (str(base), giorni)
    if chiave in CACHE_CONSUMO and (adesso - CACHE_CONSUMO[chiave][0]).total_seconds() < 120:
        return CACHE_CONSUMO[chiave][1]
    inizio = (adesso - timedelta(days=giorni - 1)).date()
    per_giorno = {inizio + timedelta(days=d): {"token": 0, "messaggi": 0} for d in range(giorni)}
    visti = set()
    for file in Path(base).glob("*/*.jsonl"):
        try:
            if datetime.fromtimestamp(file.stat().st_mtime).date() < inizio:
                continue
            with file.open(encoding="utf-8", errors="replace") as righe:
                for riga in righe:
                    if '"usage"' not in riga:
                        continue
                    try:
                        r = json.loads(riga)
                    except ValueError:
                        continue
                    m = r.get("message") or {}
                    u, quando = m.get("usage"), r.get("timestamp")
                    if r.get("type") != "assistant" or not u or not quando or (m.get("id"), r.get("requestId")) in visti:
                        continue
                    visti.add((m.get("id"), r.get("requestId")))
                    giorno = datetime.fromisoformat(quando.replace("Z", "+00:00")).astimezone().date()
                    if giorno in per_giorno:
                        per_giorno[giorno]["token"] += u.get("input_tokens", 0) + u.get("output_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                        per_giorno[giorno]["messaggi"] += 1
        except OSError:
            continue
    risultato = {"giorni": [{"data": g.isoformat(), **v} for g, v in sorted(per_giorno.items())]}
    CACHE_CONSUMO[chiave] = (adesso, risultato)
    return risultato


def _progetti_con_repo():
    """Nome -> cartelle docs/ dei repo del progetto, dalle righe di INDEX e dalle righe `Repo:` degli STATE.
    Solo docs/, mai la radice del repo: sono le sole cartelle da cui la pagina serve immagini."""
    out = {}
    for riga in (VAULT / "projects" / "INDEX.md").read_text(encoding="utf-8").splitlines():
        m = RIGA_PROGETTO.match(riga)
        if m:
            repo_progetto = repo_di((VAULT / "projects" / m.group(1) / "STATE.md").read_text(encoding="utf-8"))
            out[m.group(1)] = [Path(r) / "docs" for r in repo_progetto if r != "nessuno"]
    return out


def post_calendari():
    """Un calendario per ogni `projects/<progetto>/post-<canale>.json` dei progetti in INDEX."""
    progetti = _progetti_con_repo()
    cartelle = [d for docs in progetti.values() for d in docs]
    out = []
    for c in post_modulo.scopri(VAULT / "projects", progetti):
        try:
            dati = post_modulo.carica(c["file"])
        except (OSError, ValueError):
            continue
        richieste = richieste_modulo.leggi(richieste_modulo.file_di(VAULT / "projects", c["progetto"], c["canale"]), c["progetto"], c["canale"])["richieste"]
        out.append({"progetto": c["progetto"], "canale": c["canale"], "richieste": richieste,
                    **post_modulo.per_la_pagina(dati, c["progetto"], c["canale"], cartelle)})
    return out


def post_richieste_aperte():
    """Quante bozze aspettano la tua approvazione, in tutti i calendari: il numero sul menu Post."""
    progetti = _progetti_con_repo()
    out = 0
    for c in post_modulo.scopri(VAULT / "projects", progetti):
        try:
            out += sum(1 for v in post_modulo.carica(c["file"]).get("voci", []) if v.get("stato") == "da approvare")
        except (OSError, ValueError):
            pass
    return out


def post_trova(progetto, canale):
    progetti = _progetti_con_repo()
    for c in post_modulo.scopri(VAULT / "projects", progetti):
        if c["progetto"] == progetto and c["canale"] == canale:
            return c["file"], [d for docs in progetti.values() for d in docs]
    return None, []


CALENDARIO = {"eventi": None, "errore": "", "quando": None, "in_corso": False, "assente": False, "avvisi": []}  # gli appuntamenti restano solo in memoria
BLOCCO_CALENDARIO = threading.Lock()
VALIDITA_CALENDARIO = 900  # secondi: leggere il Calendario è lento (da decine di secondi a minuti)


def _aggiorna_calendario():
    try:
        cal = calendario_modulo.provider(VAULT)
        if cal is None:  # nessun calendario collegato (config.json, o un sistema senza provider): la sezione resta vuota
            eventi, errore, avvisi = [], "", []
        else:
            nomi = cal.nomi()
            agenda_modulo.scrivi_config(VAULT / "docs" / "calendari.md", nomi)
            config = agenda_modulo.leggi_config(VAULT / "docs" / "calendari.md")
            eventi = cal.eventi(7, esclusi=[n for n, c in config.items() if not c["mostra"]])
            errore, avvisi = "", list(getattr(cal, "avvisi", []))
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:
        eventi, errore, avvisi, cal = None, str(e) or "Calendario non risponde", [], True
    with BLOCCO_CALENDARIO:
        CALENDARIO.update({"eventi": eventi, "errore": errore, "quando": datetime.now(), "in_corso": False, "assente": cal is None, "avvisi": avvisi})


def _calendario_in_background():
    """Gli appuntamenti dell'ultima lettura; se sono vecchi di oltre 5 minuti ne parte una nuova, senza far aspettare la pagina."""
    with BLOCCO_CALENDARIO:
        vecchio = CALENDARIO["quando"] is None or (datetime.now() - CALENDARIO["quando"]).total_seconds() > VALIDITA_CALENDARIO
        if vecchio and not CALENDARIO["in_corso"]:
            CALENDARIO["in_corso"] = True
            threading.Thread(target=_aggiorna_calendario, daemon=True).start()
        return dict(CALENDARIO)


def _calendario_o_errore():
    cal = calendario_modulo.provider(VAULT)
    if cal is None:
        raise ValueError("nessun calendario collegato")
    return cal


def _scadenze_prossime(adesso):
    """Voci con data da piano, scadenze, rinnovi dei servizi e post non ancora pubblicati."""
    voci = [{"fonte": f, "testo": v["testo"], "data": v["data"], "fatto": False}
            for f, lista in (("piano", [x for sez in leggi_sezioni(VAULT / "docs" / "piano.md") for x in sez["voci"]]), ("scadenze", scadenze(None)))
            for v in lista if not v["fatto"] and v["data"] and _momento(v["data"])]
    for p in servizi_modulo.servizi(VAULT / "docs" / "servizi.md"):
        for c in p["costi"]:
            if c.get("Rinnovo") and _momento(c["Rinnovo"][:10]):
                resto = c["Rinnovo"][10:].lstrip(", ")
                voci.append({"fonte": "rinnovo", "testo": "Rinnovo di " + c["Voce"] + (" (" + resto + ")" if resto else ""), "data": c["Rinnovo"][:10]})
    for cal in post_calendari():
        for v in cal["voci"]:
            if v.get("stato") != "pubblicato" and _momento(v.get("data", "")):
                voci.append({"fonte": "post", "testo": "Post: " + v["titolo"], "data": v["data"] + (" " + v["ora"][:5] if v["ora"][:2].isdigit() and v["ora"][2:3] == ":" else "")})
    return voci


def aspetta(adesso=None):
    adesso = adesso or datetime.now()
    c = _calendario_in_background()
    config = agenda_modulo.leggi_config(VAULT / "docs" / "calendari.md")
    voci = agenda_modulo.unisci(c["eventi"] or [], _scadenze_prossime(adesso), adesso, 7, config)
    rapporto = radar()
    return {"voci": voci,
            "calendario": {"stato": "errore" if c["errore"] else "ok" if c["eventi"] is not None else "caricamento",
                           "errore": c["errore"], "aggiornato": c["quando"].isoformat(timespec="minutes") if c["quando"] else None,
                           "assente": c["assente"], "avvisi": c["avvisi"]},
            "novita": {"data": rapporto["data"] if rapporto else None, "daLeggere": (rapporto["daLeggere"] if rapporto else [])[:3]}}


def _plurale(n, uno, molti):
    return "%d %s" % (n, uno if n == 1 else molti)


def voci_attesa(bozze_rete, controllo_skill, avvii_dati):
    """«Aspetta te»: ciò che chiede una decisione adesso, in ordine di urgenza. Ogni voce porta alla pagina dove decidere (`link`).

    Job non riusciti (fallito, mancato, mai partito), aggiornamenti di skill già scansionati (stato «nuova»), bozze da pubblicare.
    Un job «saltato» (ha girato e non c'era nulla da fare) o in ritardo non è un problema da decidere."""
    voci = []
    job = [j for j in avvii_dati.get("job", []) if isinstance(j, dict) and j.get("stato") in ("fallito", "mancato", "mai")]
    for j in job:
        voci.append({"tipo": "job_fallito", "testo": "%s: %s" % (j.get("nome", "?"), j.get("motivo", "")), "link": "avvii"})
    # Senza controllo (nessun file, illeggibile, forma inattesa) il dato manca: None, non «0 skill da aggiornare»
    elenco = controllo_skill.get("skill") if isinstance(controllo_skill, dict) else None
    skill = [s for s in elenco if isinstance(s, dict) and s.get("stato") == "nuova"] if isinstance(elenco, list) else None
    if skill:
        voci.append({"tipo": "skill_da_aggiornare", "testo": _plurale(len(skill), "aggiornamento di skill", "aggiornamenti di skill"), "link": "configurazione"})
    bozze = [b for lista in bozze_rete.values() if isinstance(lista, list) for b in lista if isinstance(b, dict) and b.get("stato") == "da pubblicare"]
    if bozze:
        voci.append({"tipo": "bozza_da_pubblicare", "testo": _plurale(len(bozze), "bozza da pubblicare", "bozze da pubblicare"), "link": "post"})
    n = len(voci)
    fatto = "Niente aspetta te." if not n else "Una cosa aspetta te." if n == 1 else "%d cose aspettano te." % n
    return {"voci": voci, "fatto": fatto, "conteggi": {"job": len(job), "skill": None if skill is None else len(skill), "bozze": len(bozze)}}


def attesa():
    # Le bozze si contano solo se il modulo è attivo: «Apri» porterebbe a una pagina che il modulo nasconde.
    bozze = bozze_per_rete() if moduli_attivi().get("bozze") else {}
    return voci_attesa(bozze, ultimo_controllo_skill(), avvii())


def servizi_dati(adesso=None):
    """I servizi di ogni progetto con proiezione, verdetti, spesa mensile e costo del passaggio ai piani a pagamento."""
    oggi = (adesso or datetime.now()).date()
    out = []
    for p in servizi_modulo.servizi(VAULT / "docs" / "servizi.md"):
        misure = []
        for m in p["misure"]:
            try:
                misure.append(limiti_modulo.analizza(m, oggi))
            except (KeyError, ValueError):
                continue  # una riga mal scritta non rompe la pagina
        verdetti = {}
        for servizio in {m["servizio"] for m in misure}:
            verdetti[servizio] = limiti_modulo.verdetto_servizio([m for m in misure if m["servizio"] == servizio])
        p["analisi"] = {"misure": misure, "verdetti": verdetti, "spesaMensile": limiti_modulo.spesa_mensile(p["costi"]),
                        "saltoDiPiano": limiti_modulo.salto_di_piano(p["piani"], verdetti), "etichette": limiti_modulo.ETICHETTA}
        out.append(p)
    return out


def avvii():
    vivi = [n for n, p in PROCESSI.items() if p.poll() is None]
    jobs = jobs_pianificati(VAULT)
    esiti = {n: avvii_modulo.ultimo_exit(p["Label"]) for n, p in jobs.items() if n in avvii_modulo.JOB_PIANIFICATI and p.get("Label")}
    a_mano = {n: (INIZI[n], p.poll()) for n, p in PROCESSI.items() if n in INIZI and p.poll() is not None}
    return avvii_modulo.avvii(datetime.now(), jobs, percorsi.cartella_log(),
                              in_corso=vivi, acceso=avvii_modulo.avvio_mac(), azioni=AZIONI, esiti=esiti, giri_a_mano=a_mano)


BOZZE = VAULT / "content" / "linkedin"
RETI = {"linkedin": BOZZE, "instagram": VAULT / "content" / "instagram"}


STATO_BOZZE = VAULT / "content" / "stato.json"  # {"linkedin/<file>.md": {"stato": "pubblicata", "data": "2026-10-30"}}
STATI_BOZZA = ("da pubblicare", "pubblicata", "scartata")


def stati_bozze(file=STATO_BOZZE):
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def imposta_stato_bozza(rete, nome, stato, adesso=None, file=STATO_BOZZE):
    """Segna una bozza come pubblicata o scartata (o la rimette in coda). Il nome deve essere di una bozza esistente."""
    if not all(isinstance(x, str) for x in (rete, nome, stato)) or rete not in RETI or stato not in STATI_BOZZA or not any(b["nome"] == nome for b in bozze(RETI[rete])):
        raise ValueError("bozza o stato non validi")
    stati = stati_bozze(file)
    if stato == "da pubblicare":
        stati.pop(rete + "/" + nome, None)
    else:
        stati[rete + "/" + nome] = {"stato": stato, "data": (adesso or datetime.now()).date().isoformat()}
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(stati, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, file)


def bozze(cartella=BOZZE, stati=None):
    """Bozze di una rete: titolo, testo da copiare, immagine (<nome>.png, o <nome>-schema.png) se esiste, stato."""
    if not cartella.is_dir():
        return []
    out = []
    for file in sorted(cartella.glob("*.md"), reverse=True):
        righe = file.read_text(encoding="utf-8").splitlines()
        titolo = righe[0].removeprefix("# ").strip() if righe else file.stem
        testo = "\n".join(r for r in righe[1:] if not r.lstrip("[").startswith("Immagine")).strip()
        immagine = next((i for i in (file.with_suffix(".png"), file.with_name(file.stem + "-schema.png")) if i.is_file()), None)
        st = (stati or {}).get(cartella.name + "/" + file.name) or {}
        out.append({"nome": file.name, "titolo": titolo, "testo": testo, "immagine": immagine.name if immagine else None,
                    "stato": st.get("stato", "da pubblicare"), "data": st.get("data")})
    return out


def bozze_per_rete():
    stati = stati_bozze()
    return {rete: bozze(cartella, stati) for rete, cartella in RETI.items()}


def immagine_bozza(nome, cartella=BOZZE):
    """Percorso dell'immagine solo se è tra quelle elencate da bozze(): il nome dalla richiesta non apre altri file."""
    for b in bozze(cartella):
        if b["immagine"] == nome:
            return cartella / nome
    return None


# Rotte GET che rispondono con JSON: percorso -> funzione senza argomenti (lambda: i test possono sostituire le funzioni del modulo)
ROTTE_JSON = {
    "/api/stato": lambda: stato(),
    "/api/piano": lambda: piano(),
    "/api/oggi": lambda: oggi(datetime.now()),
    "/api/attesa": lambda: attesa(),
    "/api/moduli": lambda: {**moduli_attivi(), "modello": modello_assistente()},
    "/api/configurazione": lambda: configurazione_dati(),
    "/api/prestazioni": lambda: prestazioni(),
    "/api/esecuzioni": lambda: esecuzioni(),
    "/api/servizi": lambda: servizi_dati(),
    "/api/aspetta": lambda: aspetta(),
    "/api/post/aperte": lambda: {"aperte": post_richieste_aperte()},
    "/api/post": lambda: post_calendari(),
    "/api/avvii": lambda: avvii(),
    "/api/bozze": lambda: bozze_per_rete(),
    "/api/mappa": lambda: mappa(datetime.now()),
}
# Le sole risorse statiche servite: il nome non viene mai dal percorso della richiesta
STATICI = {"/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
           "/mappa.js": ("mappa.js", "text/javascript; charset=utf-8"),
           "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8")}


class Gestore(BaseHTTPRequestHandler):
    def do_POST(self):
        # Un sito aperto nel browser non può mandare X-Azione: la richiesta con questo header richiede una preflight
        # che il server non accetta, quindi solo la dashboard può avviare un'azione.
        if self.headers.get("Host") not in HOST_OK or self.headers.get("X-Azione") != "conferma":
            self.send_error(403)
            return
        percorso = self.path.split("?", 1)[0]
        if percorso == "/api/spunte":
            self._spunta()
            return
        if percorso in ("/api/mappa/stato", "/api/mappa/avvia", "/api/mappa/nuovo"):
            self._mappa_scrive(percorso.rsplit("/", 1)[1])
            return
        if percorso == "/api/radar/feedback":
            self._vota()
            return
        if percorso == "/api/bozze/stato":
            self._bozza_stato()
            return
        if percorso == "/api/post/stato":
            self._post_stato()
            return
        if percorso == "/api/servizi/misura":
            self._servizi_misura()
            return
        if percorso == "/api/assistente/chiedi":
            self._assistente_chiedi()
            return
        if percorso in ("/api/assistente/proponi", "/api/assistente/applica", "/api/assistente/annulla"):
            self._assistente_scrive(percorso.rsplit("/", 1)[1])
            return
        if percorso in ("/api/post/richiesta", "/api/post/richiesta/annulla"):
            self._post_richiesta(percorso.endswith("/annulla"))
            return
        if percorso in ("/api/configurazione/interruttore", "/api/configurazione/aggiorna"):
            self._configura(percorso.rsplit("/", 1)[1])
            return
        if not percorso.startswith("/api/azioni/"):
            self.send_error(404)
            return
        try:
            esito = avvia(percorso.removeprefix("/api/azioni/"))
        except ValueError:
            self.send_error(404)
            return
        except RuntimeError:
            self.send_error(409)
            return
        self._json(esito)

    def _spunta(self):
        try:
            corpo = self._corpo_json()
            fonte, data, testo, fatto = corpo["fonte"], corpo.get("data"), corpo["testo"], corpo["fatto"]
            valido = isinstance(fatto, bool) and isinstance(fonte, str) and isinstance(testo, str) and (data is None or isinstance(data, str))
        except (ValueError, KeyError, TypeError, AttributeError):
            valido = False
        if not valido:
            self.send_error(400)
            return
        try:
            imposta_fatto(fonte, data, testo, fatto)
        except ValueError:
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        except RuntimeError:
            self.send_error(409)
            return
        except OSError:
            self.send_error(500)
            return
        self._json({"fatto": fatto})

    def _mappa_scrive(self, azione):
        """azione: «stato», «avvia» o «nuovo»."""
        try:
            corpo = self._corpo_json()
            data, testo = corpo.get("data"), corpo["testo"]
            stato_nuovo = corpo["stato"] if azione == "stato" else None
            tag = corpo["tag"] if azione == "nuovo" else None
            valido = (isinstance(testo, str) and (data is None or isinstance(data, str))
                      and (azione != "stato" or isinstance(stato_nuovo, str)) and (azione != "nuovo" or isinstance(tag, str)))
        except (KeyError, TypeError, AttributeError):
            valido = False
        if not valido:
            self.send_error(400)
            return
        try:
            if azione == "avvia":
                esito = avvia_claude(data, testo)
            elif azione == "nuovo":
                esito = {"ok": True, "riga": aggiungi_voce(tag, testo)}
            else:
                imposta_stato("piano", data, testo, stato_nuovo)
                esito = {"ok": True}
        except ValueError:
            self.send_error(400)
            return
        except NotImplementedError:
            self.send_error(501)
            return
        except LookupError:
            self.send_error(404)
            return
        except RuntimeError as e:
            self._json({"errore": str(e)}, 409)
            return
        except OSError:
            self.send_error(500)
            return
        self._json(esito)

    def _vota(self):
        try:
            corpo = self._corpo_json()
            titolo, giudizio = corpo["titolo"], corpo["giudizio"]
            valido = isinstance(titolo, str) and isinstance(giudizio, str)
        except (ValueError, KeyError, TypeError, AttributeError):
            valido = False
        if not valido:
            self.send_error(400)
            return
        try:
            vota_scartata(titolo, giudizio)
        except ValueError:
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        self._json({"giudizio": giudizio})

    def _post_scarica(self, percorso):
        """Una immagine (/scarica/<progetto>/<canale>/<id>/<n>, n da 1) o tutte in uno ZIP (/zip/<progetto>/<canale>/<id>)."""
        try:
            tipo, _, resto = percorso.removeprefix("/api/post/").partition("/")
            pezzi = resto.split("/")
            progetto, canale, id_voce = pezzi[:3]
            file, cartelle = post_trova(progetto, canale)
            voce = post_modulo.trova_voce(post_modulo.carica(file), id_voce) if file else None
            if voce is None:
                raise LookupError
            if tipo == "zip":
                self._invia(post_modulo.zip_voce(voce, cartelle), "application/zip",
                            scarica=post_modulo.nome_file(voce, 0, ".zip").replace("-00.zip", ".zip"))
                return
            n = int(pezzi[3])
            immagine = post_modulo.percorso_immagine({"voci": [voce]}, id_voce, n - 1, cartelle) if n >= 1 else None
            if immagine is None:
                raise LookupError
            self._invia(immagine.read_bytes(), post_modulo.ESTENSIONI[immagine.suffix.lower()],
                        scarica=post_modulo.nome_file(voce, n, immagine.suffix.lower()))
        except (LookupError, ValueError, IndexError, OSError):
            self.send_error(404)

    def _assistente_scrive(self, azione):
        """proponi: la frase diventa una scheda modificabile (non scrive). applica: scrive dopo il clic. annulla: toglie ciò che si è creato."""
        corpo = self._corpo_json(2048)
        if not isinstance(corpo, dict):
            self.send_error(400)
            return
        adesso = datetime.now()
        config = agenda_modulo.leggi_config(VAULT / "docs" / "calendari.md")
        scrivibili = [n for n, c in config.items() if c["scrivi"] and c["tipo"] != "lavoro"]
        try:
            if azione == "proponi":
                frase = corpo.get("frase")
                if not isinstance(frase, str) or not 2 <= len(frase.strip()) <= 400:
                    raise ValueError("frase non valida")
                campi, in_conflitto = assistente_modulo.proponi(frase.strip(), adesso, aspetta()["voci"])
                esito = {"proposta": campi, "conflitti": in_conflitto, "calendari": scrivibili}
            elif azione == "applica":
                valido = assistente_modulo.valida(corpo, adesso, scrivibili)
                creati = assistente_modulo.crea_evento(valido, _calendario_o_errore())
                with BLOCCO_CALENDARIO:  # l'evento nuovo si vede subito, senza rileggere tutto il Calendario
                    for c in creati:
                        (CALENDARIO["eventi"] if CALENDARIO["eventi"] is not None else []).append(
                            {"calendario": c["calendario"], "titolo": valido["titolo"], "inizio": valido["inizio"], "fine": valido["fine"], "tuttoIlGiorno": False, "uid": c["uid"]})
                esito = {"creati": creati}
            else:
                uid = corpo.get("uid")
                if not isinstance(uid, str):
                    raise ValueError("uid non valido")
                assistente_modulo.togli_evento(uid, _calendario_o_errore())
                with BLOCCO_CALENDARIO:
                    if CALENDARIO["eventi"] is not None:
                        CALENDARIO["eventi"] = [e for e in CALENDARIO["eventi"] if e.get("uid") != uid]
                esito = {"tolto": True}
        except ValueError as e:
            self._json({"errore": str(e)}, 400)
            return
        except LookupError as e:
            self._json({"errore": str(e)}, 404)
            return
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            self._json({"errore": "il Calendario non ha risposto: %s" % e}, 502)
            return
        self._json(esito)

    def _assistente_chiedi(self):
        domanda = (self._corpo_json(2048) or {}).get("domanda")
        if not isinstance(domanda, str) or not 2 <= len(domanda.strip()) <= 400:
            self.send_error(400)
            return
        dati = aspetta()
        if dati["calendario"]["stato"] != "ok":
            esito = {"pronto": False, "risposta": "Sto ancora leggendo il Calendario: riprova tra un minuto." if dati["calendario"]["stato"] == "caricamento"
                     else "Non riesco a leggere il Calendario (%s): senza non rispondo, per non dire che sei libero quando non lo sei." % dati["calendario"]["errore"]}
        else:
            inizio = datetime.now()
            try:
                risposta = assistente_modulo.chiedi(domanda.strip(), dati["voci"], [n["titolo"] for n in dati["novita"]["daLeggere"] if n.get("titolo")], inizio,
                                                     senza_calendario=dati["calendario"].get("assente", False) or not calendario_al_modello())
                esito = {"pronto": True, "risposta": risposta, "secondi": round((datetime.now() - inizio).total_seconds(), 1),
                         "calendario": dati["calendario"]}
            except RuntimeError as e:
                esito = {"pronto": False, "risposta": str(e)}
        self._json(esito)

    def _servizi_misura(self):
        corpo = self._corpo_json()
        try:
            progetto, servizio, misura, usato = corpo["progetto"], corpo["servizio"], corpo["misura"], corpo["usato"]
            valido = all(isinstance(x, (str, int, float)) for x in (progetto, servizio, misura, usato))
        except (KeyError, TypeError):
            valido = False
        if not valido:
            self.send_error(400)
            return
        try:
            with BLOCCO_RICHIESTE:
                servizi_modulo.aggiorna_misura(VAULT / "docs" / "servizi.md", progetto, servizio, misura, usato, datetime.now().date().isoformat())
        except ValueError:
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        self._json({"ok": True})

    def _post_richiesta(self, annulla):
        corpo = self._corpo_json(8192)
        try:
            progetto, canale = corpo["progetto"], corpo["canale"]
            valido = isinstance(progetto, str) and isinstance(canale, str)
        except (KeyError, TypeError):
            valido = False
        file, _ = post_trova(progetto, canale) if valido else (None, [])
        if not valido or file is None:
            self.send_error(400 if not valido else 404)
            return
        percorso_richieste = richieste_modulo.file_di(VAULT / "projects", progetto, canale)
        try:
            with BLOCCO_RICHIESTE:
                if annulla:
                    r = richieste_modulo.annulla(percorso_richieste, progetto, canale, corpo.get("id"), datetime.now())
                else:
                    ids = {v.get("id") for v in post_modulo.carica(file).get("voci", [])}
                    r = richieste_modulo.aggiungi(percorso_richieste, progetto, canale, corpo, ids, datetime.now())
                    try:
                        avvia("richieste")  # se è già in corso, riprende lui anche questa
                    except RuntimeError:
                        pass
        except ValueError:
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        self._json(r)

    def _bozza_stato(self):
        corpo = self._corpo_json() or {}
        try:
            imposta_stato_bozza(corpo.get("rete"), corpo.get("nome"), corpo.get("stato"))
        except ValueError:
            self.send_error(400)
            return
        self._json({"stato": corpo["stato"]})

    def _post_stato(self):
        corpo = self._corpo_json()
        try:
            progetto, canale, id_voce, stato = (corpo or {})["progetto"], corpo["canale"], corpo["id"], corpo["stato"]
            valido = all(isinstance(x, str) for x in (progetto, canale, id_voce, stato))
        except (KeyError, TypeError):
            valido = False
        if not valido:
            self.send_error(400)
            return
        file, _ = post_trova(progetto, canale)
        if file is None:
            self.send_error(404)
            return
        try:
            post_modulo.imposta_stato(file, id_voce, stato)
        except ValueError:
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        self._json({"stato": stato})

    def _corpo_json(self, massimo=4096):
        try:
            lunghezza = int(self.headers.get("Content-Length", ""))
            corpo = json.loads(self.rfile.read(lunghezza)) if 0 < lunghezza <= massimo else None
        except ValueError:
            return None
        return corpo if isinstance(corpo, dict) else None

    def _errore(self, codice, messaggio):
        self._json({"errore": messaggio}, codice)

    def _configura(self, azione):
        """Cambi ai file globali di Claude: interruttori di skill e plugin, aggiornamento di una skill già controllata."""
        corpo = self._corpo_json()
        if corpo is None or not isinstance(corpo.get("nome"), str):
            self._errore(400, "richiesta non valida")
            return
        if not BLOCCO_CONFIG.acquire(blocking=False):
            self._errore(409, "un altro cambio è in corso")
            return
        try:
            if azione == "interruttore":
                if not isinstance(corpo.get("attivo"), bool):
                    self._errore(400, "richiesta non valida")
                    return
                configurazione.imposta_interruttore(corpo.get("tipo"), corpo["nome"], corpo["attivo"])
                esito = {"nome": corpo["nome"], "attivo": corpo["attivo"]}
            else:
                esito = controllo_skill.aggiorna(corpo["nome"], corpo.get("atteso") or "")
            self._json(esito)
        except LookupError:
            self._errore(404, "non trovata: " + corpo["nome"])
        except (ValueError, RuntimeError) as e:
            self._errore(409 if isinstance(e, RuntimeError) else 400, str(e))
        except PermissionError as e:
            self._errore(403, str(e))
        except (OSError, subprocess.SubprocessError) as e:
            self._errore(500, "operazione non riuscita: " + type(e).__name__)
        finally:
            BLOCCO_CONFIG.release()

    def do_GET(self):
        if self.headers.get("Host") not in HOST_OK:
            self.send_error(403)
            return
        percorso = self.path.split("?", 1)[0]  # un parametro in più (es. ?v=2) non deve dare 404
        if percorso == "/":
            self._invia((HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif percorso in STATICI:
            nome, tipo = STATICI[percorso]
            self._invia((HERE / nome).read_bytes(), tipo)
        elif percorso in ROTTE_JSON:
            self._json(ROTTE_JSON[percorso]())
        elif percorso.startswith("/api/post/immagine/"):
            try:
                progetto, canale, id_voce, n = percorso.removeprefix("/api/post/immagine/").split("/")
                file, cartelle = post_trova(progetto, canale)
                immagine = post_modulo.percorso_immagine(post_modulo.carica(file), id_voce, int(n), cartelle) if file else None
            except (ValueError, OSError):
                immagine = None
            if immagine is None:
                self.send_error(404)
            else:
                self._invia(immagine.read_bytes(), post_modulo.ESTENSIONI[immagine.suffix.lower()])
        elif percorso.startswith("/api/post/scarica/") or percorso.startswith("/api/post/zip/"):
            self._post_scarica(percorso)
        elif percorso.startswith("/api/bozze/immagine/"):
            rete, _, nome = percorso.removeprefix("/api/bozze/immagine/").partition("/")
            immagine = immagine_bozza(nome, RETI[rete]) if rete in RETI else None
            if immagine is None:
                self.send_error(404)
            else:
                self._invia(immagine.read_bytes(), "image/png")
        else:
            self.send_error(404)

    def _json(self, oggetto, codice=200):
        self._invia(json.dumps(oggetto, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", codice)

    def _invia(self, corpo, tipo, codice=200, scarica=None):
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        if scarica:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % scarica)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, formato, *args):
        pass


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORTA
    HOST_OK.update({"127.0.0.1:%d" % porta, "localhost:%d" % porta})
    ThreadingHTTPServer(("127.0.0.1", porta), Gestore).serve_forever()


if __name__ == "__main__":
    main()
