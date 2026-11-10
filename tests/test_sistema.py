import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
import sistema  # noqa: E402


def carica(nome):
    spec = importlib.util.spec_from_file_location(nome, RADICE / (nome + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


setup = carica("setup")
SCAN_GRANDE = {"sistema": "macos", "arch": "arm64", "ram_gb": 32, "disco_libero_gb": 200, "cpu": 10, "gpu": "Apple Silicon (unified memory)"}


class ConsigliTest(unittest.TestCase):
    def test_il_modello_dipende_da_ram_e_disco(self):
        self.assertEqual(sistema.consigli(SCAN_GRANDE), {"chat": "qwen3:8b", "embedding": "bge-m3"})
        self.assertEqual(sistema.consigli({**SCAN_GRANDE, "ram_gb": 8})["chat"], "qwen3:4b-instruct-2507")
        self.assertEqual(sistema.consigli({**SCAN_GRANDE, "ram_gb": 4}), {"chat": None, "embedding": None})
        self.assertIsNone(sistema.consigli({**SCAN_GRANDE, "disco_libero_gb": 6})["chat"])  # un download da 5 GB su 6 liberi no
        self.assertEqual(sistema.consigli({**SCAN_GRANDE, "ram_gb": None}), {"chat": None, "embedding": None})

    def test_la_scansione_ha_solo_dati_del_computer(self):
        self.assertEqual(set(sistema.scansiona()), {"sistema", "arch", "ram_gb", "disco_libero_gb", "cpu", "gpu"})

    def test_gpu_nvidia_e_apple(self):
        finto = mock.Mock(return_value=mock.Mock(returncode=0, stdout="NVIDIA RTX 4060, 8188 MiB\n"))
        self.assertEqual(sistema.gpu(finto, quale=lambda n: "/usr/bin/nvidia-smi", sistema="linux", arch="x86_64"), "NVIDIA RTX 4060, 8188 MiB")
        self.assertIn("Apple", sistema.gpu(finto, quale=lambda n: None, sistema="macos", arch="arm64"))
        self.assertIsNone(sistema.gpu(finto, quale=lambda n: None, sistema="windows", arch="AMD64"))


class PianoTest(unittest.TestCase):
    def test_comandi_dei_gestori_di_pacchetti_come_liste(self):
        brew = lambda n: "/opt/homebrew/bin/" + n
        self.assertEqual(sistema.piano_installazione("obsidian", "macos", brew)[0], ["brew", "install", "--cask", "obsidian"])
        self.assertEqual(sistema.piano_installazione("ollama", "windows", lambda n: n)[0][:4], ["winget", "install", "--id", "Ollama.Ollama"])
        self.assertEqual(sistema.piano_installazione("obsidian", "linux", lambda n: n)[0][:2], ["flatpak", "install"])

    def test_senza_il_gestore_dice_quale_manca(self):
        self.assertEqual(sistema.piano_installazione("obsidian", "macos", lambda n: None), (None, "brew"))

    def test_gli_installatori_da_internet_non_si_eseguono(self):
        """Claude Code e Ollama su Linux si installano con uno script scaricato: il wizard lo mostra, non lo lancia."""
        for programma, os_ in (("claude", "macos"), ("claude", "windows"), ("claude", "linux"), ("ollama", "linux"), ("gitleaks", "linux")):
            self.assertEqual(sistema.piano_installazione(programma, os_, lambda n: n), (None, None), (programma, os_))
        for per_sistema in sistema.PACCHETTI.values():
            for gestore, comando in per_sistema.values():
                self.assertIn(gestore, ("brew", "winget", "flatpak"))
                self.assertNotIn("|", " ".join(comando))

    def test_esegui_rifiuta_una_stringa(self):
        with self.assertRaises(AssertionError):
            sistema.esegui("brew install x; rm -rf /")


class BarraDiStatoTest(unittest.TestCase):
    def test_aggiunge_con_copia_e_non_sovrascrive(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / ".claude" / "settings.json"
            self.assertEqual(sistema.aggiungi_statusline(f, "x"), "aggiunta")  # il file non c'era: nasce
            f.write_text(json.dumps({"model": "m"}), encoding="utf-8")
            self.assertEqual(sistema.aggiungi_statusline(f, "x"), "aggiunta")
            dati = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual((dati["model"], dati["statusLine"]), ("m", {"type": "command", "command": "x"}))
            self.assertEqual(json.loads(f.with_name("settings.json.bak-second-brain").read_text(encoding="utf-8")), {"model": "m"})
            self.assertEqual(sistema.aggiungi_statusline(f, "altro"), "gia-presente")
            self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["statusLine"]["command"], "x")

    def test_un_file_non_json_non_si_tocca(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "settings.json"
            f.write_text("{ non json", encoding="utf-8")
            self.assertEqual(sistema.aggiungi_statusline(f, "x"), "illeggibile")
            self.assertEqual(f.read_text(encoding="utf-8"), "{ non json")


class FintoDoctor:
    INSTALLA = {"claude": {"macos": "curl ... | bash", "linux": "curl ... | bash", "windows": "irm ... | iex"}}

    def __init__(self, scaricati=(), attivo=True):
        self.scaricati, self.attivo = set(scaricati), attivo

    def trova_obsidian(self): return False
    def ollama_attivo(self): return self.attivo
    def modelli_scaricati(self): return self.scaricati if self.attivo else None


class PercorsoGuidatoTest(unittest.TestCase):
    def vault(self, t, modelli=None, radar=False):
        d = Path(t)
        (d / "config.json").write_text(json.dumps({"modelli": modelli or {}}), encoding="utf-8")
        (d / "install_jobs.py").write_text("", encoding="utf-8")
        (d / "memory").mkdir()
        (d / "memory" / "feeds.md").write_text("- https://a.example/rss\n", encoding="utf-8")
        (d / "scripts").mkdir()
        (d / "scripts" / "feed.py").write_text("", encoding="utf-8")
        return d

    def esegui(self, d, si, attivi=None, doctor=None, installato=lambda n, doc=None: False, piano=None):
        comandi, domande = [], []

        def risposta(testo, predef=False):
            domande.append(testo)
            return si(testo)
        with mock.patch.object(sistema, "installato", installato), \
                mock.patch.object(sistema, "piano_installazione", piano or (lambda n, *a: (["pacchetto", "installa", n], None))), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            setup.passi_guidati(attivi or {"core": {}}, "en", d, risposta, esegui=lambda c: comandi.append(c) or 0, scan=SCAN_GRANDE,
                                home=d / "casa", doctor=doctor or FintoDoctor())
        return comandi, domande, out.getvalue()

    def test_dicendo_no_a_tutto_non_si_lancia_niente(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t, {"assistente": "ollama:qwen3:8b"})
            comandi, domande, _ = self.esegui(d, lambda testo: False, {"core": {}, "radar": {}})
            self.assertEqual(comandi, [])
            self.assertTrue(len(domande) >= 3)
            self.assertFalse((d / "casa" / ".claude" / "settings.json").exists())

    def test_il_si_lancia_proprio_il_comando_mostrato(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t, {"assistente": "ollama:qwen3:8b"})
            comandi, domande, _ = self.esegui(d, lambda testo: testo.startswith("Install obsidian"))
            self.assertEqual(comandi, [["pacchetto", "installa", "obsidian"]])
            self.assertIn("Install obsidian? It runs: pacchetto installa obsidian", domande)

    def test_scarica_il_modello_solo_se_ollama_gira_e_dopo_il_si(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t, {"assistente": "ollama:qwen3:8b", "radar_embedding": "ollama:bge-m3"})
            installato = lambda n, doc=None: n == "ollama"
            comandi, _, _ = self.esegui(d, lambda testo: testo.startswith("Download qwen3"), doctor=FintoDoctor({"bge-m3:latest"}), installato=installato)
            self.assertEqual(comandi, [["ollama", "pull", "qwen3:8b"]])  # bge-m3 c'è già
            comandi, _, uscita = self.esegui(d, lambda testo: True, doctor=FintoDoctor(attivo=False), installato=installato)
            self.assertNotIn(["ollama", "pull", "qwen3:8b"], comandi)  # Ollama spento: non si prova, si dice come fare
            self.assertIn("ollama pull qwen3:8b", uscita)

    def test_poco_disco_salta_il_download(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t, {"assistente": "ollama:qwen3:8b"})
            comandi, domande, uscita = self.esegui(d, lambda testo: True, installato=lambda n, doc=None: n == "ollama")
            self.assertIn(["ollama", "pull", "qwen3:8b"], comandi)  # disco abbondante: si chiede e si scarica
            with mock.patch.dict(SCAN_GRANDE, {"disco_libero_gb": 6}):
                comandi, domande, uscita = self.esegui(d, lambda testo: True, installato=lambda n, doc=None: n == "ollama")
            self.assertNotIn(["ollama", "pull", "qwen3:8b"], comandi)
            self.assertIn("Not enough free disk", uscita)

    def test_senza_gestore_di_pacchetti_mostra_dove_scaricare(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t)
            comandi, domande, uscita = self.esegui(d, lambda testo: True, piano=lambda n, *a: (None, "brew"))
            self.assertFalse([c for c in comandi if c[0] == "brew"])
            self.assertIn("needs brew", uscita)
            self.assertIn("https://obsidian.md/download", uscita)

    def test_barra_di_stato_e_primo_giro_del_radar(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t)
            comandi, _, _ = self.esegui(d, lambda testo: testo.startswith(("Show your Claude", "Collect the news")), {"core": {}, "radar": {}})
            self.assertEqual([Path(c[-1]).name for c in comandi], ["feed.py", "radar.py"])
            impostazioni = json.loads((d / "casa" / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("statusline-uso.py", impostazioni["statusLine"]["command"])

    def test_regole_si_installano_solo_dopo_il_si(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t)
            (d / "scripts" / "installa-regole.py").write_text("", encoding="utf-8")
            comandi, domande, _ = self.esegui(d, lambda testo: False)
            self.assertEqual(comandi, [])
            self.assertTrue(any("push" in q and "force" in q for q in domande))
            comandi, _, _ = self.esegui(d, lambda testo: testo.startswith("Turn on the rules"))
            self.assertEqual([Path(c[-2]).name for c in comandi], ["installa-regole.py"])
            self.assertEqual(comandi[0][-1], "--si")

    def test_radar_senza_feed_non_lancia_niente(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.vault(t)
            (d / "memory" / "feeds.md").write_text("# Feeds\n", encoding="utf-8")
            comandi, _, uscita = self.esegui(d, lambda testo: testo.startswith("Collect the news"), {"core": {}, "radar": {}})
            self.assertEqual(comandi, [])
            self.assertIn("feeds.md", uscita)


class MenuModelliTest(unittest.TestCase):
    def opzioni(self, scan, d):
        with mock.patch.object(setup, "scansione", lambda: scan):
            return setup.opzioni_modello(d, "en")

    def test_il_menu_propone_il_modello_adatto_al_computer(self):
        d = {"validazione": "modello"}
        self.assertEqual([o[0] for o in self.opzioni(SCAN_GRANDE, d)], ["none", "claude", "ollama:qwen3:8b"])
        self.assertEqual([o[0] for o in self.opzioni({**SCAN_GRANDE, "ram_gb": 4}, d)], ["none", "claude", None])
        self.assertEqual([o[0] for o in self.opzioni(SCAN_GRANDE, {"validazione": "modello", "solo": ["none", "ollama"]})], ["none", "ollama:bge-m3"])

    def test_si_risponde_con_il_numero_e_il_valore_e_validato(self):
        domanda = {"id": "m", "tipo": "testo", "validazione": "modello", "predefinito": "none", "testo": "Which model", "avviso": "x"}
        for scelto, atteso in (("3", "ollama:qwen3:8b"), ("2", "claude"), ("1", "none"), ("", "none"), ("ollama:phi3", "ollama:phi3")):
            with mock.patch.object(setup, "scansione", lambda: SCAN_GRANDE), mock.patch("builtins.input", return_value=scelto), \
                    contextlib.redirect_stdout(io.StringIO()):
                risposte = setup.chiedi({"domande": [dict(domanda)]}, "en", setup.MESSAGGI["en"], {})
            self.assertEqual(risposte["m"], atteso, scelto)


if __name__ == "__main__":
    unittest.main()
