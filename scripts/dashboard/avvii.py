"""Scheda Avvii: per ogni job pianificato, l'ultimo orario previsto, l'ultimo log e se è partito.

Gli orari si leggono dai job di scripts/jobs.json (via genera_plist), quindi non si duplicano qui. Il log è lo
StandardOutPath del plist: la sua data di modifica è l'ultima volta che il job ha scritto.
"""
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# nome del job -> azione della dashboard che lo lancia a mano (None: nessun pulsante)
JOB_PIANIFICATI = {"morning": "morning", "chiusura": "chiudi-giornata", "radar": "radar", "pulizia": "pulizia", "bozze": "bozze"}
TOLLERANZA = timedelta(minutes=15)
# Ultime righe con cui i job dicono «sono partito ma non c'era niente da fare»
# Le righe con cui i job dicono di non aver finito il lavoro pur uscendo con 0 (chiudi-giornata esce sempre con 0)
FALLITO = re.compile(r"verify non passa|commit bloccato|non autenticato|già in stage fuori|Traceback", re.IGNORECASE)
SALTATO = re.compile(r"\bsalto\b|già elaborata|nessuna inbox|niente da aggiornare", re.IGNORECASE)


def orari(plist):
    """Lista di (giorno ISO 1-7 o None se ogni giorno, ora, minuto) dal plist."""
    intervalli = plist.get("StartCalendarInterval", [])
    if isinstance(intervalli, dict):
        intervalli = [intervalli]
    out = []
    for i in intervalli:
        giorno = i.get("Weekday")
        out.append((None if giorno is None else (giorno or 7), i.get("Hour", 0), i.get("Minute", 0)))
    return out


def ultimo_previsto(voci, adesso):
    """L'ultimo orario previsto non dopo 'adesso' (cerca negli ultimi 8 giorni), o None."""
    migliore = None
    for giorni_fa in range(8):
        giorno = adesso - timedelta(days=giorni_fa)
        for settimana, ora, minuto in voci:
            if settimana is not None and settimana != giorno.isoweekday():
                continue
            quando = giorno.replace(hour=ora, minute=minuto, second=0, microsecond=0)
            if quando <= adesso and (migliore is None or quando > migliore):
                migliore = quando
    return migliore


def prossimo_previsto(voci, adesso):
    migliore = None
    for giorni_avanti in range(8):
        giorno = adesso + timedelta(days=giorni_avanti)
        for settimana, ora, minuto in voci:
            if settimana is not None and settimana != giorno.isoweekday():
                continue
            quando = giorno.replace(hour=ora, minute=minuto, second=0, microsecond=0)
            if quando > adesso and (migliore is None or quando < migliore):
                migliore = quando
    return migliore


def avvio_mac():
    """Quando il Mac si è acceso (kern.boottime), o None."""
    try:
        r = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.boottime"], capture_output=True, text=True, encoding="utf-8", timeout=5)
        m = re.search(r"sec = (\d+)", r.stdout)
        return datetime.fromtimestamp(int(m.group(1))) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def ultimo_exit(etichetta):
    """Il codice di uscita dell'ultima esecuzione del job, da `launchctl print`, o None (mai partito, non registrato, sistema senza launchctl)."""
    try:
        r = subprocess.run(["/bin/launchctl", "print", "gui/%d/%s" % (os.getuid(), etichetta)], capture_output=True, text=True, encoding="utf-8", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"last exit code = (-?\d+)", r.stdout)
    return int(m.group(1)) if m else None


def esito_job(exit_code, riga):
    """(stato, spiegazione) se l'ultimo giro è fallito o non ha fatto nulla, altrimenti None. Il log scritto dopo l'orario previsto
    dice che il job è partito, non che è riuscito: il codice di uscita e l'ultima riga dicono come è andata."""
    if exit_code not in (None, 0):
        return "fallito", "l'ultimo giro è uscito con codice %s" % exit_code
    if FALLITO.search(riga or ""):
        return "fallito", "l'ultima riga del log dice che non ha finito: %s" % riga
    if SALTATO.search(riga or ""):
        return "saltato", "ha girato ma non c'era nulla da fare: %s" % riga
    return None


def _ultima_riga(log):
    try:
        righe = [r for r in log.read_text(encoding="utf-8", errors="replace").splitlines() if r.strip()]
    except OSError:
        return ""
    return righe[-1][:200] if righe else ""


def stato_job(previsto, prossimo, adesso, log_mtime, in_corso, acceso):
    """(stato, spiegazione). Stati: in-corso, ok, in-ritardo, in-attesa, mancato, mai."""
    if in_corso:
        return "in-corso", "in corso adesso"
    if previsto is None:
        return "in-attesa", "nessun orario previsto di recente"
    if log_mtime is not None and log_mtime >= previsto:
        if acceso is not None and acceso > previsto and log_mtime >= acceso:
            return "in-ritardo", "partito solo dopo l'accensione del Mac, alle %s" % acceso.strftime("%H:%M")
        return "ok", "ha scritto dopo l'orario previsto"
    if adesso - previsto <= TOLLERANZA:
        return "in-attesa", "l'orario previsto è appena passato"
    motivo = "non ha scritto dopo l'orario previsto"
    if acceso is not None and acceso > previsto:
        motivo += ": il Mac si è acceso alle %s, dopo" % acceso.strftime("%H:%M")
    return ("mai" if log_mtime is None else "mancato"), motivo


def avvii(adesso, jobs, cartella_log, in_corso=(), acceso=None, azioni=(), esiti=None, giri_a_mano=None):
    """Una riga per job pianificato. 'in_corso' sono i nomi delle azioni avviate dalla dashboard e ancora vive;
    'esiti' è {job: codice di uscita dell'ultimo giro} (da ultimo_exit); 'giri_a_mano' è {azione: (inizio, codice)} dei giri lanciati
    dalla dashboard: se è più recente dell'ultimo orario previsto vale il suo codice, perché il log è lo stesso e launchd non sa del giro a mano."""
    righe = []
    for nome, azione in JOB_PIANIFICATI.items():
        if nome not in jobs:  # un job di un modulo non scelto non è registrato
            continue
        plist = jobs[nome]
        voci = orari(plist)
        log = Path(plist.get("StandardOutPath", "")) if plist.get("StandardOutPath") else Path(cartella_log) / ("second-brain-%s.log" % nome)
        log_mtime = datetime.fromtimestamp(log.stat().st_mtime) if log.exists() else None
        previsto = ultimo_previsto(voci, adesso)
        prossimo = prossimo_previsto(voci, adesso)
        stato, motivo = stato_job(previsto, prossimo, adesso, log_mtime, azione in in_corso, acceso)
        ultima = _ultima_riga(log) if log.exists() else ""
        if stato in ("ok", "in-ritardo"):  # partito: ma è riuscito?
            giro = (giri_a_mano or {}).get(azione)
            codice = giro[1] if giro and previsto and giro[0] >= previsto else (esiti or {}).get(nome)
            esito = esito_job(codice, ultima)
            if esito:
                stato, motivo = esito
        righe.append({
            "nome": nome,
            "azione": azione if azione in azioni else None,
            "previsto": previsto.isoformat(timespec="minutes") if previsto else None,
            "prossimo": prossimo.isoformat(timespec="minutes") if prossimo else None,
            "ultimoLog": log_mtime.isoformat(timespec="minutes") if log_mtime else None,
            "stato": stato,
            "motivo": motivo,
            "ultimaRiga": ultima,
        })
    return {"macAcceso": acceso.isoformat(timespec="minutes") if acceso else None, "job": righe}
