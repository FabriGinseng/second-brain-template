#!/usr/bin/env python3
"""Livello unico per i modelli: ogni passo che ha bisogno di un modello lo chiama da qui. Solo libreria standard.

La scelta sta in config.json, per passo: {"modelli": {"radar_giudizio": "ollama:qwen3:8b", "bozze": "claude", "assistente": "none"}}.
Un passo senza scelta usa "none": nessun modello, nessun invio verso il cloud, nessun download.

    chiedi("radar_giudizio", istruzioni, testo, json_=True)  -> Risposta(testo, statistiche)
    python3 scripts/modello.py --ram                          RAM del computer e modello locale consigliato
    python3 scripts/modello.py --check-model radar_giudizio   prova di compatibilità del modello scelto per quel passo

Regole: la cartella riservata non passa mai da qui (nessun passo la legge); date e orari li calcola il codice, non il modello.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import namedtuple
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
OLLAMA = "http://127.0.0.1:11434"
NOME_MODELLO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")
Risposta = namedtuple("Risposta", "testo statistiche")


class ModelloNonDisponibile(RuntimeError):
    """Il provider non c'è, non risponde o il passo non ha un modello: il passo si salta con questo messaggio."""


class RispostaNonUtilizzabile(RuntimeError):
    """Il modello ha risposto, ma non con il JSON richiesto (anche al secondo tentativo)."""


def valida_nome(nome):
    """Nome di un modello Ollama: lettere, numeri e . : / - _. Finisce come argomento di un comando, mai in una shell."""
    if not NOME_MODELLO.fullmatch(nome or "") or ".." in nome:
        raise ValueError("nome di modello non valido: %r" % nome)
    return nome


