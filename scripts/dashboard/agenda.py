"""Cosa mi aspetta: appuntamenti del calendario (scripts/calendario.py) e scadenze, uniti per giorno.

Gli appuntamenti si leggono in sola lettura, per esempio dall'app Calendario del Mac dove Google e Apple sono già
insieme, e restano nel processo del server: non si scrivono in nessun file e nessun modello li vede (ADR-001, ADR-002).
Il file docs/calendari.md contiene solo i nomi dei calendari, con se mostrarli e se sono di lavoro.
"""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location("calendario", Path(__file__).resolve().parent.parent / "calendario.py")
calendario = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(calendario)
_osascript = calendario._osascript


def nomi_calendari(esegui=_osascript):
    return calendario.Macos(esegui).nomi()


def leggi_eventi(giorni=7, esegui=_osascript, esclusi=()):
    """Gli eventi dell'app Calendario del Mac (vedi scripts/calendario.py). Il server usa il provider scelto in config.json."""
    return calendario.Macos(esegui).eventi(giorni, esclusi)


def leggi_config(file):
    """Nome calendario -> {'mostra': bool, 'tipo': str}, dalla tabella di docs/calendari.md. Un calendario assente si mostra."""
    out = {}
    try:
        righe = Path(file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    colonne = None
    for riga in righe:
        if not riga.startswith("|"):
            continue
        celle = [c.strip() for c in riga.strip().strip("|").split("|")]
        if colonne is None:
            colonne = [c.lower() for c in celle]
        elif not set("".join(celle)) <= set("-: "):
            d = dict(zip(colonne, celle))
            out[d.get("calendario", "")] = {"mostra": d.get("mostra", "sì").lower() in ("sì", "si", "s", "yes", "y"), "tipo": d.get("tipo", "personale").lower(),
                          "scrivi": d.get("scrivi", "no").lower() in ("sì", "si", "s", "yes", "y")}
    return out


def scrivi_config(file, nomi):
    """Crea docs/calendari.md con tutti i calendari mostrati, se il file non c'è ancora. Solo nomi."""
    if Path(file).exists():
        return False
    righe = ["# Calendari", "", "Quali calendari mostra la dashboard in «Cosa mi aspetta». Solo i nomi dei calendari, niente eventi.",
             "In «Mostra» scrivi sì o no. In «Scrivi» sì per i calendari dove l'assistente può aggiungere appuntamenti (solo personali, mai di lavoro). In «Tipo» scrivi personale o lavoro: un calendario di lavoro è segnato come tale e non lascia mai il Mac.", "",
             "| Calendario | Mostra | Tipo | Scrivi |", "|---|---|---|---|"]
    righe += ["| %s | sì | personale | no |" % n.replace("|", "/") for n in sorted(nomi)]
    Path(file).write_text("\n".join(righe) + "\n", encoding="utf-8")
    return True


ARRETRATO_DOPO_GIORNI = 2


def _ora(d):
    return d.strftime("%H:%M")


def unisci(eventi, scadenze, adesso, giorni=7, config=None):
    """Una lista ordinata di voci per i prossimi `giorni` giorni, più le scadenze già in ritardo.

    eventi: dal Calendario; scadenze: [{fonte, testo, data 'YYYY-MM-DD[ HH:MM]', ...altri campi passati così come sono}].
    """
    config = config or {}
    oggi = adesso.date()
    limite = oggi + timedelta(days=giorni)
    voci, visti = [], set()
    for e in eventi:
        c = config.get(e["calendario"], {"mostra": True, "tipo": "personale"})
        if not c["mostra"]:
            continue
        if (e["titolo"], e["inizio"], e["fine"]) in visti:  # lo stesso evento scritto in due calendari (Google e Apple) si mostra una volta
            continue
        visti.add((e["titolo"], e["inizio"], e["fine"]))
        giorno = max(e["inizio"].date(), oggi)
        if giorno >= limite:
            continue
        in_corso = e["inizio"].date() < oggi
        voci.append({"giorno": giorno.isoformat(), "ora": "" if e["tuttoIlGiorno"] else _ora(e["inizio"]), "fine": "" if e["tuttoIlGiorno"] else _ora(e["fine"]),
                     "titolo": e["titolo"], "fonte": "calendario", "dettaglio": e["calendario"], "lavoro": c["tipo"] == "lavoro",
                     "inRitardo": False, "inCorso": in_corso, "tuttoIlGiorno": e["tuttoIlGiorno"]})
    for s in scadenze:
        data = s["data"]
        giorno = datetime.strptime(data[:10], "%Y-%m-%d").date()
        ritardo = giorno < oggi
        if giorno >= limite:
            continue
        voce = dict(s)
        voce.update({"giorno": (oggi if ritardo else giorno).isoformat(), "originale": giorno.isoformat(), "ora": data[11:16] if len(data) >= 16 else "",
                     "fine": "", "titolo": s["testo"], "dettaglio": "", "lavoro": False, "inRitardo": ritardo, "inCorso": False, "tuttoIlGiorno": len(data) < 16,
                     # un post scaduto da più di due giorni è un arretrato: il rosso resta per ciò che chiede una decisione oggi
                     "arretrato": ritardo and s.get("fonte") == "post" and (oggi - giorno).days > ARRETRATO_DOPO_GIORNI})
        voci.append(voce)
    voci.sort(key=lambda v: (not v["inRitardo"], v.get("arretrato", False), v["giorno"], v["ora"] == "", v["ora"], v["titolo"]))
    return voci
