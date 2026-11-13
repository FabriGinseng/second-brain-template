import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("radar_claude", Path(__file__).resolve().parent / "radar-claude.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

INBOX = """# Novità del 2026-11-09

- [Node 24.22.2 Security Releases](https://nodejs.org/en/blog/vulnerability/x) — Tue, 03 Nov 2026
  > Fix per tre CVE nel runtime.
- [Cloudflare WAF nuovo](https://blog.cloudflare.com/waf/) — Mon, 02 Nov 2026
- [Nuxt 4.3.0](https://github.com/nuxt/nuxt/releases/tag/v4.3.0) — 2026-11-05
"""
INDICE = """| Progetto | Stack | Stato | Priorità | Ultimo aggiornamento |
|---|---|---|---|---|
| [[projects/api/STATE\\|api]] | Node 24, Fastify | ok | alta | 2026-11-09 |
| [[projects/sito/STATE\\|sito]] | Nuxt 4 | ok | alta | 2026-11-09 |
| [[projects/@@/STATE\\|lavoro]] | Cliente X | ok | alta | 2026-11-09 |
| [[projects/segreto/STATE\\|segreto]] | Riservato | ok | alta | 2026-11-09 |
""".replace("@@", "la" + "voro")


class RadarClaude(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.v = Path(self.tmp.name)
        for n in ("inbox", "radar", "daily"):
            (self.v / n).mkdir()
        (self.v / "projects").mkdir()
        (self.v / "projects" / "INDEX.md").write_text(INDICE, encoding="utf-8")
        for n in ("api", "sito", "lavoro", "segreto"):
            (self.v / "projects" / n).mkdir()
            (self.v / "projects" / n / "STATE.md").write_text("# %s\n## Obiettivo attuale\nobiettivo di %s\n## Dove sono\nx\n" % (n, n), encoding="utf-8")
        (self.v / "config.json").write_text(json.dumps({"moduli": {"riservata": {"cartella": "projects/segreto"}}}), encoding="utf-8")
        self.inbox = self.v / "inbox" / "2026-11-09-novita.md"
        self.inbox.write_text(INBOX, encoding="utf-8")

    def esegui(self, risposta):
        viste = []

        def chiedi(istruzioni, testo):
            viste.append(testo)
            return risposta if isinstance(risposta, str) else json.dumps(risposta)

        out = rc.radar_claude(self.v, chiedi)
        return out.read_text(encoding="utf-8"), viste

    def test_voci_con_riassunto(self):
        v = rc.voci(self.inbox)
        self.assertEqual([x["riassunto"] for x in v], ["Fix per tre CVE nel runtime.", "", ""])
        self.assertEqual(v[0]["url"], "https://nodejs.org/en/blog/vulnerability/x")

    def test_nel_prompt_non_entrano_lavoro_ne_riservata(self):
        _, viste = self.esegui({"schede": []})
        self.assertIn("api:", viste[0])
        self.assertIn("sito:", viste[0])
        self.assertNotIn("lavoro", viste[0])
        self.assertNotIn("segreto", viste[0])
        self.assertNotIn("Cliente X", viste[0])

    def test_la_scheda_usa_titolo_e_link_dell_inbox(self):
        testo, _ = self.esegui({"schede": [{"n": 1, "progetti": ["api", "sito", "lavoro", "inventato", "api"], "tipo": "sicurezza", "cosa": "tre CVE", "azione": "aggiornare Node", "costo": "10 minuti",
                                            "url": "https://evil.example", "titolo": "falso"}]})
        self.assertIn("### [Node 24.22.2 Security Releases](https://nodejs.org/en/blog/vulnerability/x)", testo)
        self.assertIn("- **Progetti:** [[projects/api/STATE|api]], [[projects/sito/STATE|sito]]\n", testo)  # solo quelli dell'indice, senza doppioni
        self.assertIn("- **Costo per provarlo:** 10 minuti", testo)
        self.assertNotIn("evil", testo)

    def test_schede_non_valide_si_scartano_il_resto_passa(self):
        buona = {"n": 3, "progetti": ["sito"], "tipo": "progetto", "cosa": "c", "azione": "a", "costo": "k"}
        schede = [
            {**buona, "n": 9}, {**buona, "n": 0}, {**buona, "n": "1"}, {**buona, "n": True},
            {**buona, "progetti": ["lavoro"]}, {**buona, "progetti": ["inventato"]}, {**buona, "progetti": "api"}, {**buona, "progetti": []}, {**buona, "tipo": "altro"}, {**buona, "cosa": ""},
            "testo", buona, buona,
        ]
        testo, _ = self.esegui({"schede": schede})
        self.assertEqual(testo.count("### "), 1)
        self.assertIn("Nuxt 4.3.0", testo)
        self.assertEqual(rc._titolo({"titolo": "v4.6.4", "url": "https://github.com/nuxt/nuxt/releases/tag/v4.6.4"}), "nuxt/nuxt v4.6.4")

    def test_i_campi_non_possono_fare_link_ne_andare_a_capo(self):
        testo, _ = self.esegui({"schede": [{"n": 2, "progetti": ["api"], "tipo": "progetto", "cosa": "[clic](https://evil.example)\n## Titolo finto",
                                            "azione": "x" * 1000, "costo": "ok"}]})
        self.assertNotIn("](https://evil", testo)
        self.assertEqual(testo.count("\n## "), 1)  # solo «Da leggere»
        self.assertLess(max(len(r) for r in testo.splitlines()), 300)

    def test_risposta_senza_schede_e_un_errore(self):
        for r in ('{"altro": 1}', "[]", '{"schede": "no"}'):
            with self.assertRaises(ValueError):
                self.esegui(r)

    def test_nessuna_scheda_scrive_il_giro_vuoto(self):
        testo, _ = self.esegui({"schede": []})
        self.assertIn("Nessuna novità rilevante", testo)
        self.assertIn("Novità lette: 3. Schede: 0.", testo)

    def test_massimo_otto_schede(self):
        inbox = "\n".join("- [Voce %d](https://x.example/%d)" % (i, i) for i in range(1, 21))
        self.inbox.write_text("# x\n\n" + inbox + "\n", encoding="utf-8")
        schede = [{"n": i, "progetti": ["api"], "tipo": "progetto", "cosa": "c", "azione": "a", "costo": "k"} for i in range(1, 21)]
        testo, _ = self.esegui({"schede": schede})
        self.assertEqual(testo.count("### "), rc.MAX_SCHEDE)

    def test_skill_con_versione_nuova_solo_come_proposta(self):
        (self.v / "daily" / "2026-W45-skill.json").write_text(json.dumps({"skill": [
            {"nome": "grilling", "stato": "nuova", "azione": "aggiornare, con il tuo ok"},
            {"nome": "design-taste-frontend", "stato": "rimossa", "azione": "valutare la rimozione"},
            {"nome": "ok", "stato": "uguale", "azione": "nessuna: già all'ultima versione"}]}), encoding="utf-8")
        testo, _ = self.esegui({"schede": []})
        self.assertIn("## Skill con una versione nuova", testo)
        self.assertIn("- grilling: aggiornare, con il tuo ok", testo)
        self.assertNotIn("design-taste", testo)
        self.assertNotIn("ok:", testo)

    def test_senza_progetti_non_chiama_il_modello(self):
        (self.v / "projects" / "INDEX.md").write_text("| Progetto |\n|---|\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.esegui({"schede": []})


if __name__ == "__main__":
    unittest.main()
