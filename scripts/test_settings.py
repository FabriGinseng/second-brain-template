#!/usr/bin/env python3
"""Controlli sui permessi di Claude Code del vault: le regole che non devono mai saltare stanno nei settings, non nella prosa."""
import json
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent


def carica(percorso):
    return json.loads((RADICE / percorso).read_text(encoding="utf-8"))


def carica_locale():
    # settings.local.json è ignorato da git: su un clone nuovo non c'è
    try:
        return carica(".claude/settings.local.json")
    except FileNotFoundError:
        return {}


class SettingsTest(unittest.TestCase):
    def test_deny_no_verify(self):
        deny = carica(".claude/settings.json")["permissions"]["deny"]
        self.assertIn("Bash(git commit *--no-verify*)", deny)
        self.assertIn("Bash(git commit -n*)", deny)

    def test_push_e_azioni_esterne_chiedono_conferma_il_force_push_e_negato(self):
        perm = carica(".claude/settings.json")["permissions"]
        for regola in ("Bash(git push *)", "Bash(rm *)", "Bash(launchctl *)", "Bash(gh pr create *)"):
            self.assertIn(regola, perm["ask"])
            self.assertNotIn(regola, perm["allow"] + perm["deny"])
        self.assertIn("Bash(git push *--force*)", perm["deny"])
        self.assertIn("Bash(git push -f*)", perm["deny"])

    def test_bypass_disabilitato(self):
        self.assertEqual(carica(".claude/settings.json")["permissions"].get("disableBypassPermissionsMode"), "disable")

    def test_nessun_mcp_approvato_in_automatico(self):
        self.assertIsNot(carica_locale().get("enableAllProjectMcpServers"), True)

    def test_allow_senza_interprete_aperto_ne_launchctl(self):
        allow = carica(".claude/settings.json")["permissions"]["allow"] + carica_locale().get("permissions", {}).get("allow", [])
        self.assertNotIn("Bash(python3)", allow)
        self.assertFalse([r for r in allow if r.startswith("Bash(launchctl")], allow)

    def test_web_non_in_allow(self):
        # senza la voce in allow, una run non presidiata (dontAsk) nega il web e una sessione interattiva chiede conferma
        allow = carica(".claude/settings.json")["permissions"]["allow"]
        self.assertNotIn("WebFetch", allow)
        self.assertNotIn("WebSearch", allow)

    def test_hook_registrati_e_i_file_esistono(self):
        hooks = carica(".claude/settings.json")["hooks"]
        per_matcher = {v["matcher"]: [h["command"] for h in v["hooks"]] for v in hooks["PreToolUse"]}
        self.assertTrue(any("protect_files.py" in c for c in per_matcher["Edit|Write"]))
        self.assertTrue(any("no_bypass.py" in c for c in per_matcher["Bash"]))
        self.assertTrue(any("stop_verify.py" in h["command"] for v in hooks["Stop"] for h in v["hooks"]))
        for nome in ("protect_files.py", "no_bypass.py", "stop_verify.py"):
            self.assertTrue((RADICE / ".claude" / "hooks" / nome).is_file(), nome)

    def test_agenti_senza_agent_tool(self):
        # i subagenti non ne lanciano altri: lo garantisce l'elenco `tools`, non la piattaforma
        agenti = sorted((RADICE / ".claude" / "agents").glob("*.md"))
        self.assertTrue(agenti)
        for f in agenti:
            tools = next((r for r in f.read_text(encoding="utf-8").splitlines() if r.startswith("tools:")), None)
            self.assertIsNotNone(tools, f.name)
            self.assertNotIn("Agent", [t.strip() for t in tools[6:].split(",")], f.name)

    def test_code_reviewer_e_a_sola_lettura(self):
        testo = (RADICE / ".claude" / "agents" / "code-reviewer.md").read_text(encoding="utf-8")
        tools = next(r for r in testo.splitlines() if r.startswith("tools:"))
        for scrittura in ("Write", "Edit", "NotebookEdit"):
            self.assertNotIn(scrittura, tools)
        self.assertIn("Assumi che il diff contenga almeno un bug", testo)


if __name__ == "__main__":
    unittest.main()
