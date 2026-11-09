import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("agenda", Path(__file__).parent / "dashboard" / "agenda.py")
agenda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agenda)

ADESSO = datetime(2026, 10, 30, 9, 0)


def evento(titolo, inizio, fine, cal="Personale", tutto=False):
    return {"calendario": cal, "titolo": titolo, "inizio": inizio, "fine": fine, "tuttoIlGiorno": tutto}


class AgendaTest(unittest.TestCase):
    def test_unisce_ordina_e_mette_in_cima_il_ritardo(self):
        eventi = [evento("Dentista", datetime(2026, 10, 31, 15, 0), datetime(2026, 10, 31, 16, 0)),
                  evento("Riunione", datetime(2026, 10, 30, 10, 30), datetime(2026, 10, 30, 11, 0), cal="Ufficio"),
                  evento("Lontano", datetime(2026, 11, 20, 10, 0), datetime(2026, 11, 20, 11, 0))]
        scadenze = [{"fonte": "piano", "testo": "Valutare OmniRoute", "data": "2026-10-30"},
                    {"fonte": "scadenze", "testo": "Vecchia", "data": "2026-10-28"}]
        v = agenda.unisci(eventi, scadenze, ADESSO, 7, {"Ufficio": {"mostra": True, "tipo": "lavoro"}})
        self.assertEqual([x["titolo"] for x in v], ["Vecchia", "Riunione", "Valutare OmniRoute", "Dentista"])
        self.assertTrue(v[0]["inRitardo"])
        self.assertEqual(v[0]["giorno"], "2026-10-30")      # il ritardo si mostra oggi
        self.assertEqual(v[0]["originale"], "2026-10-28")
        self.assertTrue(v[1]["lavoro"])
        self.assertEqual(v[2]["fonte"], "piano")             # le voci del piano mantengono i loro campi

    def test_i_post_scaduti_da_piu_di_due_giorni_sono_arretrati_e_vanno_in_fondo_al_ritardo(self):
        # dieci post rossi in cima a «Cosa mi aspetta» saturano l'allarme: il rosso resta per ciò che chiede una decisione oggi
        scadenze = [{"fonte": "post", "testo": "Post: vecchio", "data": "2026-10-20"},
                    {"fonte": "post", "testo": "Post: di ieri", "data": "2026-10-29"},
                    {"fonte": "piano", "testo": "Voce del piano vecchia", "data": "2026-10-10"},
                    {"fonte": "post", "testo": "Post: tra due giorni", "data": "2026-11-01"}]
        v = agenda.unisci([], scadenze, ADESSO)
        per_titolo = {x["titolo"]: x for x in v}
        self.assertTrue(per_titolo["Post: vecchio"]["arretrato"])
        self.assertFalse(per_titolo["Post: di ieri"].get("arretrato", False))            # ieri non è un arretrato
        self.assertFalse(per_titolo["Voce del piano vecchia"].get("arretrato", False))   # solo i post
        self.assertFalse(per_titolo["Post: tra due giorni"].get("arretrato", False))
        titoli = [x["titolo"] for x in v]
        self.assertEqual(set(titoli[:2]), {"Voce del piano vecchia", "Post: di ieri"})  # prima il ritardo che chiede una decisione
        self.assertEqual(titoli[2], "Post: vecchio")                                  # poi l'arretrato

    def test_la_pagina_raggruppa_gli_arretrati(self):
        D = Path(__file__).parent / "dashboard"
        html = "".join((D / n).read_text(encoding="utf-8") for n in ("index.html", "dashboard.js", "dashboard.css"))
        self.assertIn("v.arretrato", html)
        self.assertIn("'Post arretrati (' +", html)

    def test_lo_stesso_evento_in_due_calendari_si_mostra_una_volta(self):
        a, b = datetime(2026, 11, 2, 15, 0), datetime(2026, 11, 2, 16, 0)
        v = agenda.unisci([evento("Dentista", a, b, cal="Google"), evento("Dentista", a, b, cal="Apple"), evento("Dentista", a, b.replace(hour=17))], [], ADESSO)
        self.assertEqual(len(v), 2)

    def test_calendario_nascosto_e_evento_in_corso(self):
        eventi = [evento("Rumore", datetime(2026, 10, 30, 9, 0), datetime(2026, 10, 30, 10, 0), cal="Festività"),
                  evento("Viaggio", datetime(2026, 10, 28, 0, 0), datetime(2026, 11, 2, 0, 0), tutto=True)]
        v = agenda.unisci(eventi, [], ADESSO, 7, {"Festività": {"mostra": False, "tipo": "personale"}})
        self.assertEqual([x["titolo"] for x in v], ["Viaggio"])
        self.assertTrue(v[0]["inCorso"])
        self.assertEqual(v[0]["giorno"], "2026-10-30")

    def test_config_e_file_creato_una_volta_sola(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "calendari.md"
            self.assertTrue(agenda.scrivi_config(f, ["Lavoro", "Casa"]))
            self.assertFalse(agenda.scrivi_config(f, ["Altro"]))
            c = agenda.leggi_config(f)
            self.assertEqual(set(c), {"Lavoro", "Casa"})
            f.write_text(f.read_text(encoding="utf-8").replace("| Lavoro | sì | personale |", "| Lavoro | no | lavoro |"), encoding="utf-8")
            self.assertEqual(agenda.leggi_config(f)["Lavoro"], {"mostra": False, "tipo": "lavoro", "scrivi": False})

    def test_leggi_eventi_converte_gli_orari_in_locali(self):
        finto = lambda codice: json.dumps([{"calendario": "C", "titolo": "", "inizio": "2026-10-30T08:00:00.000Z", "fine": "2026-10-30T09:00:00.000Z", "tuttoIlGiorno": False}])
        e = agenda.leggi_eventi(7, finto)[0]
        self.assertEqual(e["titolo"], "(senza titolo)")
        self.assertIsNone(e["inizio"].tzinfo)


if __name__ == "__main__":
    unittest.main()
