#!/usr/bin/env python3
"""First-run wizard for the second brain. Standard library only; works on macOS, Linux and Windows.

Usage:
    python3 setup.py                        (Windows: py -3 setup.py) asks a few questions, one module at a time
    python3 setup.py --add riservata        add a module later, without touching what you already have
    python3 setup.py --answers answers.json --yes     no questions: answers from a file (for repeat installs and tests)
    python3 setup.py --list                 the modules and what each one does
    python3 setup.py --clean-example        remove the example project once you have your own
    python3 setup.py --dry-run              show what it would do, change nothing

Modules live in modules/<id>/module.json. The wizard shows a summary of every change and waits for your yes before it writes anything.
It never overwrites a file that already exists.
"""
import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import moduli
import sistema

RADICE = Path(__file__).resolve().parent

MESSAGGI = {
    "en": {
        "language": "Language for the wizard and the agent's replies (en/it)", "yes_no": "[y/N]", "yes_no_default_yes": "[Y/n]",
        "would": "would do", "done_one": "done", "removed": "removed",
        "no_example": "the example project is not there (already removed)",
        "summary": "This is what will happen:", "confirm": "Go ahead?", "aborted": "Nothing was changed.",
        "done": "Done. Next: python3 doctor.py (Windows: py -3 doctor.py), then open GETTING_STARTED.md.",
        "bad_lang": "language must be en or it", "needs": "needs the module %s first (run: python3 setup.py --add %s)",
        "unknown_module": "unknown module: %s", "invalid": "not accepted: %s", "not_for_os": "not available on this system",
        "add_needs_core": "run python3 setup.py first (config.json is missing)", "modules": "Modules:", "always": "always",
        "pull": "To download the model (needs Ollama installed): ollama pull %s",
        "no_claude": "You chose something that uses Claude Code, but it is not installed. python3 doctor.py shows how to install it.",
        "next": "Next steps for what you chose:",
        "step_ollama": "Start Ollama before anything that uses a local model (the Ollama app, or: ollama serve). The page \"Modello locale\" stays empty until it runs.",
        "step_radar": "Radar: put your feeds in memory/feeds.md, then run once %s scripts/feed.py and %s scripts/radar.py (or the Radar button in the Avvii page). Until the first run the Radar page is empty; after that the jobs do it every Monday.",
        "step_claude": "Page \"Uso di Claude\": it fills only after you add the status line to ~/.claude/settings.json (README, \"When a page is empty\").",
        "obsidian": "Optional: open this folder as a vault in Obsidian to read your notes in a nice interface (https://obsidian.md/download). Nothing to configure: the folder is already a vault.",
    },
    "it": {
        "language": "Lingua del wizard e delle risposte dell'agente (en/it)", "yes_no": "[s/N]", "yes_no_default_yes": "[S/n]",
        "would": "farei", "done_one": "fatto", "removed": "rimosso",
        "no_example": "il progetto d'esempio non c'è (già rimosso)",
        "summary": "Ecco cosa succederà:", "confirm": "Procedo?", "aborted": "Non è cambiato niente.",
        "done": "Fatto. Ora: python3 doctor.py (Windows: py -3 doctor.py), poi apri INIZIA.md.",
        "bad_lang": "la lingua deve essere en o it", "needs": "serve prima il modulo %s (lancia: python3 setup.py --add %s)",
        "unknown_module": "modulo sconosciuto: %s", "invalid": "non accettato: %s", "not_for_os": "non disponibile su questo sistema",
        "add_needs_core": "lancia prima python3 setup.py (manca config.json)", "modules": "Moduli:", "always": "sempre",
        "pull": "Per scaricare il modello (serve Ollama installato): ollama pull %s",
        "no_claude": "Hai scelto qualcosa che usa Claude Code, ma non è installato. python3 doctor.py mostra come installarlo.",
        "next": "Prossimi passi per ciò che hai scelto:",
        "step_ollama": "Avvia Ollama prima di tutto ciò che usa un modello locale (l'app Ollama, oppure: ollama serve). La pagina «Modello locale» resta vuota finché non gira.",
        "step_radar": "Radar: metti i tuoi feed in memory/feeds.md, poi lancia una volta %s scripts/feed.py e %s scripts/radar.py (oppure il pulsante Radar nella pagina Avvii). Fino al primo giro la pagina Radar è vuota; poi ci pensano i job ogni lunedì.",
        "step_claude": "Pagina «Uso di Claude»: si riempie solo dopo che aggiungi la barra di stato a ~/.claude/settings.json (README, «Quando una pagina è vuota»).",
        "obsidian": "Facoltativo: apri questa cartella come vault in Obsidian per leggere le note con un'interfaccia comoda (https://obsidian.md/download). Non c'è niente da configurare: la cartella è già un vault.",
    },
}


