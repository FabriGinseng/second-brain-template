#!/usr/bin/env python3
"""PreToolUse su Bash: nega i modi di saltare il pre-commit del vault.

Le regole `deny` di settings.json confrontano il testo del comando e non vedono le varianti che git accetta:
`--no-verif` (git accetta i prefissi univoci), `-an` o `-qn` (flag corti uniti), `-m x -n` (flag dopo il messaggio),
`-c core.hooksPath=...`. Qui il comando si spezza con shlex e si guardano i token di ogni `git commit`.
Se il comando non si riesce ad analizzare (apici non chiusi) l'hook lascia passare: restano i deny per sottostringa.
Exit 2 = blocco, il messaggio su stderr arriva a Claude.
"""
import json
import re
import shlex
import sys

LUNGO = "--no-verify"
CORTI = re.compile(r"^-[A-Za-z]+$")
MESSAGGIO = "salta il pre-commit del vault (gitleaks, verify, test): non lo faccio. Se serve davvero, lo fa l'utente a mano."


def segmenti(comando):
    corrente = []
    for t in shlex.shlex(comando, posix=True, punctuation_chars=True):  # ; && || | diventano token a sé
        if t and set(t) <= set(";&|()<>"):
            yield corrente
            corrente = []
        else:
            corrente.append(t)
    yield corrente


def aggira(seg):
    if "git" not in seg:
        return False
    dopo = seg[seg.index("git") + 1:]
    if any("hookspath" in t.lower() for t in dopo) and "scripts/hooks" not in dopo:
        return True
    if "commit" not in dopo:
        return False
    for t in dopo[dopo.index("commit") + 1:]:
        if t == "-n" or (t.startswith("--no-v") and LUNGO.startswith(t)) or (CORTI.match(t) and "n" in t[1:]):
            return True
    return False


try:
    comando = (json.load(sys.stdin).get("tool_input") or {}).get("command") or ""
    bloccato = any(aggira(s) for s in segmenti(comando))
except ValueError:  # JSON non valido o apici non chiusi (shlex): lascia passare
    sys.exit(0)
if bloccato:
    sys.stderr.write(MESSAGGIO + "\n")
    sys.exit(2)