def scelta(passo, vault=VAULT):
    """(provider, modello) del passo, da config.json. 'ollama:qwen3:8b' -> ('ollama', 'qwen3:8b'); 'claude' -> ('claude', '')."""
    try:
        cfg = json.loads((Path(vault) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    provider, _, nome = str(cfg.get("modelli", {}).get(passo, "none")).partition(":")
    if provider not in ("claude", "ollama", "none"):
        raise ModelloNonDisponibile("provider sconosciuto per «%s»: %s (usa claude, ollama:<modello> o none)" % (passo, provider))
    if provider == "ollama":
        valida_nome(nome)
    return provider, nome


def _ollama(nome, istruzioni, testo, json_, timeout, url=OLLAMA):
    corpo = {"model": nome, "stream": False, "keep_alive": "10m", "options": {"temperature": 0},
             "messages": [{"role": "system", "content": istruzioni}, {"role": "user", "content": testo}]}
    if json_:
        corpo["format"] = "json"
    if _dichiara(nome, "thinking", url):
        corpo["think"] = False  # i modelli che non lo dichiarano rifiutano il parametro
    richiesta = urllib.request.Request(url + "/api/chat", json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as r:
            dati = json.load(r)
        return Risposta(dati["message"]["content"].strip(), {k: dati.get(k) for k in ("total_duration", "prompt_eval_count", "eval_count", "eval_duration")})
    except (OSError, ValueError, KeyError) as e:
        raise ModelloNonDisponibile("il modello locale %s non risponde: %s" % (nome, e))


def _dichiara(nome, capacita, url=OLLAMA):
    """True se Ollama dichiara la capacità (es. 'thinking') per il modello. Se non si riesce a sapere: False."""
    try:
        richiesta = urllib.request.Request(url + "/api/show", json.dumps({"model": nome}).encode("utf-8"), {"Content-Type": "application/json"})
        with urllib.request.urlopen(richiesta, timeout=10) as r:
            return capacita in json.load(r).get("capabilities", [])
    except (OSError, ValueError):
        return False


def _claude(nome, istruzioni, testo, json_, timeout):
    """`claude -p` senza strumenti e senza salvare la sessione; il testo va da stdin, il comando è una lista (nessuna shell)."""
    comando = ["claude", "-p", "--tools", "", "--no-session-persistence", "--system-prompt", istruzioni]
    if nome:
        comando += ["--model", nome]
    try:
        r = subprocess.run(comando, input=testo, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                           env={**os.environ, "SB_NO_STOP_VERIFY": "1"})  # lo Stop hook non deve rimandare indietro una run senza strumenti
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ModelloNonDisponibile("claude non risponde: %s" % e)
    if r.returncode != 0:
        raise ModelloNonDisponibile("claude ha restituito un errore: %s" % (r.stderr.strip()[:200] or r.returncode))
    return Risposta(r.stdout.strip(), {})


PROVIDER = {"ollama": _ollama, "claude": _claude}


def _json_valido(testo):
    try:
        json.loads(testo)
        return True
    except ValueError:
        return False


def chiedi(passo, istruzioni, testo, json_=False, timeout=300, vault=VAULT, provider=None):
    """Chiede al modello scelto per `passo`. `provider` (dict nome -> funzione) serve ai test. Con json_ la risposta si valida e,
    se non è JSON, si riprova una volta; poi RispostaNonUtilizzabile."""
    nome_provider, nome = scelta(passo, vault)
    if nome_provider == "none":
        raise ModelloNonDisponibile("nessun modello scelto per «%s» (config.json → modelli.%s)" % (passo, passo))
    funzione = (provider or PROVIDER)[nome_provider]
    istr = istruzioni + ("\nRispondi solo con JSON valido, senza altro testo." if json_ and nome_provider == "claude" else "")
    for _ in range(2 if json_ else 1):
        risposta = funzione(nome, istr, testo, json_, timeout)
        if not json_ or _json_valido(risposta.testo):
            return risposta
    raise RispostaNonUtilizzabile("«%s»: il modello non ha risposto con JSON valido" % passo)


def incorpora(passo, testi, timeout=120, vault=VAULT, url=OLLAMA):
    """Vettori di embedding (uno per testo) dal modello `ollama:<nome>` scelto per `passo`. Claude non fa embedding."""
    provider, nome = scelta(passo, vault)
    if provider != "ollama":
        raise ModelloNonDisponibile("«%s» richiede un modello di embedding su Ollama (config.json → modelli.%s = ollama:<modello>)" % (passo, passo))
    richiesta = urllib.request.Request(url + "/api/embed", json.dumps({"model": nome, "input": testi}).encode("utf-8"), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as r:
            dati = json.load(r)
        vettori = dati["embeddings"]
    except (OSError, ValueError, KeyError) as e:
        raise ModelloNonDisponibile("il modello di embedding %s non risponde: %s" % (nome, e))
    if len(vettori) != len(testi) or not all(isinstance(v, list) and v and isinstance(v[0], (int, float)) for v in vettori):
        raise ModelloNonDisponibile("%s non restituisce vettori: non è un modello di embedding" % nome)
    return Risposta(vettori, {k: dati.get(k) for k in ("total_duration", "prompt_eval_count")})


# ---- RAM e modello locale consigliato ----

def ram_gb():
    """RAM del computer in GB con la sola libreria standard, o None se non si riesce a leggerla."""
    try:
        if sys.platform == "darwin":
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, encoding="utf-8")) / 2**30
        if sys.platform.startswith("linux"):
            for riga in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if riga.startswith("MemTotal:"):
                    return int(riga.split()[1]) / 2**20
        if sys.platform == "win32":
            import ctypes

            class Stato(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("carico", ctypes.c_ulong), ("totale", ctypes.c_ulonglong), ("libera", ctypes.c_ulonglong),
                            ("pf_t", ctypes.c_ulonglong), ("pf_l", ctypes.c_ulonglong), ("v_t", ctypes.c_ulonglong), ("v_l", ctypes.c_ulonglong),
                            ("ext", ctypes.c_ulonglong)]

            s = Stato()
            s.len = ctypes.sizeof(Stato)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
                return s.totale / 2**30
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        pass
    return None


def consiglia(ram):
    """{'locale': modello o None, 'testo': frase}: soglie e stime, non misure sui computer degli altri. L'alternativa con Claude c'è sempre."""
    if ram is None:
        return {"locale": None, "testo": "RAM non rilevata: scegli tu. Un modello locale piccolo va quasi ovunque; Claude è l'alternativa."}
    if ram >= 15:
        return {"locale": "qwen3:8b", "testo": "%.0f GB: va bene qwen3:8b (circa 5 GB, Apache 2.0). In alternativa Claude." % ram}
    if ram >= 7:
        return {"locale": "qwen3:4b-instruct-2507", "testo": "%.0f GB: meglio un modello piccolo come qwen3:4b-instruct-2507 (circa 2,5 GB, Apache 2.0), oppure Claude." % ram}
    return {"locale": None, "testo": "%.0f GB: troppo poca per un modello locale comodo. Consigliati Claude o nessun modello." % ram}


# ---- prova di compatibilità: tre richieste fisse, senza dati dell'utente ----

PROVE = [
    ("json", 'Rispondi solo con JSON {"colore": "..."} dove il valore è il colore del cielo sereno.', "Qual è?", True),
    ("data", 'Rispondi solo con JSON {"giorno": "..."} con il nome in italiano del giorno della settimana che segue martedì.', "Dimmelo.", True),
    ("riassunto", "Riassumi il testo in una frase.", "Il radar legge ogni lunedì le novità dei feed, le confronta con i progetti attivi e scrive una scheda solo per quelle utili.", False),
]


def prova(passo, vault=VAULT, provider=None):
    """Esito della prova per il modello scelto per `passo`: {'esito': adatto|adatto con riserva|non adatto, 'dettagli': [...]}."""
    if passo.endswith("embedding"):
        try:
            v = incorpora(passo, ["una frase di prova"], vault=vault).testo
            return {"esito": "adatto", "dettagli": ["embedding: ok (vettore di %d numeri)" % len(v[0])]}
        except ModelloNonDisponibile as e:
            return {"esito": "non adatto", "dettagli": ["embedding: no (%s)" % e]}
    dettagli, riusciti = [], 0
    for nome, istruzioni, testo, json_ in PROVE:
        t0 = time.time()
        try:
            r = chiedi(passo, istruzioni, testo, json_=json_, timeout=180, vault=vault, provider=provider)
        except (ModelloNonDisponibile, RispostaNonUtilizzabile) as e:
            dettagli.append("%s: no (%s)" % (nome, e))
            continue
        secondi = time.time() - t0
        ok = bool(r.testo) and (nome != "data" or "mercoled" in r.testo.lower().replace("ì", "i"))
        riusciti += ok
        dettagli.append("%s: %s (%.1f s)" % (nome, "ok" if ok else "risposta sbagliata", secondi))
    esito = "adatto" if riusciti == len(PROVE) else "adatto con riserva" if riusciti >= 2 else "non adatto"
    return {"esito": esito, "dettagli": dettagli}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ram", action="store_true")
    ap.add_argument("--check-model", metavar="PASSO")
    a = ap.parse_args(argv)
    if a.ram:
        print(consiglia(ram_gb())["testo"])
    if a.check_model:
        try:
            esito = prova(a.check_model)
        except (ModelloNonDisponibile, ValueError) as e:
            sys.exit(str(e))
        print("\n".join(esito["dettagli"] + ["esito: " + esito["esito"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
