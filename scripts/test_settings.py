#!/usr/bin/env python3
"""Controlli sui permessi di Claude Code del vault: le regole che non devono mai saltare stanno nei settings, non nella prosa."""
import importlib.util
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
    def test_le_regole_bash_stanno_nell_hook(self):
        # ADR-012: push, PR, rm e launchctl chiedono, force-push e --no-verify sono negati, decisi da regole.json
        spec = importlib.util.spec_from_file_location("regole", RADICE / ".claude" / "hooks" / "regole.py")
        regole = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(regole)
        elenco = regole.carica_regole(RADICE / ".claude" / "hooks" / "regole.json")
        attese = {"git push": "chiedi", "rm x": "chiedi", "launchctl load x": "chiedi", "gh pr create": "chiedi",
                  "git push --force": "nega", "git push -f": "nega", "git commit --no-verify -m x": "nega", "git commit -n -m x": "nega"}
        for comando, azione in attese.items():
            self.assertEqual(regole.decidi({"tool_name": "Bash", "tool_input": {"command": comando}}, elenco, RADICE, Path.home())[0], azione, comando)

    def test_settings_del_vault_senza_regole_bash(self):
        # le regole Bash per sottostringa si aggiravano (git -C . push) e bloccavano testo innocuo: in deny e ask restano solo quelle
        # sui dati riservati (cartella del vault, _private del template o la cartella scelta dal wizard di setup.py, che la CI lancia prima dei test). Gira anche dentro il template costruito.
        for file in (".claude/settings.json", "template/.claude/settings.json"):
            if (RADICE / file).is_file():
                perm = carica(file)["permissions"]
                bash = {r for r in perm["deny"] + perm["ask"] if r.startswith("Bash(")}
                self.assertLessEqual(bash, {"Bash(*GRAPH_REPORT*)", "Bash(*lavoro*)", "Bash(*_private*)", "Bash(*confidential-notes*)"}, file)

    def test_nessun_allow_che_aggiri_l_hook(self):
        # rtk riscrive git in `rtk git …`: un allow su rtk git o gh pr fa partire push e PR senza conferma (prova del 2026-11-09)
        allow = carica(".claude/settings.json")["permissions"]["allow"] + carica_locale().get("permissions", {}).get("allow", [])
        self.assertFalse([r for r in allow if r.startswith(("Bash(rtk", "Bash(gh pr", "Bash(git push"))], allow)

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
        # PreToolUse lo fa l'hook utente ~/.claude/hooks/regole.py (scripts/installa-regole.py); nel progetto resta lo Stop
        for file in (".claude/settings.json", "template/.claude/settings.json"):
            if not (RADICE / file).is_file():
                continue  # dentro il template costruito c'è solo .claude/settings.json
            hooks = carica(file)["hooks"]
            self.assertNotIn("PreToolUse", hooks, file)
            self.assertTrue(any("stop_verify.py" in h["command"] for v in hooks["Stop"] for h in v["hooks"]), file)
        for nome in ("regole.py", "regole.json", "stop_verify.py"):
            self.assertTrue((RADICE / ".claude" / "hooks" / nome).is_file(), nome)
        for vecchio in ("protect_files.py", "no_bypass.py"):
            self.assertFalse((RADICE / ".claude" / "hooks" / vecchio).exists(), vecchio)

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