def trova_obsidian():
    """Obsidian installato? Lo chiede a doctor.py; se non c'è (o non si carica) si propone e basta."""
    try:
        spec = importlib.util.spec_from_file_location("doctor", RADICE / "doctor.py")
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)
        return d.trova_obsidian()
    except (OSError, ImportError, AttributeError, KeyError):
        return False


def prossimi_passi(attivi, msg, piattaforma=None):
    """Righe «cosa fare adesso» per i moduli scelti: certe pagine della dashboard restano vuote finché non si fa questo."""
    py = "py -3" if (piattaforma or sys.platform) == "win32" else "python3"
    ollama = any(isinstance(v, str) and v.startswith("ollama:") for r in attivi.values() for v in r.values())
    righe = [msg["step_ollama"]] if ollama else []
    if "radar" in attivi:
        righe.append(msg["step_radar"] % (py, py))
    righe.append(msg["step_claude"])
    return righe


GUIDA = {
    "en": {
        "scan": "Your computer: %s",
        "none": "nothing to install, nothing leaves your computer", "claude": "most precise; the text of this step leaves for Anthropic and uses your plan quota",
        "ollama": "stays on this computer; about %.1f GB to download", "no_local": "(no local model fits this RAM or disk: Claude or none)",
        "titolo": "Let's get this computer ready. I ask before each step and show the command; you can say no to any of them.",
        "claude_manca": "Claude Code is not installed. Run this in your terminal, then come back: %s",
        "installa": "Install %s? It runs: %s", "gestore": "%s needs %s, which is not installed: get it from %s",
        "a_mano": "Install %s yourself: %s", "ok": "done", "fallito": "it failed (code %s). Do it by hand: %s",
        "ollama_spento": "Ollama is installed but not running. Start it (the Ollama app, or: ollama serve), then run: %s",
        "scarica": "Download %s (about %.1f GB)?", "poco_disco": "Not enough free disk for %s (about %.1f GB): skipped. Free some space and run: ollama pull %s",
        "hook": "Turn on the secret scan before each commit? It runs: git config core.hooksPath scripts/hooks",
        "regole": "Turn on the rules for Claude Code in every repo? push, PR, deploy and rm ask first; force-push, reset --hard and clean are refused (ADR-012). It runs: %s --si\n    (it copies two files to ~/.claude/hooks and adds a hook to %s, keeping a copy of the file)",
        "statusline": "Show your Claude usage in the dashboard? It adds this status line to %s (a copy of the file is kept first):\n    %s",
        "statusline_ok": "Status line added.", "statusline_c_e": "You already have a status line there: I left it as it is (README, \"When a page is empty\").",
        "statusline_no": "I could not read %s as JSON: I left it alone. Add the status line by hand (README, \"When a page is empty\").",
        "jobs": "Register the scheduled jobs now (radar, chiusura, dashboard...)? You can remove them with: install_jobs.py --uninstall",
        "radar": "Collect the news and run the radar once now, so the Radar page has something to show?", "radar_vuoti": "Add feed addresses to memory/feeds.md first: skipped.",
    },
    "it": {
        "scan": "Il tuo computer: %s",
        "none": "niente da installare, niente esce dal computer", "claude": "più preciso; il testo di questo passo esce verso Anthropic e consuma la quota del tuo piano",
        "ollama": "resta su questo computer; circa %.1f GB da scaricare", "no_local": "(nessun modello locale va bene per questa RAM o questo disco: Claude o nessuno)",
        "titolo": "Prepariamo questo computer. Chiedo prima di ogni passo e mostro il comando; puoi dire no a qualunque.",
        "claude_manca": "Claude Code non è installato. Lancia questo nel tuo terminale, poi torna: %s",
        "installa": "Installo %s? Lancia: %s", "gestore": "%s richiede %s, che non è installato: scaricalo da %s",
        "a_mano": "Installa %s a mano: %s", "ok": "fatto", "fallito": "non è riuscito (codice %s). Fallo a mano: %s",
        "ollama_spento": "Ollama è installato ma non è acceso. Avvialo (l'app Ollama, oppure: ollama serve), poi lancia: %s",
        "scarica": "Scarico %s (circa %.1f GB)?", "poco_disco": "Poco spazio libero sul disco per %s (circa %.1f GB): saltato. Libera spazio e lancia: ollama pull %s",
        "hook": "Attivo il controllo dei segreti prima di ogni commit? Lancia: git config core.hooksPath scripts/hooks",
        "regole": "Attivo le regole di Claude Code in ogni repo? push, PR, deploy e rm chiedono conferma; force-push, reset --hard e clean sono rifiutati (ADR-012). Lancia: %s --si\n    (copia due file in ~/.claude/hooks e aggiunge un hook a %s, tenendo una copia del file)",
        "statusline": "Mostro l'uso di Claude nella dashboard? Aggiunge questa barra di stato a %s (prima ne tengo una copia):\n    %s",
        "statusline_ok": "Barra di stato aggiunta.", "statusline_c_e": "Lì c'è già una barra di stato: l'ho lasciata com'è (README, «Quando una pagina è vuota»).",
        "statusline_no": "Non riesco a leggere %s come JSON: l'ho lasciato stare. Aggiungi la barra di stato a mano (README, «Quando una pagina è vuota»).",
        "jobs": "Registro ora i job pianificati (radar, chiusura, dashboard...)? Si tolgono con: install_jobs.py --uninstall",
        "radar": "Raccolgo le novità e lancio il radar una volta adesso, così la pagina Radar ha qualcosa da mostrare?", "radar_vuoti": "Prima metti gli indirizzi dei feed in memory/feeds.md: saltato.",
    },
}
_SCAN = []


