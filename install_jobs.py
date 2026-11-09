#!/usr/bin/env python3
"""Registers the scheduled jobs of scripts/jobs.json with the native scheduler of this computer.
Standard library only. macOS: launchd. Linux: systemd user timers. Windows: Task Scheduler.

Usage:
    python3 install_jobs.py --dry-run          show the files and the commands, change nothing
    python3 install_jobs.py                    write the files and run the commands, one by one
    python3 install_jobs.py --only radar,morning
    python3 install_jobs.py --all              also the optional jobs ("default": false in jobs.json)
                                               (the jobs of a module you chose in setup.py are included without --all)
    python3 install_jobs.py --uninstall        remove what this script registered
    python3 install_jobs.py --out DIR --os linux --dry-run     write the generated files into DIR for any system (to read them)

Jobs are idempotent: each one checks whether its work for the period is already done, so a second start is harmless.
That is what makes catching up after the computer was off safe: every job has a time trigger and, if "at_login" is
true, a login trigger. Windows (Task Scheduler) also has "run as soon as possible after a missed start".
"""
import argparse
import getpass
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from xml.sax.saxutils import escape

RADICE = Path(__file__).resolve().parent
NOMI_GIORNO_SYSTEMD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NOMI_GIORNO_WINDOWS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SISTEMI = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}


def sistema_corrente():
    return SISTEMI.get(platform.system(), "linux")


def cartella_log(sistema, home):
    home = Path(home)
    if sistema == "macos":
        return home / "Library" / "Logs"
    if sistema == "windows":
        return Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "second-brain" / "logs"
    return Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "second-brain"


