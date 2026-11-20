import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("morning", Path(__file__).resolve().parent / "morning.py")
morning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(morning)


class Esito:
    def __init__(self, rc, stdout=""):
        self.returncode, self.stdout = rc, stdout


class Morning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name) / "Obsidian.app"
        self.vault = Path("/x/second-brain")
        self.chiamate = []
        self.segnalazioni = []

    def tearDown(self):
        self.tmp.cleanup()

    def lancia(self, rc_per_comando=None):
        def run(cmd, **kw):
            self.chiamate.append(cmd)
            return Esito((rc_per_comando or {}).get(cmd[0], 0))
        return run

    def vai(self, run, env=None, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = morning.morning(self.vault, run, env or {}, date(2026, 11, 3), self.app, segnala=lambda *a: self.segnalazioni.append(a), **kw)
        return rc, buf.getvalue()

    def test_task_pronti_nel_prompt(self):
        rc, _ = self.vai(self.lancia(), pronti=lambda: "- progetto · piano · Task 1 «x» — basso → deepseek")
        self.assertEqual(rc, 0)
        self.assertEqual(self.chiamate[0][-1], "/morning Task pronti dallo smistatore:\n- progetto · piano · Task 1 «x» — basso → deepseek")

    def test_senza_task_pronti_resta_morning(self):
        self.vai(self.lancia(), pronti=lambda: "")
        self.assertEqual(self.chiamate[0][-1], "/morning")

    def test_smistatore_rotto_non_ferma_il_brief(self):
        def rotto():
            raise OSError("manca")
        rc, _ = self.vai(self.lancia(), pronti=rotto)
        self.assertEqual((rc, self.chiamate[0][-1]), (0, "/morning"))

    def test_smistatore_solo_se_config_lo_indica(self):
        v = Path(self.tmp.name)
        lanci = []
        def run(cmd, **kw):
            lanci.append(cmd)
            return Esito(0, "- task pronto\n")
        self.assertEqual(morning.pronti_smistatore(v, run), "")                       # niente config.json
        (v / "config.json").write_text('{"modelli": {}}', encoding="utf-8")
        self.assertEqual((morning.pronti_smistatore(v, run), lanci), ("", []))       # config senza la chiave
        (v / "config.json").write_text('{"smistatore": "~/s/bin/smistatore"}', encoding="utf-8")
        self.assertEqual(morning.pronti_smistatore(v, run), "- task pronto")
        self.assertEqual(lanci[0][2], str(Path.home() / "s" / "bin" / "smistatore"))

    def test_dry_run_stampa_e_non_esegue(self):
        rc, out = self.vai(self.lancia(), {"MORNING_DRY_RUN": "1"})
        self.assertEqual((rc, self.chiamate), (0, []))
        self.assertIn("claude --permission-mode dontAsk", out)
        self.assertIn("'Bash(git log *)'", out)

    def test_brief_verify_e_obsidian(self):
        self.app.mkdir()
        rc, out = self.vai(self.lancia())
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "verify: OK")
        self.assertEqual(self.chiamate[0][0], "claude")
        self.assertEqual(self.chiamate[1][-1], "scripts/verify")
        self.assertEqual(self.chiamate[2], ["open", "obsidian://open?vault=second-brain&file=daily/2026-11-03"])

    def test_senza_obsidian_non_apre_e_verify_che_fallisce_si_segnala(self):
        def run(cmd, **kw):
            self.chiamate.append(cmd)
            return Esito(1 if cmd[-1] == "scripts/verify" else 0)
        rc, out = self.vai(run)
        self.assertEqual((rc, out.strip()), (0, "verify: problemi, vedi sopra"))
        self.assertEqual(len(self.chiamate), 2)

    def test_se_claude_fallisce_ci_si_ferma(self):
        rc, out = self.vai(self.lancia({"claude": 3}))
        self.assertEqual((rc, len(self.chiamate), out), (3, 1, ""))

    def test_claude_non_autenticato_avvisa_e_non_prosegue(self):
        def run(cmd, **kw):
            self.chiamate.append(cmd)
            return Esito(1, "Failed to authenticate: OAuth session expired and could not be refreshed\n")
        rc, out = self.vai(run)
        self.assertEqual(rc, 1)
        self.assertIn("Failed to authenticate", out)           # l'output resta nel log di launchd
        self.assertEqual(self.segnalazioni, [(self.vault, "il brief del mattino")])
        self.assertEqual(len(self.chiamate), 1)                # niente verify né Obsidian


if __name__ == "__main__":
    unittest.main()