def scansione():
    """La scansione del computer, fatta una volta sola per sessione."""
    if not _SCAN:
        _SCAN.append(sistema.scansiona(RADICE))
    return _SCAN[0]


def opzioni_modello(d, lingua):
    """[(valore, nota)] per la domanda di un modello: none, claude e il modello locale adatto a questo computer.
    Una voce con valore None è solo una nota (nessun modello locale adatto)."""
    g, rec = GUIDA[lingua], sistema.consigli(scansione())
    solo = d.get("solo", ["none", "claude", "ollama"])
    out = [("none", g["none"])]
    if "claude" in solo:
        out.append(("claude", g["claude"]))
    nome = rec["embedding"] if d.get("solo") else rec["chat"]
    if "ollama" in solo:
        out.append(("ollama:" + nome, g["ollama"] % sistema.DIMENSIONI[nome]) if nome else (None, g["no_local"]))
    return out


def passi_guidati(attivi, lingua, radice, si, esegui=sistema.esegui, scan=None, home=None, doctor=None):
    """Il percorso guidato dopo la scrittura dei file: programmi che mancano, modelli da scaricare, controllo dei segreti, barra di stato,
    job e primo giro del radar. Ogni passo si chiede prima e mostra il comando. `si(testo, predefinito)` risponde; `esegui(lista)` lancia."""
    g, radice = GUIDA[lingua], Path(radice)
    d = doctor or sistema._carica("doctor")
    cfg = moduli._leggi_json(radice / "config.json")
    print("\n" + g["titolo"])
    print(g["scan"] % sistema.descrivi(scan or scansione(), lingua))

    def programma(nome):
        if sistema.installato(nome, d):
            return True
        comando, manca = sistema.piano_installazione(nome)
        if comando:
            if not si(g["installa"] % (nome, " ".join(comando)), False):
                return False
            codice = esegui(comando)
            print("  " + (g["ok"] if codice == 0 else g["fallito"] % (codice, " ".join(comando))))
            return codice == 0 and sistema.installato(nome, d)
        print("  " + (g["gestore"] % (nome, manca, sistema.PAGINE[nome]) if manca else g["a_mano"] % (nome, d.INSTALLA.get(nome, {}).get(sistema.SISTEMA, sistema.PAGINE[nome]))))
        return False

    if not sistema.installato("claude", d):
        print("  " + g["claude_manca"] % d.INSTALLA["claude"][sistema.SISTEMA])
    modelli = sorted({str(v)[7:] for v in cfg.get("modelli", {}).values() if str(v).startswith("ollama:")})
    if modelli and programma("ollama"):
        scaricati = d.modelli_scaricati()
        mancanti = [m for m in modelli if scaricati is None or (m not in scaricati and m + ":latest" not in scaricati)]
        if scaricati is None and mancanti:
            print("  " + g["ollama_spento"] % "; ".join("ollama pull " + m for m in mancanti))
        for m in ([] if scaricati is None else mancanti):
            gb = sistema.DIMENSIONI.get(m, 5.0)
            libero = (scan or scansione()).get("disco_libero_gb")
            if libero is not None and libero < gb + 5:
                print("  " + g["poco_disco"] % (m, gb, m))
            elif si(g["scarica"] % (m, gb), False):
                codice = esegui(["ollama", "pull", m])
                print("  " + (g["ok"] if codice == 0 else g["fallito"] % (codice, "ollama pull " + m)))
    programma("obsidian")
    if (radice / ".git").exists() and (radice / "scripts" / "hooks" / "pre-commit").exists():
        if (sistema.installato("gitleaks", d) or programma("gitleaks")) and si(g["hook"], False):
            codice = esegui(["git", "-C", str(radice), "config", "core.hooksPath", "scripts/hooks"])
            print("  " + (g["ok"] if codice == 0 else g["fallito"] % (codice, "git config core.hooksPath scripts/hooks")))
    impostazioni = Path(home or Path.home()) / ".claude" / "settings.json"
    comando = sistema.comando_statusline(radice)
    if si(g["statusline"] % (impostazioni, comando), False):
        esito = sistema.aggiungi_statusline(impostazioni, comando)
        print("  " + {"aggiunta": g["statusline_ok"], "gia-presente": g["statusline_c_e"], "illeggibile": g["statusline_no"] % impostazioni}[esito])
    regole = radice / "scripts" / "installa-regole.py"
    if regole.exists() and si(g["regole"] % (regole, impostazioni), False):
        codice = esegui([sys.executable, "-I", str(regole), "--si"])
        print("  " + (g["ok"] if codice == 0 else g["fallito"] % (codice, "%s -I %s" % (sys.executable, regole))))
    if (radice / "install_jobs.py").exists() and si(g["jobs"], False):
        esegui([sys.executable, str(radice / "install_jobs.py")])
    if "radar" in attivi and (radice / "scripts" / "feed.py").exists() and si(g["radar"], False):
        feeds = radice / "memory" / "feeds.md"
        if not feeds.exists() or "http" not in feeds.read_text(encoding="utf-8"):
            print("  " + g["radar_vuoti"])
        else:
            for script in ("feed.py", "radar.py"):
                esegui([sys.executable, "-I", str(radice / "scripts" / script)])