def leggi_config(radice=RADICE):
    try:
        return json.loads((Path(radice) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def del_modulo_attivo(job, config):
    """Un job con "modulo" (e, se c'è, "se": {risposta: valore}) è voluto se quel modulo è attivo in config.json e le risposte coincidono."""
    scelte = (config or {}).get("moduli", {}).get(job.get("modulo"), {})
    return bool(scelte.get("attivo")) and all(scelte.get(k) == v for k, v in job.get("se", {}).items())


def seleziona(jobs, sistema, solo=None, tutti=False, config=None):
    """Job per questo sistema. Di default quelli con "default" vero (o assente) e quelli di un modulo attivo; --all anche gli altri."""
    out = {}
    for nome, j in jobs.items():
        if solo is not None and nome not in solo:
            continue
        if sistema not in j.get("os", ["macos", "linux", "windows"]):
            continue
        if solo is None and not tutti and not j.get("default", True) and not del_modulo_attivo(j, config):
            continue
        out[nome] = j
    return out


def comando(job, ctx, sistema=None):
    """Lista di argomenti con i segnaposto risolti. Il primo diventa un percorso assoluto (systemd lo richiede).
    Per Windows i percorsi con segnaposto hanno tutti il separatore di Windows (altrimenti si mescolano / e \\)."""
    valori = {"python": ctx["python"], "vault": str(ctx["vault"]), "home": str(ctx["home"])}
    args = [str(PureWindowsPath(a.format(**valori))) if sistema == "windows" and "{" in a else a.format(**valori) for a in job["command"]]
    args[0] = shutil.which(args[0]) or args[0]
    return args


def giorni(job):
    return sorted(job.get("days") or [])


# ---- macOS: launchd

def piano_launchd(nome, job, ctx):
    etichetta = "%s.%s" % (ctx["etichetta"], nome)
    args = comando(job, ctx)
    if not job.get("service"):
        args = ["/usr/bin/caffeinate", "-i"] + args  # il Mac resta sveglio finché il job lavora
    log = str(ctx["log"] / ("second-brain-%s.log" % nome))
    plist = {"Label": etichetta, "ProgramArguments": args, "WorkingDirectory": str(ctx["vault"]), "StandardOutPath": log, "StandardErrorPath": log,
             "EnvironmentVariables": {"PATH": "%s/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" % ctx["home"]}}
    if job.get("time") and giorni(job):
        h, m = (int(x) for x in job["time"].split(":"))
        plist["StartCalendarInterval"] = [{"Weekday": g % 7, "Hour": h, "Minute": m} for g in giorni(job)]  # launchd: domenica 0, lunedì 1
    if job.get("at_login") or job.get("service"):
        plist["RunAtLoad"] = True
    if job.get("service"):
        plist["KeepAlive"] = True
    percorso = Path(ctx["home"]) / "Library" / "LaunchAgents" / ("%s.plist" % etichetta)
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return {"file": [("%s.plist" % etichetta, plistlib.dumps(plist))], "dest": percorso.parent,
            "avvia": [["?", "launchctl", "bootout", "gui/%d/%s" % (uid, etichetta)], ["launchctl", "bootstrap", "gui/%d" % uid, str(percorso)]],
            "ferma": [["?", "launchctl", "bootout", "gui/%d/%s" % (uid, etichetta)]]}


# ---- Linux: systemd (utente)

def _q(parola):
    """Quota una parola per ExecStart di systemd."""
    return '"%s"' % parola.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") if any(c in parola for c in ' "\\\t') or "%" in parola else parola


def piano_systemd(nome, job, ctx):
    etichetta = "%s.%s" % (ctx["etichetta"], nome)
    log = str(ctx["log"] / ("second-brain-%s.log" % nome))
    servizio = ["[Unit]", "Description=second-brain %s: %s" % (nome, job.get("description", "")), "",
                "[Service]", "Type=%s" % ("simple" if job.get("service") else "oneshot"),
                "ExecStart=%s" % " ".join(_q(a) for a in comando(job, ctx)), "WorkingDirectory=%s" % ctx["vault"],
                "Environment=PATH=%s/.local/bin:/usr/local/bin:/usr/bin:/bin" % ctx["home"],
                "StandardOutput=append:%s" % log, "StandardError=append:%s" % log]
    if job.get("service"):
        # always, not on-failure: a clean exit (code 0) must also bring the service back, like launchd's KeepAlive.
        servizio += ["Restart=always", "RestartSec=10"]
    file, avvia, ferma = [], [["systemctl", "--user", "daemon-reload"]], []
    if job.get("at_login") or job.get("service"):
        servizio += ["", "[Install]", "WantedBy=default.target"]
        avvia.append(["systemctl", "--user", "enable", "--now", "%s.service" % etichetta])
        ferma.append(["systemctl", "--user", "disable", "--now", "%s.service" % etichetta])
    file.append(("%s.service" % etichetta, "\n".join(servizio) + "\n"))
    if job.get("time") and giorni(job):
        quando = ",".join(NOMI_GIORNO_SYSTEMD[g - 1] for g in giorni(job)) + " " + job["time"] + ":00"
        timer = ["[Unit]", "Description=second-brain %s (timer)" % nome, "", "[Timer]", "OnCalendar=%s" % quando,
                 "Persistent=true", "Unit=%s.service" % etichetta, "", "[Install]", "WantedBy=timers.target"]
        file.append(("%s.timer" % etichetta, "\n".join(timer) + "\n"))
        avvia.append(["systemctl", "--user", "enable", "--now", "%s.timer" % etichetta])
        ferma.append(["systemctl", "--user", "disable", "--now", "%s.timer" % etichetta])
    return {"file": file, "dest": Path(ctx["home"]) / ".config" / "systemd" / "user", "avvia": avvia, "ferma": ferma}


# ---- Windows: Utilità di pianificazione

def utente_windows(ctx):
    """DOMINIO\\utente per il trigger «all'accesso»: il job parte solo per te e si registra senza amministratore."""
    if ctx.get("utente"):
        return ctx["utente"]
    nome = os.environ.get("USERNAME") or getpass.getuser()
    dominio = os.environ.get("USERDOMAIN")
    return "%s\\%s" % (dominio, nome) if dominio else nome


def piano_windows(nome, job, ctx):
    etichetta = "%s.%s" % (ctx["etichetta"], nome)
    log = ctx["log"] / ("second-brain-%s.log" % nome)
    args = comando(job, ctx, "windows")
    riga = " ".join('"%s"' % a for a in args)
    trigger = []
    if job.get("time") and giorni(job):
        giorno_xml = "".join("<%s />" % NOMI_GIORNO_WINDOWS[g - 1] for g in giorni(job))
        trigger.append("<CalendarTrigger><StartBoundary>2026-01-01T%s:00</StartBoundary><Enabled>true</Enabled>"
                       "<ScheduleByWeek><DaysOfWeek>%s</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>" % (job["time"], giorno_xml))
    if job.get("at_login") or job.get("service"):
        # senza UserId vuol dire «all'accesso di qualsiasi utente», che chiede i diritti di amministratore
        # A service that exits with code 0 is not a "failure", so RestartOnFailure never revives it. Re-firing the
        # logon trigger every 10 minutes acts as a watchdog: IgnoreNew skips the run while the service is still up.
        ripeti = "<Repetition><Interval>PT10M</Interval></Repetition>" if job.get("service") else ""
        trigger.append("<LogonTrigger>%s<Enabled>true</Enabled><UserId>%s</UserId></LogonTrigger>" % (ripeti, escape(utente_windows(ctx))))
    riavvio = "<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>" if job.get("service") else ""
    xml = ('<?xml version="1.0" encoding="UTF-16"?>\n<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
           "<RegistrationInfo><Description>%s</Description></RegistrationInfo><Triggers>%s</Triggers>"
           "<Principals><Principal id=\"Author\"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>"
           "<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
           "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><Enabled>true</Enabled>"
           "<ExecutionTimeLimit>%s</ExecutionTimeLimit>%s</Settings>"
           "<Actions Context=\"Author\"><Exec><Command>conhost.exe</Command><Arguments>%s</Arguments><WorkingDirectory>%s</WorkingDirectory></Exec></Actions></Task>"
           % (escape("second-brain %s: %s" % (nome, job.get("description", ""))), "".join(trigger), "PT0S" if job.get("service") else "PT2H", riavvio,
              # An InteractiveToken task running cmd.exe pops up an empty console window on every run. conhost --headless
              # gives cmd and its children (python, git, claude) a console that is never shown; the log redirect is unchanged.
              escape('--headless cmd.exe /c "%s >> "%s" 2>&1"' % (riga, log)), escape(str(ctx["vault"]))))
    nome_file = "%s.xml" % etichetta
    percorso = Path(ctx["home"]) / ".second-brain-jobs" / nome_file
    return {"file": [(nome_file, xml.encode("utf-16"))], "dest": percorso.parent,
            "avvia": [["schtasks", "/create", "/tn", etichetta, "/xml", str(percorso), "/f"]], "ferma": [["schtasks", "/delete", "/tn", etichetta, "/f"]]}


BACKEND = {"macos": piano_launchd, "linux": piano_systemd, "windows": piano_windows}


def piano(sistema, jobs, ctx):
    return {nome: BACKEND[sistema](nome, job, ctx) for nome, job in jobs.items()}


def contesto(sistema, radice=RADICE, home=None):
    home = Path(home or Path.home())
    return {"vault": Path(radice), "home": home, "python": sys.executable, "log": cartella_log(sistema, home),
            "etichetta": leggi_config(radice).get("etichetta", "second-brain")}


def esegui(args, dry):
    """Lancia un comando. Se il primo elemento è "?" il comando è facoltativo: un errore non ferma (per esempio togliere un job non ancora caricato)."""
    facoltativo = args[0] == "?"
    args = args[1:] if facoltativo else args
    print("  $ " + " ".join(args))
    if dry:
        return True
    try:
        return subprocess.run(args, capture_output=facoltativo).returncode == 0 or facoltativo
    except OSError as e:
        print("    non riuscito: %s" % e)
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--out", help="write the generated files here instead of the system folders (no commands run)")
    ap.add_argument("--os", choices=sorted(set(SISTEMI.values())), help="generate for another system (needs --out or --dry-run)")
    a = ap.parse_args(argv)
    sistema = a.os or sistema_corrente()
    if sistema != sistema_corrente() and not (a.out or a.dry_run):
        sys.exit("--os for another system needs --out or --dry-run")
    ctx = contesto(sistema)
    jobs = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
    try:
        config = json.loads((RADICE / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    scelti = seleziona(jobs, sistema, a.only.split(",") if a.only else None, a.all, config)
    if not scelti:
        sys.exit("no job to register for %s" % sistema)
    dry = a.dry_run or bool(a.out)
    for nome, p in piano(sistema, scelti, ctx).items():
        print("[%s]" % nome)
        destinazione = Path(a.out) if a.out else p["dest"]
        if a.uninstall:
            for c in p["ferma"]:
                esegui(c, dry)
            for nome_file, _ in p["file"]:
                print("  remove %s" % (destinazione / nome_file))
                if not dry:
                    (destinazione / nome_file).unlink(missing_ok=True)
            continue
        for nome_file, contenuto in p["file"]:
            print("  write %s" % (destinazione / nome_file))
            if not dry or a.out:
                destinazione.mkdir(parents=True, exist_ok=True)
                (destinazione / nome_file).write_bytes(contenuto if isinstance(contenuto, bytes) else contenuto.encode("utf-8"))
        if not a.out:
            if not dry:
                ctx["log"].mkdir(parents=True, exist_ok=True)
            for c in p["avvia"]:
                if not esegui(c, dry):
                    sys.exit("stopped at the first failure: fix it and run again")
    if sistema == "linux" and not a.uninstall:
        print("\nOn Linux, user timers run without a login session only after: loginctl enable-linger $USER")
    if sistema == "macos" and not a.uninstall:
        print("\nOptional, to wake the Mac for weekday jobs: sudo pmset repeat wakeorpoweron MTWRF 07:55:00")
    return 0


if __name__ == "__main__":
    sys.exit(main())
