#!/usr/bin/env python3
"""Hook di Claude Code del vault: protect_files (PreToolUse) e stop_verify (Stop). Repo temporanei, mai il vault."""
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def lancia(script, payload, root):
    env = {"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, "-I", str(HOOKS / script)], input=json.dumps(payload), capture_output=True, text=True, env=env)


class ProtectFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, percorso):
        return lancia("protect_files.py", {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": percorso}}, self.root)

    def test_blocca_i_guardrail_stessi(self):
        for p in ("scripts/verify", "scripts/hooks/pre-commit", ".claude/hooks/protect_files.py", str(self.root / "scripts" / "hooks" / "pre-commit")):
            r = self.edit(p)
            self.assertEqual(r.returncode, 2, p)
            self.assertIn("guardrail", r.stderr)

    def test_lascia_passare_il_resto_che_e_sotto_le_regole_ask(self):
        # ADR-004: docs/adr, CLAUDE.md e .claude/ sono «con conferma», non «mai»: la conferma resta alla regola ask
        for p in ("daily/oggi.md", "docs/adr/ADR-004-livello-autonomia.md", "CLAUDE.md", ".claude/settings.json", "scripts/verify-altro.py", "/tmp/fuori-dal-vault.txt"):
            self.assertEqual(self.edit(p).returncode, 0, p)

    def test_input_vuoto_o_senza_percorso_non_blocca(self):
        self.assertEqual(lancia("protect_files.py", {"tool_input": {}}, self.root).returncode, 0)

    def test_maiuscole_diverse_sono_lo_stesso_file_su_macos(self):
        # APFS non distingue le maiuscole: SCRIPTS/verify è scripts/verify
        for p in ("SCRIPTS/verify", "scripts/Verify", "scripts/HOOKS/pre-commit", ".claude/Hooks/stop_verify.py"):
            self.assertEqual(self.edit(p).returncode, 2, p)


class NoBypass(unittest.TestCase):
    def comando(self, testo):
        with tempfile.TemporaryDirectory() as d:
            return lancia("no_bypass.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": testo}}, Path(d))

    def test_blocca_ogni_modo_di_saltare_il_pre_commit(self):
        for c in ("git commit --no-verify -m x", "git commit --no-verif -m x", "git commit --no-veri -m x", "git commit --no-v -m x",
                  "git commit -n -m x", "git commit -an", "git commit -qn -m x", "git commit -m x -n", "git commit -a -n",
                  "cd /tmp && git commit -m y -n", "git add . && git commit --no-verify -m z",
                  "git -c core.hooksPath=/dev/null commit -m x", "git config core.hooksPath /dev/null"):
            r = self.comando(c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("pre-commit", r.stderr)

    def test_lascia_passare_i_commit_normali(self):
        for c in ("git commit -m 'add -noise filter'", 'git commit -q -m "fix: x" -m "Co-Authored-By: Claude <n@x>"', "git commit -am 'msg'",
                  "git commit -m x --allow-empty", "git status", "git log -n 5", "git config core.hooksPath scripts/hooks",
                  "git commit -m \"$(cat <<'EOF'\nfix: it's fine\nEOF\n)\"", "ls -n", "echo 'git commit -n'"):
            self.assertEqual(self.comando(c).returncode, 0, c)

    def test_comando_non_analizzabile_non_blocca(self):
        # un hook che si blocca per un apice non chiuso è peggio del deny per sottostringa che resta come seconda difesa
        self.assertEqual(self.comando("git commit -m 'non chiuso").returncode, 0)


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
        env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(self.root), "SB_NO_STOP_VERIFY": "1"}
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