def modello_mod():
    """scripts/modello.py: nel template sta in scripts/, quando si prova dentro il vault dell'autore un livello sopra."""
    for cartella in (RADICE, RADICE.parent):
        file = cartella / "scripts" / "modello.py"
        if file.exists():
            spec = importlib.util.spec_from_file_location("modello", file)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ValueError("scripts/modello.py not found")


def domanda(testo, predefinito=""):
    risposta = input("%s%s: " % (testo, " [%s]" % predefinito if predefinito else "")).strip()
    return risposta or predefinito


def si_no(testo, msg, predefinito=False):
    r = input("%s %s: " % (testo, msg["yes_no_default_yes" if predefinito else "yes_no"])).strip().lower()
    return predefinito if not r else r[0] in ("y", "s")


def una_riga(testo):
    """Una riga sola e senza spazi in fondo: certi valori finiscono in un file di istruzioni."""
    return re.sub(r"[\r\n]+", " ", str(testo)).strip()


def chiedi(m, lingua, msg, gia, interattivo=True):
    """Le risposte alle domande di un modulo: da `gia` (file di risposte), chiedendole, o col valore di fabbrica se non c'è nessuno
    a rispondere. Una risposta non valida si richiede (se viene da un file, è un errore)."""
    risposte = {}
    for d in m.get("domande", []):
        while True:
            if d["id"] in gia:
                valore = gia[d["id"]]
            elif not interattivo:
                valore = predefinito(d)
            elif d.get("validazione") == "modello" and interattivo and not d.get("_mostrata"):
                d["_mostrata"] = True
                if d.get("avviso"):
                    print("  " + moduli.testo(d["avviso"], lingua))
                opzioni = opzioni_modello(d, lingua)
                print("  " + GUIDA[lingua]["scan"] % sistema.descrivi(scansione(), lingua))
                for v, nota in opzioni:
                    print("    %s" % nota if v is None else "    %d) %-28s %s" % ([o[0] for o in opzioni if o[0]].index(v) + 1, v, nota))
                opzioni = [o for o in opzioni if o[0]]
                valore = domanda(moduli.testo(d["testo"], lingua), str(d.get("predefinito", "none")))
                if valore.isdigit() and 1 <= int(valore) <= len(opzioni):
                    valore = opzioni[int(valore) - 1][0]
            elif d["tipo"] == "si_no":
                valore = si_no(moduli.testo(d["testo"], lingua), msg, bool(d.get("predefinito")))
            else:
                scelte = " (%s)" % " / ".join(d["opzioni"]) if d.get("opzioni") else ""
                if d.get("avviso") and not d.get("_mostrata"):
                    d["_mostrata"] = True
                    print("  " + moduli.testo(d["avviso"], lingua))
                valore = domanda(moduli.testo(d["testo"], lingua) + scelte, str(predefinito(d)))
            try:
                risposte[d["id"]] = verifica(d, valore)
                break
            except ValueError as e:
                print("  " + msg["invalid"] % e)
                if d["id"] in gia:
                    raise
    return risposte


