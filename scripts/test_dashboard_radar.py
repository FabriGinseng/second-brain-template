#!/usr/bin/env python3
"""Dashboard, pagina Radar: la scheda del radar in un solo passo (progetti, tipo, cosa farci, costo) e i voti utile / non utile."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("server", RADICE / "scripts" / "dashboard" / "server.py")
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


SCHEDA_UN_PASSO = (
    "# Radar del 2026-11-13\n\n## Da leggere\n\n"
    "### [nuxt/nuxt v4.6.4](https://github.com/nuxt/nuxt/releases/tag/v4.6.4)\n"
    "- **Progetti:** [[projects/my-book-club/STATE|my-book-club]], [[projects/sommoPhoto/STATE|sommoPhoto]]\n"
    "- **Tipo:** sicurezza\n- **Cos'è:** Otto avvisi corretti.\n- **Cosa farci:** Aggiornare Nuxt.\n- **Costo per provarlo:** mezz'ora\n\n"
)


class RadarUnPassoTest(unittest.TestCase):
    def prepara(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        (d / "2026-11-13.md").write_text(SCHEDA_UN_PASSO, encoding="utf-8")
        return d, d / "feedback.jsonl"

    def test_la_scheda_ha_progetti_tipo_e_campi(self):
        d, f = self.prepara()
        c = server.radar(d, f)["daLeggere"][0]
        self.assertEqual(c["progetti"], ["my-book-club", "sommoPhoto"])
        self.assertEqual((c["tipo"], c["cosa"], c["azione"], c["costo"]), ("sicurezza", "Otto avvisi corretti.", "Aggiornare Nuxt.", "mezz'ora"))
        self.assertIsNone(c["giudizio"])

    def test_voto_utile_su_una_scheda_e_ultimo_voto_vince(self):
        d, f = self.prepara()
        server.vota_scartata("nuxt/nuxt v4.6.4", "utile", d, f)
        r = server.radar(d, f)
        self.assertEqual((r["daLeggere"][0]["giudizio"], r["utili"], r["nonUtili"], r["valutate"]), ("utile", 1, 0, 0))
        server.vota_scartata("nuxt/nuxt v4.6.4", "non-utile", d, f)
        r = server.radar(d, f)
        self.assertEqual((r["utili"], r["nonUtili"]), (0, 1))
        riga = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((riga["progetto"], riga["motivo"], riga["giudizio"]), ("my-book-club, sommoPhoto", "Otto avvisi corretti.", "utile"))

    def test_i_voti_non_si_incrociano(self):
        d, f = self.prepara()
        with self.assertRaises(LookupError):
            server.vota_scartata("nuxt/nuxt v4.6.4", "falso-scarto", d, f)  # è una scheda, non una scartata
        with self.assertRaises(LookupError):
            server.vota_scartata("altro titolo", "utile", d, f)
        self.assertFalse(f.exists())


if __name__ == "__main__":
    unittest.main()
