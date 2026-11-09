"""Il pre-commit blocca un segreto finto e lascia passare un file pulito (repo temporaneo, mai il vault)."""
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "hooks" / "pre-commit"


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, **kw)


@unittest.skipUnless(shutil.which("gitleaks"), "gitleaks non installato")
class HookGitleaks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q")
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("core.hooksPath", str(HOOK.parent))):
            git(self.repo, "config", k, v)

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, nome, testo):
        (self.repo / nome).write_text(testo, encoding="utf-8")
        git(self.repo, "add", nome)
        return git(self.repo, "commit", "-q", "-m", "prova")

    def test_segreto_finto_blocca_il_commit(self):
        finto = "ghp_" + "".join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=36))  # costruito qui, mai nel file
        r = self.commit("config.txt", f"token = {finto}\n")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(finto, r.stdout + r.stderr)  # --redact: il segreto non finisce nell'output
        self.assertNotEqual(git(self.repo, "rev-parse", "--verify", "HEAD").returncode, 0)  # nessun commit creato

    def test_file_pulito_passa(self):
        r = self.commit("nota.md", "# Ciao\nNiente di segreto.\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def scrivi(self, nome, testo):
        p = self.repo / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(testo, encoding="utf-8")
        git(self.repo, "add", nome)

    def test_verify_che_fallisce_blocca_il_commit(self):
        self.scrivi("scripts/verify", "import sys\nprint('STATE troppo lungo')\nsys.exit(1)\n")
        self.scrivi("nota.md", "# Ciao\n")
        r = git(self.repo, "commit", "-q", "-m", "prova")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("scripts/verify", r.stdout + r.stderr)
        self.assertIn("STATE troppo lungo", r.stdout + r.stderr)  # il motivo si legge, non solo l'esito

    def test_verify_che_passa_lascia_passare(self):
        self.scrivi("scripts/verify", "print('OK')\n")
        self.scrivi("nota.md", "# Ciao\n")
        r = git(self.repo, "commit", "-q", "-m", "prova")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_i_test_girano_solo_se_il_commit_tocca_il_codice(self):
        # La chiusura delle 18:30 mette in stage solo projects/daily/...: un test rosso non deve fermarla.
        self.scrivi("scripts/verify", "print('OK')\n")
        self.scrivi("scripts/test_falso.py", "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('rosso')\n")
        git(self.repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "base")
        self.scrivi("daily/oggi.md", "# oggi\n")
        r = git(self.repo, "commit", "-q", "-m", "solo note")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.scrivi("scripts/modulo.py", "x = 1\n")
        r = git(self.repo, "commit", "-q", "-m", "codice")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("test", r.stdout + r.stderr)
        self.assertIn("rosso", r.stdout + r.stderr)

    def prepara_codice_rosso(self):
        self.scrivi("scripts/verify", "print('OK')\n")
        self.scrivi("scripts/test_falso.py", "import unittest\nimport time\nclass T(unittest.TestCase):\n    def test_x(self):\n        time.sleep(float(__import__('os').environ.get('LENTO', '0')))\n        self.fail('rosso')\n")
        git(self.repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "base")

    def test_nome_con_accento_conta_come_codice(self):
        # senza -z git scrive "scripts/citt\303\240.py" tra virgolette e il prefisso scripts/ non si riconosce
        self.prepara_codice_rosso()
        self.scrivi("scripts/città.py", "x = 1\n")
        r = git(self.repo, "commit", "-q", "-m", "codice")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("rosso", r.stdout + r.stderr)

    def test_un_test_bloccato_non_ferma_il_commit_per_sempre(self):
        self.prepara_codice_rosso()
        self.scrivi("scripts/modulo.py", "x = 1\n")
        env = {**os.environ, "SB_PRE_COMMIT_TIMEOUT": "1", "LENTO": "20"}
        r = git(self.repo, "commit", "-q", "-m", "codice", env=env, timeout=30)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tempo", r.stdout + r.stderr)

    def test_senza_gitleaks_blocca(self):
        vuota = Path(self.tmp.name) / "vuota"
        vuota.mkdir()
        r = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env={"PATH": str(vuota)})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gitleaks non trovato", r.stderr)


if __name__ == "__main__":
    unittest.main()
