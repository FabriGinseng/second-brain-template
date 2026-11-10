#!/usr/bin/env python3
"""Hook Stop del vault (stop_verify). I PreToolUse sono nell'hook unico regole.py: test_regole.py. Repo temporanei, mai il vault."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def lancia(script, payload, root):
    env = dict(os.environ) if os.name == "nt" else {"PATH": "/usr/bin:/bin:/opt/homebrew/bin"}  # su Windows Python e git non partono senza SYSTEMROOT e il PATH vero
    env["CLAUDE_PROJECT_DIR"] = str(root)
    return subprocess.run([sys.executable, "-I", str(HOOKS / script)], input=json.dumps(payload), capture_output=True, text=True, env=env)


class StopVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "scripts").mkdir()
        self.sid = uuid.uuid4().hex

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, codice, testo="STATE troppo lungo"):
        (self.root / "scripts" / "verify").write_text(f"import sys\nprint({testo!r})\nsys.exit({codice})\n", encoding="utf-8")

    def stop(self):
        return lancia("stop_verify.py", {"hook_event_name": "Stop", "session_id": self.sid}, self.root)

    def test_albero_pulito_non_lancia_verify(self):
        self.verify(1)  # se girasse, bloccherebbe
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "base"], check=True)
        self.assertEqual(self.stop().returncode, 0)

    def test_le_run_che_non_devono_correggere_lo_escludono(self):
        # `claude -p` di elabora-richieste, prepara-bozze, morning e modello non possono correggere nulla:
        # un blocco renderebbe la risposta un'altra frase e la richiesta «rifiutata»
        self.verify(1)
        (self.root / "nota.md").write_text("x", encoding="utf-8")
        env = dict(os.environ) if os.name == "nt" else {"PATH": "/usr/bin:/bin"}  # su Windows Python non parte senza SYSTEMROOT
        env.update({"CLAUDE_PROJECT_DIR": str(self.root), "SB_NO_STOP_VERIFY": "1"})
        r = subprocess.run([sys.executable, "-I", str(HOOKS / "stop_verify.py")], input=json.dumps({"session_id": self.sid}), capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_i_job_che_lanciano_claude_senza_poter_correggere_impostano_la_variabile(self):
        scripts = Path(__file__).resolve().parent
        for nome in ("elabora-richieste.py", "prepara-bozze.py", "morning.py", "modello.py"):
            self.assertIn("SB_NO_STOP_VERIFY", (scripts / nome).read_text(encoding="utf-8"), nome)

    def test_verify_che_passa_lascia_chiudere(self):
        self.verify(0)
        (self.root / "nota.md").write_text("x", encoding="utf-8")
        self.assertEqual(self.stop().returncode, 0)

    def test_verify_rosso_blocca_due_volte_poi_lascia_chiudere(self):
        self.verify(1)
        (self.root / "nota.md").write_text("x", encoding="utf-8")
        primo, secondo, terzo = self.stop(), self.stop(), self.stop()
        self.assertEqual((primo.returncode, secondo.returncode, terzo.returncode), (2, 2, 0))
        self.assertIn("STATE troppo lungo", primo.stderr)  # il motivo si legge, così Claude può correggere


if __name__ == "__main__":
    unittest.main()