URL_HTTP = re.compile(r"https?://[^\s,]+")


def predefinito(d):
    """Il valore di fabbrica; `predefinito_os` ({sys.platform: valore}) lo cambia secondo il sistema."""
    return d.get("predefinito_os", {}).get(sys.platform, d.get("predefinito", ""))


def verifica(d, valore):
    if d.get("validazione") == "cartella":
        return moduli.valida_cartella(str(valore))
    if d.get("validazione") == "modello":
        # «claude», «none» o «ollama:<nome>»; `solo` restringe (l'embedding non può essere Claude)
        valore = una_riga(valore) or "none"
        provider, _, nome = valore.partition(":")
        if provider not in d.get("solo", ["none", "claude", "ollama"]) or (provider == "ollama" and not nome) or (provider != "ollama" and nome):
            raise ValueError("%s: use %s" % (valore, ", ".join(p if p != "ollama" else "ollama:<model>" for p in d.get("solo", ["none", "claude", "ollama"]))))
        if provider == "ollama":
            modello_mod().valida_nome(nome)
        return valore
    if d.get("validazione") == "url":
        voci = valore if isinstance(valore, list) else [v for v in re.split(r"[\s,]+", str(valore)) if v]
        if not all(isinstance(v, str) and URL_HTTP.fullmatch(v) for v in voci):
            raise ValueError("only http and https addresses")
        return list(voci)
    if d.get("lista"):
        voci = valore if isinstance(valore, list) else re.split(r"[,\n]", str(valore))
        return [una_riga(v) for v in voci if una_riga(v)]
    if d["tipo"] == "scelta" and valore not in d.get("opzioni", [valore]):
        raise ValueError("%s: choose one of %s" % (valore, ", ".join(d["opzioni"])))
    if valore in d.get("solo_os", {}) and sys.platform not in d["solo_os"][valore]:  # es. il Calendario di macOS solo su macOS
        raise ValueError("%s: %s" % (valore, MESSAGGI["en"]["not_for_os"]))
    return una_riga(valore) if isinstance(valore, str) else valore


