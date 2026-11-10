#!/usr/bin/env python3
"""PreToolUse: decide nega o chiedi per Bash ed Edit|Write leggendo regole.json, l'elenco unico delle regole (ADR-012).

Non confronta il testo del comando: lo scompone come la shell (segmenti su ; && || | e a capo), toglie gli involucri
(VAR=x, env, sudo, xargs, rtk, /usr/bin/, \\git, sh -c, eval, $(…), backtick) e le opzioni globali di git, poi confronta l'argv.
Uscite: nega = exit 2 con il motivo su stderr; chiedi = JSON "ask" su stdout; niente = exit 0 muto (decidono i settings).
Non risponde mai "allow". Qualsiasi errore interno (JSON rotto, regole mancanti, apici non chiusi) diventa "chiedi".
Limiti noti: alias di git, script su file (bash x.sh, python -c), tool MCP.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

PROFONDITA_MAX = 5
SEPARATORI = set(";&|()\n")
REDIREZIONI = set("<>&")
PAROLE_SHELL = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "fi", "done"}
PREFISSI = {"command", "builtin", "exec", "nohup", "time", "rtk", "nice", "caffeinate", "npx", "bunx"}
SOTTO_RTK = {"bypass", "proxy", "err", "summary", "test"}  # rtk <sotto> <comando>: eseguono il comando
ESEGUI_PACCHETTO = {("pnpm", "dlx"), ("yarn", "dlx"), ("npm", "exec"), ("pnpm", "exec"), ("bun", "x")}
SHELL_CON_VALORE = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
SHELL = {"sh", "bash", "zsh", "dash", "ksh"}
ASSEGNAZIONE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
CON_VALORE = {  # opzioni che si mangiano l'argomento successivo
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"},
    "xargs": {"-n", "-I", "-i", "-d", "-L", "-l", "-P", "-s", "-E", "-e", "-a"},
    "nice": {"-n"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "npx": {"-p", "--package"},
    "bunx": {"-p", "--package"},
    "npm": {"-p", "--package", "-w", "--workspace"},
}
GIT_CON_VALORE = {"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace", "--config-env", "--super-prefix"}
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1([^\n]*)\n.*?^[ \t]*\2[ \t]*$", re.S | re.M)
CHIAVI = {"azione", "motivo", "comando", "percorsi", "solo_vault", "se_opzione", "se_argomento", "se_config", "tranne_opzione", "tranne_argomento"}
FORZA = {"": 0, "chiedi": 1, "nega": 2}


def carica_regole(percorso):
    dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
    regole = dati["regole"] if isinstance(dati, dict) else None
    if not isinstance(regole, list) or not regole:
        raise ValueError("regole.json: manca la lista 'regole'")
    for r in regole:
        if not isinstance(r, dict) or set(r) - CHIAVI or r.get("azione") not in ("nega", "chiedi") or not isinstance(r.get("motivo"), str):
            raise ValueError("regola non valida: %r" % (r,))
        if ("comando" in r) == ("percorsi" in r):
            raise ValueError("una regola ha 'comando' oppure 'percorsi': %r" % (r,))
        for chiave in ("se_argomento", "se_config", "tranne_argomento"):
            if chiave in r:
                re.compile(r[chiave])
    return regole


def _sostituzioni(testo):
    """Il testo con $(…) e backtick sostituiti da un segnaposto, e la lista dei loro contenuti (da rianalizzare)."""
    fuori, interni, i = [], [], 0
    while i < len(testo):
        if testo.startswith("$(", i):
            prof, j = 1, i + 2
            while j < len(testo) and prof:
                prof += {"(": 1, ")": -1}.get(testo[j], 0)
                j += 1
            if prof:
                raise ValueError("$( non chiusa")
            interni.append(testo[i + 2:j - 1])
            fuori.append("SOSTITUZIONE")
            i = j
        elif testo[i] == "`":
            j = testo.find("`", i + 1)
            if j < 0:
                raise ValueError("backtick non chiuso")
            interni.append(testo[i + 1:j])
            fuori.append("SOSTITUZIONE")
            i = j + 1
        else:
            fuori.append(testo[i])
            i += 1
    return "".join(fuori), interni


def segmenti_grezzi(comando):
    """[token…] per ogni comando semplice, redirezioni comprese, e i testi interni di $(…) e backtick."""
    comando = re.sub(r"\\\r?\n", " ", comando)  # \ a capo continua la riga, non la chiude
    testo, interni = _sostituzioni(HEREDOC.sub(lambda m: "<<" + m.group(1) + m.group(2) + m.group(1) + m.group(3), comando))
    lex = shlex.shlex(testo, posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True  # senza, shlex spezza su : @ , + (host:/y diventerebbe tre token)
    lex.commenters = ""  # bash apre un commento solo a inizio parola: con "#" shlex perderebbe "wip#3 && git push"
    corrente, risultato = [], []
    for t in lex:
        if t and set(t) <= SEPARATORI:
            risultato.append(corrente)
            corrente = []
        else:
            corrente.append(t)
    risultato.append(corrente)
    return [s for s in risultato if s], interni


def _senza_redirezioni(tokens):
    """(argv senza redirezioni, file su cui una redirezione scrive)."""
    argv, scritti, salta = [], [], None
    for t in tokens:
        if salta is not None:
            if ">" in salta and not t.isdigit():
                scritti.append(t)
            salta = None
        elif t and set(t) <= REDIREZIONI:
            salta = t if t != "&" else None  # dopo > o < viene il file
        else:
            argv.append(t)
    return argv, scritti


def _togli_opzioni(argv, nome):
    con_valore, i = CON_VALORE.get(nome, set()), 0
    while i < len(argv) and argv[i].startswith("-") and argv[i] != "-":
        if argv[i] == "--":
            return argv[i + 1:]
        i += 2 if argv[i] in con_valore else 1
    return argv[i:]


def _normalizza(argv, profondita):
    """[(argv, config_git)…]: un comando può contenerne altri (sh -c, eval)."""
    while argv:
        while argv and (ASSEGNAZIONE.match(argv[0]) or argv[0] in PAROLE_SHELL):
            argv = argv[1:]
        if not argv:
            return []
        parola = argv[0].lstrip("\\")
        if "/" in parola:
            parola = parola.rstrip("/").rsplit("/", 1)[-1]
        if parola.startswith("$"):
            return [(["$VAR"] + argv[1:], [])]
        resto = argv[1:]
        if parola == "rtk" and resto and resto[0] in SOTTO_RTK:
            argv = resto[1:]
        elif (parola, resto[0] if resto else "") in ESEGUI_PACCHETTO:
            argv = _togli_opzioni(resto[1:], "npx")
        elif parola in PREFISSI:
            argv = _togli_opzioni(resto, parola)
        elif parola in ("env", "sudo", "xargs", "nice"):
            argv = _togli_opzioni(resto, parola)
            if parola == "env":
                while argv and ASSEGNAZIONE.match(argv[0]):
                    argv = argv[1:]
        elif parola == "timeout":
            argv = _togli_opzioni(resto, parola)[1:]
        elif parola in SHELL:
            i = 0
            while i < len(resto) and resto[i][:1] in "-+":
                t = resto[i]
                if t in SHELL_CON_VALORE:
                    i += 2
                    continue
                if not t.startswith("--") and "c" in t[1:]:
                    dopo = resto[i + 1:]
                    if dopo[:1] == ["--"]:
                        dopo = dopo[1:]
                    return analizza(dopo[0], profondita + 1) if dopo else []
                i += 1
            return [([parola] + resto, [])]
        elif parola == "eval":
            return analizza(" ".join(resto), profondita + 1)
        elif parola == "git":
            return [_git(resto)]
        elif parola == "gh":
            return [(["gh"] + _senza_repo(resto), [])]
        else:
            return [([parola] + resto, [])]
    return []


def _git(resto):
    config, i = [], 0
    while i < len(resto) and resto[i].startswith("-"):
        t = resto[i]
        if t in GIT_CON_VALORE:
            if t == "-c" and i + 1 < len(resto):
                config.append(resto[i + 1])
            i += 2
        else:
            i += 1
    return ["git"] + resto[i:], config


def _senza_repo(resto):
    fuori, salta = [], False
    for t in resto:
        if salta:
            salta = False
        elif t in ("-R", "--repo"):
            salta = True
        elif not t.startswith("--repo="):
            fuori.append(t)
    return fuori


def analizza(comando, profondita=0):
    """[(argv normalizzato, config_git, file scritti da redirezioni)…] di ogni comando che la riga esegue."""
    if profondita > PROFONDITA_MAX:
        raise ValueError("comando annidato oltre %d livelli" % PROFONDITA_MAX)
    grezzi, interni = segmenti_grezzi(comando)
    risultato = []
    for tokens in grezzi:
        argv, scritti = _senza_redirezioni(tokens)
        normalizzati = _normalizza(argv, profondita)
        for voce in normalizzati:
            risultato.append(voce if len(voce) == 3 else (voce[0], voce[1], scritti))
        if scritti and not normalizzati:
            risultato.append(([], [], scritti))
    for testo in interni:
        risultato += analizza(testo, profondita + 1)
    return risultato


def segmenti(comando, profondita=0):
    return [voce[0] for voce in analizza(comando, profondita)]


def _posizionali(args):
    return [a for a in args if not a.startswith("-")]


def file_scritti(argv):
    """I file che un comando modifica, per i comandi che scrivono (cp, mv, sed -i…). Sovrastima: meglio un no in più."""
    if not argv:
        return []
    nome, args = argv[0], argv[1:]
    pos = _posizionali(args)
    if nome in ("cp", "install", "ln"):
        return pos[-1:]
    if nome in ("mv", "rm", "tee", "truncate", "chmod", "chown", "touch", "unlink", "rmdir", "shred"):
        return pos
    if nome in ("sed", "perl") and any(a.startswith("-i") or a == "--in-place" or (nome == "perl" and re.fullmatch(r"-[a-z]*i[a-z]*", a)) for a in args):
        return pos
    if nome == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    return []


def _risolvi(percorso, radice, home):
    percorso = re.sub(r"^(\$HOME|\$\{HOME\})(?=/|$)", "~", percorso)
    p = home / percorso[2:] if percorso == "~" or percorso.startswith("~/") else Path(percorso)
    return os.path.normcase(str((p if p.is_absolute() else radice / p).resolve())).casefold()


def valuta_percorso(percorso, regole, radice, home, cartella=None):
    """Nega se il percorso cade sotto una regola 'percorsi'. Il confronto ignora le maiuscole (APFS e NTFS non le distinguono).
    Un percorso relativo si risolve da `cartella` (la cartella corrente della shell), i modelli relativi dalla radice del progetto."""
    bersaglio = _risolvi(percorso, cartella or radice, home)
    vault = (radice / ".claude" / "hooks" / "regole.json").is_file()
    migliore = ("", "")
    for r in regole:
        if "percorsi" not in r or (r.get("solo_vault") and not vault):
            continue
        for modello in r["percorsi"]:
            cartella = modello.endswith("/**")
            base = _risolvi(modello[:-3] if cartella else modello, radice, home)
            if bersaglio == base or (cartella and bersaglio.startswith(base + os.sep)):
                if FORZA[r["azione"]] > FORZA[migliore[0]]:
                    migliore = (r["azione"], r["motivo"])
    return migliore


def _opzione(arg, opz):
    if arg == opz or arg.startswith(opz + "="):
        return True
    if opz.startswith("--"):
        nome = arg.split("=", 1)[0]
        return arg.startswith("--") and len(nome) >= 4 and opz.startswith(nome)  # git accetta ogni prefisso univoco: --ha è --hard
    return bool(re.fullmatch(r"-[A-Za-z]+", arg)) and opz[1:] in arg[1:]


def valuta_argv(argv, regole, config=()):
    migliore = ("", "")
    for r in regole:
        parole = r.get("comando")
        if not parole or argv[:len(parole)] != parole:
            continue
        args = argv[len(parole):]
        posizionali = [a for a in args if not a.startswith("-")]
        if any(_opzione(a, o) for a in args for o in r.get("tranne_opzione", [])):
            continue
        if "tranne_argomento" in r and any(re.search(r["tranne_argomento"], a) for a in posizionali):
            continue
        condizioni = [k for k in ("se_opzione", "se_argomento", "se_config") if k in r]
        vale = not condizioni or (
            any(_opzione(a, o) for a in args for o in r.get("se_opzione", []))
            or ("se_argomento" in r and any(re.search(r["se_argomento"], a) for a in posizionali))
            or ("se_config" in r and any(re.search(r["se_config"], c) for c in config)))
        if vale and FORZA[r["azione"]] > FORZA[migliore[0]]:
            migliore = (r["azione"], r["motivo"])
    return migliore


def _piu_forte(a, b):
    return b if FORZA[b[0]] > FORZA[a[0]] else a


def decidi(evento, regole, radice, home):
    strumento = evento.get("tool_name")
    dati = evento.get("tool_input") or {}
    esito = ("", "")
    if strumento == "Bash":
        for argv, config, scritti in analizza(dati.get("command") or ""):
            esito = _piu_forte(esito, valuta_argv(argv, regole, config))
            for f in scritti + file_scritti(argv):
                esito = _piu_forte(esito, valuta_percorso(f, regole, radice, home, Path(evento.get("cwd") or radice)))
    elif strumento in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        percorso = dati.get("file_path") or dati.get("notebook_path")
        if percorso:
            esito = valuta_percorso(percorso, regole, radice, home)
    return esito


def main():
    try:
        evento = json.loads(sys.stdin.buffer.read().decode("utf-8"))  # su Windows stdin sarebbe cp1252
        regole = carica_regole(Path(__file__).resolve().parent / "regole.json")
        radice = Path(os.environ.get("CLAUDE_PROJECT_DIR") or evento.get("cwd") or os.getcwd())
        azione, motivo = decidi(evento, regole, radice, Path.home())
    except Exception as e:  # fallisce chiuso: un hook che va in errore con exit 1 non bloccherebbe nulla
        azione, motivo = "chiedi", "regole.py: non riesco a valutare il comando (%s: %s)" % (type(e).__name__, e)
    if azione == "nega":
        sys.stderr.write(motivo + "\n")
        return 2
    if azione == "chiedi":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": motivo}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
