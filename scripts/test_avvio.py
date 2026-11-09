import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("avvio", Path(__file__).resolve().parent / "avvio.py")
avvio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avvio)


class Esito:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout = returncode, stdout


class Avvio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Path(self.tmp.name)
        (self.v / "daily").mkdir()
        self.log = self.v / "avvio.log"
        self.chiamate, self.attese = [], []
        self.pending, self.nuovi, self.rc = "", "", {}
        self.risposte = [True]
        avvio.APRI = ["open"]

    def tearDown(self):
        self.tmp.cleanup()

    def run_finto(self, cmd, **kw):
        self.chiamate.append(cmd)
        nome = cmd[0] if cmd[0] in ("git", "open") else Path(cmd[-1]).name
        uscita = {"git": self.pending, "attivita-progetti.py": self.nuovi}.get(nome, "")
        return Esito(self.rc.get(nome, 0), uscita + "\n" if uscita else "")

    def vai(self, dry=False):
        risposte = iter(self.risposte)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = avvio.avvio(self.v, self.log, self.run_finto, {"AVVIO_DRY_RUN": "1"} if dry else {}, datetime(2026, 11, 3, 9, 0),
                             attese_append(self.attese), lambda url: next(risposte, False))
        return rc, buf.getvalue()

    def nomi(self):
        return [c[0] if c[0] in ("git", "open") else Path(c[-1]).name for c in self.chiamate]

    def test_vault_pulito_e_brief_presente(self):
        (self.v / "daily" / "2026-11-03.md").write_text("x")
        rc, out = self.vai(dry=True)
        self.assertEqual(out.splitlines(), ["niente da chiudere", "brief di oggi già presente: non lo rigenero"])
        self.assertEqual(self.nomi(), ["aggiorna-oggi.py", "git", "attivita-progetti.py"])

    def test_radar_della_settimana_mancante_si_lancia(self):
        (self.v / "memory").mkdir()
        (self.v / "memory" / "feeds.md").write_text("https://esempio.it/feed\n")
        (self.v / "radar").mkdir()
        (self.v / "radar" / "2026-10-27.md").write_text("x")  # la settimana scorsa (oggi è martedì 2026-11-03)
        (self.v / "daily" / "2026-11-03.md").write_text("x")
        rc, out = self.vai()
        self.assertIn("radar di questa settimana assente: lo lancio", out)
        self.assertIn("radar.py", self.nomi())
        (self.v / "radar" / "2026-11-02.md").write_text("x")  # ora c'è
        self.chiamate.clear()
        self.vai()
        self.assertNotIn("radar.py", self.nomi())

    def test_dry_run_decide_ma_non_esegue(self):
        self.pending, self.nuovi = " M x", "fse: 2 commit"
        rc, out = self.vai(dry=True)
        self.assertEqual(out.splitlines()[0], "da chiudere: modifiche non committate commit nuovi nei repo")
        self.assertEqual(out.splitlines()[1], "brief di oggi assente: lancio /morning")
        self.assertNotIn("chiudi-giornata.py", self.nomi())
        self.assertNotIn("morning.py", self.nomi())
        self.assertNotIn("open", self.nomi())

    def test_solo_commit_nuovi(self):
        self.nuovi = "fse: 2 commit"
        self.assertEqual(self.vai(dry=True)[1].splitlines()[0], "da chiudere: commit nuovi nei repo")

    def test_flusso_completo_in_ordine(self):
        self.pending = " M x"
        rc, out = self.vai()
        self.assertEqual(rc, 0)
        self.assertEqual(self.nomi(), ["aggiorna-oggi.py", "git", "attivita-progetti.py", "chiudi-giornata.py", "morning.py", "open"])
        self.assertIn("dashboard aperta su http://127.0.0.1:8765/", out)
        self.assertIn("da chiudere: modifiche non committate", self.log.read_text(encoding="utf-8"))

    def test_gli_script_figli_scrivono_in_utf8_anche_su_windows(self):
        """Con -I PYTHONUTF8 non vale: senza -X utf8 su Windows un accento nell'output dei figli rompe la lettura in UTF-8."""
        self.pending = " M x"
        self.vai()
        figli = [c for c in self.chiamate if c[0] not in ("git", "open")]
        self.assertEqual(len(figli), 4)
        for c in figli:
            self.assertEqual(c[1:4], ["-I", "-X", "utf8"], c)

    def test_attende_la_dashboard_al_massimo_20_volte(self):
        self.risposte = []
        self.vai()
        self.assertEqual(len(self.attese), 20)
        self.risposte = [False, False, True]
        self.attese.clear()
        self.vai()
        self.assertEqual(len(self.attese), 2)

    def test_se_un_passo_fallisce_si_ferma(self):
        self.pending = " M x"
        self.rc["chiudi-giornata.py"] = 1
        rc, _ = self.vai()
        self.assertEqual(rc, 1)
        self.assertNotIn("morning.py", self.nomi())

    def test_due_giri_di_fila_non_rifanno_chiusura_e_brief(self):
        self.pending = " M x"
        self.vai()
        (self.v / "daily" / "2026-11-03.md").write_text("brief")  # lo ha scritto il primo giro
        self.pending, self.chiamate = "", []
        _, out = self.vai()
        self.assertEqual(out.splitlines()[:2], ["niente da chiudere", "brief di oggi già presente: non lo rigenero"])
        self.assertNotIn("chiudi-giornata.py", self.nomi())
        self.assertNotIn("morning.py", self.nomi())


def attese_append(lista):
    return lambda s: lista.append(s)


if __name__ == "__main__":
    unittest.main()
