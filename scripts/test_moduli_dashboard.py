import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("server", RADICE / "scripts" / "dashboard" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
D = RADICE / "scripts" / "dashboard"
HTML = "".join((D / n).read_text(encoding="utf-8") for n in ("index.html", "dashboard.js", "dashboard.css"))


def con_config(cfg):
    d = tempfile.TemporaryDirectory()
    if cfg is not None:
        (Path(d.name) / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return d


class ModelloAssistenteTest(unittest.TestCase):
    def prova(self, cfg):
        with con_config(cfg) as d:
            return server.modello_assistente(d)

    def test_locale_o_cloud_dal_config(self):
        self.assertEqual(self.prova({"modelli": {"assistente": "ollama:qwen3:8b"}}), {"nome": "qwen3:8b", "locale": True})
        self.assertEqual(self.prova({"modelli": {"assistente": "claude"}}), {"nome": "Claude", "locale": False})

    def test_senza_scelta_o_con_scelta_sbagliata_dice_nessuno(self):
        self.assertEqual(self.prova({}), {"nome": "nessuno", "locale": None})
        self.assertEqual(self.prova(None), {"nome": "nessuno", "locale": None})
        self.assertEqual(self.prova({"modelli": {"assistente": "gpt:x"}}), {"nome": "nessuno", "locale": None})

    def test_la_pagina_non_scrive_fisso_che_il_modello_e_locale(self):
        # se si passa a Claude la pagina continuerebbe a dire «locale» mentre i dati vanno nel cloud
        self.assertNotIn("Risposta del modello locale", HTML)
        self.assertNotIn("modello locale, risponde in sola lettura", HTML)
        self.assertIn('id="assistente-modello"', HTML)


class CalendarioAlModelloTest(unittest.TestCase):
    def prova(self, cfg):
        with con_config(cfg) as d:
            return server.calendario_al_modello(d)

    def test_modello_locale_o_nessuno_il_calendario_resta_sul_computer(self):
        self.assertTrue(self.prova({"modelli": {"assistente": "ollama:qwen3:8b"}}))

    def test_con_claude_serve_il_consenso_scritto(self):
        base = {"modelli": {"assistente": "claude"}}
        self.assertFalse(self.prova(base))
        self.assertFalse(self.prova({**base, "moduli": {"assistente": {"attivo": True, "calendario_al_cloud": "True"}}}))
        self.assertTrue(self.prova({**base, "moduli": {"assistente": {"attivo": True, "calendario_al_cloud": True}}}))


class ModuliAttiviTest(unittest.TestCase):
    def test_un_vault_nato_prima_del_wizard_mostra_tutto(self):
        for cfg in (None, {}, {"nome": "x"}):
            with con_config(cfg) as d:
                self.assertTrue(all(server.moduli_attivi(d).values()), cfg)

    def test_con_la_chiave_moduli_solo_i_moduli_scelti(self):
        with con_config({"moduli": {}}) as d:
            self.assertFalse(any(server.moduli_attivi(d).values()))
        with con_config({"moduli": {"radar": {"attivo": True}, "bozze": {"attivo": False}, "servizi": "si"}}) as d:
            self.assertEqual({k: v for k, v in server.moduli_attivi(d).items() if v}, {"radar": True})

    def test_config_illeggibile_non_rompe_la_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.json").write_text("{ no", encoding="utf-8")
            self.assertTrue(all(server.moduli_attivi(d).values()))


class PagineDeiModuliTest(unittest.TestCase):
    def test_le_pagine_dei_moduli_dichiarano_a_quale_modulo_appartengono(self):
        voci = dict(re.findall(r'data-vista="(\w+)"(?: data-modulo="([\w ]+)")?', HTML.split('id="schede"')[1].split("</nav>")[0]))
        self.assertEqual({v: voci[v] for v in ("radar", "post", "servizi", "prestazioni")},
                         {"radar": "radar", "post": "bozze", "servizi": "servizi", "prestazioni": "radar assistente"})
        for v in ("oggi", "progetti", "piano", "claude", "avvii", "configurazione"):
            self.assertEqual(voci[v], "", v)  # le pagine di base non dipendono da un modulo
        nomi = set(server.MODULI_NOTI)
        for m in " ".join(voci.values()).split():
            self.assertIn(m, nomi)


if __name__ == "__main__":
    unittest.main()
