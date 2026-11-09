import importlib.util
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("avvii", Path(__file__).parent / "dashboard" / "avvii.py")
avvii = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avvii)

FERIALI = [(g, 8, 0) for g in range(1, 6)]
MERCOLEDI = datetime(2026, 10, 28, 9, 0)  # mercoledì


class TestAvvii(unittest.TestCase):
    def test_ultimo_previsto_oggi_e_settimanale(self):
        self.assertEqual(avvii.ultimo_previsto(FERIALI, MERCOLEDI), datetime(2026, 10, 28, 8, 0))
        self.assertEqual(avvii.ultimo_previsto([(1, 7, 30)], MERCOLEDI), datetime(2026, 10, 26, 7, 30))

    def test_domenica_zero_vale_sette(self):
        self.assertEqual(avvii.orari({"StartCalendarInterval": {"Weekday": 0, "Hour": 9}}), [(7, 9, 0)])

    def test_prossimo_salta_il_weekend(self):
        self.assertEqual(avvii.prossimo_previsto(FERIALI, datetime(2026, 10, 30, 9, 0)), datetime(2026, 11, 2, 8, 0))

    def test_stati(self):
        previsto = datetime(2026, 10, 28, 8, 0)
        adesso = datetime(2026, 10, 28, 9, 0)
        acceso = datetime(2026, 10, 28, 12, 55)
        self.assertEqual(avvii.stato_job(previsto, None, adesso, datetime(2026, 10, 28, 8, 5), False, None)[0], "ok")
        self.assertEqual(avvii.stato_job(previsto, None, adesso, datetime(2026, 10, 27, 18, 30), False, None)[0], "mancato")
        self.assertEqual(avvii.stato_job(previsto, None, adesso, None, False, None)[0], "mai")
        self.assertEqual(avvii.stato_job(previsto, None, datetime(2026, 10, 28, 8, 10), None, False, None)[0], "in-attesa")
        self.assertEqual(avvii.stato_job(previsto, None, adesso, None, True, None)[0], "in-corso")
        self.assertEqual(avvii.stato_job(previsto, None, datetime(2026, 10, 28, 14, 0), datetime(2026, 10, 28, 13, 0), False, acceso)[0], "in-ritardo")
        self.assertIn("12:55", avvii.stato_job(previsto, None, datetime(2026, 10, 28, 13, 0), None, False, acceso)[1])

    def test_esito_dal_codice_di_uscita_e_dall_ultima_riga(self):
        self.assertEqual(avvii.esito_job(1, "qualunque cosa")[0], "fallito")
        self.assertIn("codice 1", avvii.esito_job(1, "")[1])
        self.assertEqual(avvii.esito_job(0, "radar: inbox/2026-11-09-novita.md già elaborata, salto")[0], "saltato")
        self.assertEqual(avvii.esito_job(None, "radar: nessuna inbox, salto")[0], "saltato")
        self.assertIsNone(avvii.esito_job(0, "commit: chiusura 2026-11-09"))
        self.assertIsNone(avvii.esito_job(None, ""))

    def test_un_job_che_ha_scritto_dopo_l_orario_ma_e_fallito_o_saltato_non_e_ok(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "radar.log"
            plist = {"StartCalendarInterval": [{"Weekday": 1, "Hour": 7, "Minute": 30}], "StandardOutPath": str(log)}
            adesso = datetime(2026, 10, 26, 9, 0)  # lunedì
            ts = datetime(2026, 10, 26, 7, 45).timestamp()

            def stato(testo, exit_code):
                log.write_text(testo, encoding="utf-8")
                os.utime(log, (ts, ts))
                return avvii.avvii(adesso, {"radar": plist}, d, esiti={"radar": exit_code})["job"][0]["stato"]

            self.assertEqual(stato("radar: 4 schede scritte\n", 0), "ok")
            self.assertEqual(stato("radar: inbox/x.md già elaborata, salto\n", 0), "saltato")
            self.assertEqual(stato("Traceback (most recent call last)\n", 1), "fallito")
            self.assertEqual(stato("radar: 4 schede scritte\n", None), "ok")  # senza il codice si fida del log

    def test_un_giro_a_mano_piu_recente_dello_slot_vale_piu_del_codice_di_launchd(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "radar.log"
            plist = {"StartCalendarInterval": [{"Weekday": 1, "Hour": 7, "Minute": 30}], "StandardOutPath": str(log)}
            adesso = datetime(2026, 10, 26, 9, 0)  # lunedì, slot alle 7:30
            ts = datetime(2026, 10, 26, 8, 30).timestamp()
            log.write_text("radar: 4 schede scritte\n", encoding="utf-8")
            os.utime(log, (ts, ts))

            def stato(esiti, a_mano):
                return avvii.avvii(adesso, {"radar": plist}, d, esiti=esiti, giri_a_mano={"radar": a_mano} if a_mano else None)["job"][0]["stato"]

            # launchd è uscito con 1 alle 7:30, io l'ho rilanciato a mano alle 8:00 ed è andato bene: ora è ok
            self.assertEqual(stato({"radar": 1}, (datetime(2026, 10, 26, 8, 0), 0)), "ok")
            # launchd è andato bene, il giro a mano delle 8:00 è fallito: fallito
            self.assertEqual(stato({"radar": 0}, (datetime(2026, 10, 26, 8, 0), 2)), "fallito")
            # un giro a mano di prima dello slot non conta: vale launchd
            self.assertEqual(stato({"radar": 1}, (datetime(2026, 10, 26, 7, 0), 0)), "fallito")

    def test_le_righe_di_fallimento_della_chiusura_non_sono_ok(self):
        # chiudi-giornata esce sempre con 0: l'esito sta nell'ultima riga del log
        for riga in ("verify non passa: nessun commit. Vedi il log e la sezione Da confermare.",
                     "commit bloccato (hook pre-commit o git): vedi sopra, il lavoro resta non committato",
                     "claude non autenticato: chiusura non fatta, nessun commit. Lancia /login.",
                     "file già in stage fuori dalle cartelle autonome (scripts/x.py): nessun commit, il lavoro resta non committato"):
            self.assertEqual(avvii.esito_job(0, riga)[0], "fallito", riga)
        self.assertIsNone(avvii.esito_job(0, "commit: chiusura 2026-11-09"))
        self.assertIsNone(avvii.esito_job(0, "nessuna modifica da committare"))

    def test_ultimo_exit_legge_il_codice_dall_uscita_di_launchctl(self):
        from unittest import mock

        class R:
            def __init__(self, out):
                self.stdout = out
        casi = (("\tstate = not running\n\truns = 3\n\tlast exit code = 1\n", 1), ("\tlast exit code = 0\n", 0), ("\tlast exit code = (never exited)\n", None), ("", None))
        for out, atteso in casi:
            with mock.patch.object(avvii.subprocess, "run", return_value=R(out)):
                self.assertEqual(avvii.ultimo_exit("x.y"), atteso, out)

    def test_ultimo_exit_legge_launchctl(self):
        self.assertIsNone(avvii.ultimo_exit("etichetta.che.non.esiste.mai"))

    def test_la_pagina_conosce_i_nuovi_stati(self):
        D = Path(__file__).parent / "dashboard"
        html = "".join((D / n).read_text(encoding="utf-8") for n in ("index.html", "dashboard.js", "dashboard.css"))
        for stato in ("fallito", "saltato"):
            self.assertRegex(html, r"STATI_AVVIO = \{[^}]*\b" + stato + r"\b")


if __name__ == "__main__":
    unittest.main()
