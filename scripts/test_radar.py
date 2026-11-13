import importlib.util
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("radar", Path(__file__).resolve().parent / "radar.py")
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)


class Radar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Path(self.tmp.name)
        (self.v / "inbox").mkdir()
        (self.v / "radar").mkdir()
        self.chiamate = []
        self.config("ollama:bge-m3")

    def config(self, embedding):
        (self.v / "config.json").write_text(json.dumps({"modelli": {"radar_embedding": embedding}}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, rel, t):
        p = self.v / rel
        p.write_text("x")
        os.utime(p, (t, t))
        return p

    def lancia(self, vault, *args):
        self.chiamate.append(args)

    def test_senza_inbox_salta(self):
        radar.radar(self.v, self.lancia)
        self.assertEqual(self.chiamate, [])

    def test_senza_inbox_della_settimana_raccoglie_il_feed(self):
        (self.v / "memory").mkdir()
        (self.v / "memory" / "feeds.md").write_text("https://esempio.it/feed\n")
        self.file("inbox/2026-11-02-novita.md", 100)  # la settimana scorsa
        self.file("radar/2026-11-02.md", 200)
        radar.radar(self.v, self.lancia, date(2026, 11, 9))  # lunedì
        self.assertEqual(self.chiamate, [("scripts/feed.py",)])

    def test_con_inbox_della_settimana_o_senza_feeds_non_raccoglie(self):
        self.file("inbox/2026-11-09-novita.md", 100)
        self.file("radar/2026-11-09.md", 200)
        (self.v / "memory").mkdir()
        (self.v / "memory" / "feeds.md").write_text("https://esempio.it/feed\n")
        radar.radar(self.v, self.lancia, date(2026, 11, 11))  # mercoledì, inbox di lunedì
        self.assertEqual(self.chiamate, [])
        (self.v / "memory" / "feeds.md").unlink()
        (self.v / "inbox" / "2026-11-09-novita.md").unlink()
        radar.radar(self.v, self.lancia, date(2026, 11, 11))  # niente indirizzi: la raccolta resta a n8n
        self.assertEqual(self.chiamate, [])

    def test_inbox_gia_elaborata_salta(self):
        self.file("inbox/2026-11-02-novita.md", 100)
        self.file("radar/2026-11-02.md", 200)
        radar.radar(self.v, self.lancia)
        radar.radar(self.v, self.lancia)  # due volte di seguito: niente
        self.assertEqual(self.chiamate, [])

    def test_se_lo_stadio_2_fallisce_il_giro_dopo_riprova(self):
        self.file("inbox/2026-11-02-novita.md", 100)

        def lancia(vault, *args):
            self.chiamate.append(args)
            if args[0].endswith("radar-stadio1.py"):
                self.file("radar/.candidati-2026-11-02.json", 200)
            if args[0].endswith("radar-stadio2.py"):
                raise RuntimeError("Ollama spento")
        with self.assertRaises(RuntimeError):
            radar.radar(self.v, lancia)
        self.chiamate.clear()
        with self.assertRaises(RuntimeError):
            radar.radar(self.v, lancia)
        self.assertEqual(len(self.chiamate), 3)  # indice, stadio 1, stadio 2: non salta

    def test_candidati_vecchi_non_bastano_e_gira_in_ordine_sull_ultimo(self):
        self.file("inbox/2026-10-26-novita.md", 50)
        self.file("inbox/2026-11-02-novita.md", 300)
        self.file("radar/2026-10-26.md", 100)  # la scheda della settimana scorsa non vale per l'inbox nuova
        # i passi 1 e 2 producono i candidati nuovi: li simulo al secondo passo
        def lancia(vault, *args):
            self.chiamate.append(args)
            if args[0].endswith("radar-stadio1.py"):
                self.file("radar/.candidati-2026-11-02.json", 400)
            if args[0].endswith("radar-output.py"):
                self.file("radar/2026-11-02.md", 500)
        radar.radar(self.v, lancia)
        self.assertEqual(self.chiamate, [
            ("scripts/indice-embedding.py",), ("scripts/radar-stadio1.py",),
            ("scripts/radar-stadio2.py", "radar/.candidati-2026-11-02.json"),
            ("scripts/radar-output.py", "radar/.candidati-2026-11-02.json")])
        radar.radar(self.v, lancia)  # secondo giro: la scheda c'è, non rifà niente
        self.assertEqual(len(self.chiamate), 4)


    def test_senza_embedding_non_calcola_l_indice(self):
        self.config("none")
        self.file("inbox/2026-11-02-novita.md", 100)
        radar.radar(self.v, self.lancia)
        self.assertEqual([c[0] for c in self.chiamate],
                         ["scripts/radar-stadio1.py", "scripts/radar-stadio2.py", "scripts/radar-output.py"])


    def test_con_claude_raccoglie_sempre_e_lancia_un_solo_passo(self):
        (self.v / "config.json").write_text(json.dumps({"modelli": {"radar_giudizio": "claude:haiku"}}), encoding="utf-8")
        (self.v / "memory").mkdir()
        (self.v / "memory" / "feeds.md").write_text("https://esempio.it/feed\n")
        self.file("inbox/2026-11-09-novita.md", 100)
        radar.radar(self.v, self.lancia, date(2026, 11, 11))  # mercoledì: con n8n l'inbox di lunedì basterebbe
        self.assertEqual(self.chiamate, [("scripts/feed.py",), ("scripts/radar-claude.py", "inbox/2026-11-09-novita.md")])

    def test_con_claude_una_scheda_piu_recente_dell_inbox_salta(self):
        (self.v / "config.json").write_text(json.dumps({"modelli": {"radar_giudizio": "claude"}}), encoding="utf-8")
        self.file("inbox/2026-11-09-novita.md", 100)
        self.file("radar/2026-11-09.md", 200)
        radar.radar(self.v, self.lancia, date(2026, 11, 11))
        self.assertEqual(self.chiamate, [])

    def test_con_claude_e_n8n_la_raccolta_resta_a_n8n(self):
        (self.v / "config.json").write_text(json.dumps({"modelli": {"radar_giudizio": "claude"}, "moduli": {"radar": {"automazione": "n8n"}}}), encoding="utf-8")
        (self.v / "memory").mkdir()
        (self.v / "memory" / "feeds.md").write_text("https://esempio.it/feed\n")
        self.file("inbox/2026-11-09-novita.md", 100)
        radar.radar(self.v, self.lancia, date(2026, 11, 11))
        self.assertEqual(self.chiamate, [("scripts/radar-claude.py", "inbox/2026-11-09-novita.md")])


if __name__ == "__main__":
    unittest.main()