def raccogli(tutti, lingua, msg, risposte_file, solo=None, interattivo=True):
    """{id modulo: risposte} dei moduli attivi, in ordine di dipendenza. `solo`: un solo modulo (--add)."""
    attivi = {}
    for i, m in tutti.items():
        if solo and i != solo and i != "core":
            continue
        gia = (risposte_file.get("moduli", {}).get(i, {}) if i != "core" else risposte_file)
        if i == "core":
            if solo:
                continue
            attivi[i] = chiedi(m, lingua, msg, {k: v for k, v in gia.items() if k in ("nome", "ruolo")}, interattivo)
            continue
        if not m.get("sempre"):
            if solo == i:
                attivo = True
            elif "attivo" in gia:
                attivo = bool(gia["attivo"])
            elif interattivo:
                print("\n%s: %s" % (moduli.testo(m["titolo"], lingua), moduli.testo(m["descrizione"], lingua)))
                attivo = si_no(moduli.testo(m["domanda_attivazione"], lingua), msg)
            else:
                attivo = False
            if not attivo:
                continue
        for d in m.get("richiede", []):
            if d not in attivi and d != "core" and not solo:
                raise ValueError(msg["needs"] % (d, d))
        attivi[i] = chiedi(m, lingua, msg, gia, interattivo)
    return attivi


def installa(nome, ruolo, lingua, msg, dry=False, radice=RADICE):
    """Il modulo core con nome e ruolo dati: config.json, memory/*.md e CLAUDE.md. Non sovrascrive niente."""
    tutti = moduli.carica(radice)
    for a in moduli.azioni_di(tutti["core"], {"nome": nome, "ruolo": ruolo}, lingua):
        print("  %s: %s" % (msg["would" if dry else "done_one"], moduli.descrivi(a, lingua)))
        moduli.applica(a, radice, dry=dry)


def pulisci_esempio(msg, dry=False, radice=RADICE):
    """Toglie projects/example-project e la sua riga in projects/INDEX.md. Solo quel percorso, mai altro."""
    cartella = radice / "projects" / "example-project"
    if not cartella.is_dir():
        print("  " + msg["no_example"])
        return
    print("  projects/example-project: %s" % msg["would" if dry else "removed"])
    if dry:
        return
    shutil.rmtree(cartella)
    indice = radice / "projects" / "INDEX.md"
    righe = [r for r in indice.read_text(encoding="utf-8").splitlines() if "[[projects/example-project/STATE" not in r]
    moduli.scrivi(indice, "\n".join(righe) + "\n")
    servizi = radice / "docs" / "servizi.md"
    if servizi.exists():  # anche la sezione d'esempio della tabella dei servizi
        testo = re.sub(r"^## example-project\n.*?(?=^## |\Z)", "", servizi.read_text(encoding="utf-8"), flags=re.S | re.M)
        moduli.scrivi(servizi, testo.rstrip() + "\n")


