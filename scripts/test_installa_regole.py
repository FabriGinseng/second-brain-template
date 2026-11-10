#!/usr/bin/env python3
"""scripts/installa-regole.py: copia l'hook delle regole in ~/.claude/hooks e lo registra, senza toccare il resto. Home temporanea."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "installa-regole.py"
_spec = importlib.util.spec_from_file_location("installa_regole", SCRIPT)
ir = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ir)

RTK = {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}


class Installa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.sorgente, self.home = base / "sorgente", base / "home"
        self.sorgente.mkdir()
        self.home.mkdir()
        (self.sorgente / "regole.py").write_text("print('hook')\n", encoding="utf-8")
        (self.sorgente / "regole.json").write_text('{"regole": []}\n', encoding="utf-8")
        self.settings = self.home / ".claude" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def voci_regole(self):
        dati = json.loads(self.settings.read_text(encoding="utf-8"))
        return [g for g in dati["hooks"]["PreToolUse"] if any("regole.py" in h["command"] for h in g["hooks"])]

    def test_installa_copia_e_registra(self):
        self.assertTrue(ir.installa(self.sorgente, self.home, applica=False))  # c'è qualcosa da fare
        self.assertFalse(self.settings.exists())  # senza applica non scrive
        ir.installa(self.sorgente, self.home, applica=True)
        for nome in ("regole.py", "regole.json"):
            self.assertEqual((self.home / ".claude" / "hooks" / nome).read_bytes(), (self.sorgente / nome).read_bytes())
        voce = self.voci_regole()
        self.assertEqual(len(voce), 1)
        self.assertEqual(voce[0]["matcher"], "Bash|Edit|Write|MultiEdit|NotebookEdit")
        self.assertIn(str(self.home / ".claude" / "hooks" / "regole.py"), voce[0]["hooks"][0]["command"])
        self.assertTrue(ir.controlla(self.sorgente, self.home))

    def test_idempotente(self):
        ir.installa(self.sorgente, self.home, applica=True)
        self.assertEqual(ir.installa(self.sorgente, self.home, applica=True), [])
        self.assertEqual(len(self.voci_regole()), 1)

    def test_conserva_altri_hook_e_chiavi(self):
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [RTK]}, "permissions": {"defaultMode": "auto"}}), encoding="utf-8")
        ir.installa(self.sorgente, self.home, applica=True)
        dati = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertIn(RTK, dati["hooks"]["PreToolUse"])
        self.assertEqual(dati["permissions"], {"defaultMode": "auto"})
        self.assertTrue(self.settings.with_name("settings.json.bak-second-brain").exists())

    def test_controlla_disallineata(self):
        self.assertFalse(ir.controlla(self.sorgente, self.home))  # non installata
        ir.installa(self.sorgente, self.home, applica=True)
        (self.home / ".claude" / "hooks" / "regole.json").write_text('{"regole": [1]}', encoding="utf-8")
        self.assertFalse(ir.controlla(self.sorgente, self.home))

    def test_su_windows_registra_il_python_che_gira(self):
        # un `python` nudo può essere l'alias dello Store: l'hook uscirebbe con 9009 e Claude Code lascerebbe passare tutto
        comando = ir._comando(self.home, "nt")
        self.assertTrue(comando.startswith('"%s" -I ' % sys.executable), comando)

    @unittest.skipIf(os.name == "nt", "i link simbolici su Windows chiedono privilegi")
    def test_settings_come_link_resta_un_link(self):
        vero = self.home / "dotfiles" / "settings.json"
        vero.parent.mkdir()
        vero.write_text("{}", encoding="utf-8")
        self.settings.parent.mkdir()
        self.settings.symlink_to(vero)
        ir.installa(self.sorgente, self.home, applica=True)
        self.assertTrue(self.settings.is_symlink())
        self.assertIn("regole.py", vero.read_text(encoding="utf-8"))

    def test_settings_illeggibile_non_sovrascrive(self):
        self.settings.parent.mkdir()
        self.settings.write_text("{rotto", encoding="utf-8")
        with self.assertRaises(ValueError):
            ir.installa(self.sorgente, self.home, applica=True)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{rotto")
        self.assertFalse((self.home / ".claude" / "hooks" / "regole.py").exists())


class CopiaInstallata(unittest.TestCase):
    """Sulla macchina vera, in sola lettura: se l'hook è installato deve essere uguale al sorgente, sennò una regola cambiata
    nel vault non varrebbe. Il pre-commit lancia i test quando un commit tocca .claude/ o scripts/."""

    def test_copia_installata_uguale_al_sorgente(self):
        if not (Path.home() / ".claude" / "hooks" / "regole.py").exists():
            self.skipTest("hook delle regole non installato su questa macchina")
        self.assertTrue(ir.controlla(ir.SORGENTE, Path.home()), "copia in ~/.claude/hooks diversa dal sorgente: lancia python3 scripts/installa-regole.py")


if __name__ == "__main__":
    unittest.main()