def main(argv=None, radice=RADICE):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name")
    ap.add_argument("--role")
    ap.add_argument("--language")
    ap.add_argument("--yes", action="store_true", help="do not ask: use the answers file, the options and the defaults")
    ap.add_argument("--answers", help="JSON file with the answers")
    ap.add_argument("--add", metavar="MODULE")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--clean-example", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    file_risposte = json.loads(Path(a.answers).read_text(encoding="utf-8-sig")) if a.answers else {}
    lingua = (a.language or file_risposte.get("lingua") or "en").lower()
    if lingua not in MESSAGGI:
        sys.exit(MESSAGGI["en"]["bad_lang"])
    msg = MESSAGGI[lingua]
    if a.clean_example:
        pulisci_esempio(msg, a.dry_run, radice)
        return 0
    tutti = moduli.carica(radice)
    if a.list:
        print(msg["modules"])
        for i, m in tutti.items():
            print("  %-10s %s%s" % (i, moduli.testo(m["titolo"], lingua), " (%s)" % msg["always"] if m.get("sempre") else ""))
            print("             " + moduli.testo(m["descrizione"], lingua))
        return 0
    interattivo = not (a.yes or a.answers)
    if a.add and a.add not in tutti:
        sys.exit(msg["unknown_module"] % a.add)
    if a.add and not (radice / "config.json").exists():
        sys.exit(msg["add_needs_core"])
    if interattivo and not a.language:
        lingua = domanda(msg["language"], lingua).lower()
        if lingua not in MESSAGGI:
            sys.exit(MESSAGGI["en"]["bad_lang"])
        msg = MESSAGGI[lingua]
    gia = {**file_risposte, **({"nome": a.name} if a.name is not None else {}), **({"ruolo": a.role} if a.role is not None else {})}
    try:
        attivi = raccogli(tutti, lingua, msg, gia, solo=a.add, interattivo=interattivo)
    except ValueError as e:
        sys.exit(str(e))
    azioni = []
    for i, risposte in attivi.items():
        nome_core = attivi.get("core", {}).get("nome")
        if i == "core" and not nome_core:
            risposte["nome"] = risposte.get("nome") or "<your name>"
        azioni += [(i, x) for x in moduli.azioni_di(tutti[i], risposte, lingua)]
    print("\n" + msg["summary"])
    for i, x in azioni:
        print("  [%s] %s" % (i, moduli.descrivi(x, lingua)))
    if a.dry_run:
        return 0
    if interattivo and not si_no(msg["confirm"], msg, True):
        print(msg["aborted"])
        return 1
    try:
        for i, x in azioni:
            moduli.applica(x, radice)
    except ValueError as e:
        sys.exit(str(e))
    if interattivo and not a.dry_run:  # mai con --yes o --answers: i test e le installazioni ripetute non devono installare niente
        passi_guidati(attivi, lingua, radice, lambda testo, predef=False: si_no(testo, msg, predef))
    else:
        for risposte in attivi.values():
            for v in risposte.values():
                if isinstance(v, str) and v.startswith("ollama:"):
                    print(msg["pull"] % v[len("ollama:"):])
    print("\n" + msg["next"])
    for riga in prossimi_passi(attivi, msg):
        print("  - " + riga)
    usa_claude = "bozze" in attivi or any(v == "claude" for r in attivi.values() for v in r.values())
    if usa_claude and shutil.which("claude") is None:
        print(msg["no_claude"])
    if not trova_obsidian():
        print(msg["obsidian"])
    print(msg["done"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
