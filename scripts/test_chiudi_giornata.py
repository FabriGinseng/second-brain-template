import importlib.util
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("chiudi", Path(__file__).resolve().parent / "chiudi-giornata.py")
chiudi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chiudi)


class Esito:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout = returncode, stdout


class ChiudiGiornata(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault"
        (self.vault / "daily").mkdir(parents=True)
        self.log = Path(self.tmp.name) / "chiudi.log"
        self.lock = Path(self.tmp.name) / "chiudi.lock"
        self.chiamate = []
        self.stati = []        # uscite successive di `git status --porcelain`
        self.attivita = ""
        self.verify_rc = 0
        self.in_stage = ""  # uscita di `git diff --cached --name-only -z`
        self.commit_rc = 0
        self.claude_out = ""
        self.segnalazioni = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_finto(self, cmd, **kw):
        self.chiamate.append(cmd)
        if cmd[0] == "claude":
            return Esito(stdout=self.claude_out)
        if cmd[:2] == ["git", "status"]:
            return Esito(stdout=self.stati.pop(0))
        if cmd[-1].endswith("attivita-progetti.py"):
            return Esito(stdout=self.attivita)
        if cmd[-1].endswith("verify"):
            return Esito(self.verify_rc)
        if cmd[:3] == ["git", "diff", "--cached"]:
            return Esito(stdout=self.in_stage)
        if cmd[:2] == ["git", "commit"]:
            return Esito(self.commit_rc)
        return Esito()

    def vai(self):
        return chiudi.chiudi(self.vault, self.log, self.lock, self.run_finto, datetime(2026, 11, 3, 18, 30),
                              lambda *a: self.segnalazioni.append(a))

    def nomi(self):
        return [c[0] if c[0] == "claude" else " ".join(c[:2]) if c[0] == "git" else "script:" + Path(c[-1]).name for c in self.chiamate]

    def leggi_log(self):
        return self.log.read_text(encoding="utf-8")

    def test_lock_fresco_salta(self):
        self.lock.mkdir()
        self.assertEqual(self.vai(), 0)
        self.assertEqual(self.chiamate, [])
        self.assertIn("chiusura già in corso: salto", self.leggi_log())
        self.assertTrue(self.lock.exists())  # il lock non è nostro: resta

    def test_lock_vecchio_viene_rimosso(self):
        self.lock.mkdir()
        vecchio = time.time() - 31 * 60
        os.utime(self.lock, (vecchio, vecchio))
        self.stati = [""]
        self.vai()
        self.assertIn("niente da aggiornare", self.leggi_log())
        self.assertFalse(self.lock.exists())  # preso e rilasciato

    def test_niente_da_fare(self):
        self.stati = [""]
        self.vai()
        self.assertEqual(self.nomi(), ["script:attivita-progetti.py", "git status"])
        self.assertIn("niente da aggiornare: nessun commit nuovo nei repo e vault pulito", self.leggi_log())

    def test_chiusura_con_commit(self):
        self.attivita = "fse: 3 commit\n"
        self.stati = [" M x", " M STATE.md"]
        self.vai()
        self.assertEqual(self.nomi(), ["script:attivita-progetti.py", "claude", "git status", "script:verify", "git diff", "git add", "git commit"])
        prompt = self.chiamate[1][-1]
        self.assertEqual(prompt, "/chiudi-giornata\nAttività dei repo dall'ultimo STATE:\nfse: 3 commit")
        self.assertEqual(self.chiamate[-1][3:5], ["-m", "chiusura 2026-11-03"])
        self.assertIn("commit: chiusura 2026-11-03", self.leggi_log())

    def test_committa_solo_le_cartelle_dove_si_scrive_in_autonomia(self):
        # ADR-004: inbox, radar, daily, projects, content. Il lavoro di ricerca o i report non finiscono nel commit notturno.
        for cartella in ("projects", "research_notes", "reports"):
            (self.vault / cartella).mkdir()
        self.stati = [" M x", " M STATE.md"]
        self.vai()
        add = next(c for c in self.chiamate if c[:2] == ["git", "add"])
        self.assertEqual(add, ["git", "add", "--", "projects", "daily"])
        self.assertNotIn("-A", add)

    def test_file_gia_in_stage_fuori_dalle_cartelle_autonome_non_si_committano(self):
        # un `git add scripts/x.py` rimasto in stage (commit rifiutato dal pre-commit) finirebbe nel commit «chiusura»
        self.stati = [" M x", " M STATE.md"]
        self.in_stage = "scripts/x.py\0projects/a/STATE.md\0"
        self.vai()
        self.assertNotIn("git commit", self.nomi())
        self.assertNotIn("git add", self.nomi())
        self.assertIn("fuori dalle cartelle autonome", self.leggi_log())

    def test_lo_stato_del_vault_guarda_solo_le_cartelle_autonome(self):
        # senza il filtro un file in research_notes/ farebbe partire il modello ogni sera
        (self.vault / "projects").mkdir()
        self.stati = [""]
        self.attivita = ""
        self.vai()
        status = next(c for c in self.chiamate if c[:2] == ["git", "status"])
        self.assertEqual(status[:3], ["git", "status", "--porcelain"])
        self.assertEqual(status[3:], ["--", "projects", "daily"])
        self.assertIn("niente da aggiornare", self.leggi_log())

    def test_senza_attivita_il_prompt_dice_nessuna(self):
        self.stati = [" M x", ""]
        self.vai()
        self.assertTrue(next(c for c in self.chiamate if c[0] == "claude")[-1].endswith("\nnessuna"))
        self.assertIn("nessuna modifica da committare", self.leggi_log())
        self.assertNotIn("git add", " ".join(self.nomi()))

    def test_verify_che_fallisce_non_committa_e_avvisa_una_volta(self):
        self.verify_rc = 1
        daily = self.vault / "daily" / "2026-11-03.md"
        daily.write_text("# oggi\n", encoding="utf-8")
        for _ in range(2):
            self.stati = [" M x", " M y"]
            self.vai()
        self.assertNotIn("git commit", self.nomi())
        self.assertEqual(daily.read_text(encoding="utf-8").count("Chiusura non committata"), 1)
        self.assertIn("verify non passa", self.leggi_log())
        self.assertFalse(self.lock.exists())

    def test_due_giri_di_fila_fanno_un_solo_commit(self):
        self.attivita = "fse: 3 commit\n"
        self.stati = [" M x", " M STATE.md"]
        self.vai()
        self.attivita = ""      # lo STATE è aggiornato e committato: nessun commit nuovo, albero pulito
        self.stati = [""]
        self.vai()
        self.assertEqual(self.nomi().count("claude"), 1)
        self.assertEqual(self.nomi().count("git commit"), 1)

    def test_commit_rifiutato_dall_hook_non_si_scrive_come_fatto(self):
        self.stati = [" M x", " M y"]
        self.commit_rc = 1
        self.vai()
        self.assertIn("commit bloccato", self.leggi_log())
        self.assertNotIn("commit: chiusura", self.leggi_log())

    def test_claude_non_autenticato_non_committa_e_avvisa(self):
        self.stati = [" M x"]            # lavoro non committato di qualcun altro: non va in un commit "chiusura"
        self.claude_out = "Failed to authenticate: OAuth session expired and could not be refreshed\n"
        self.assertEqual(self.vai(), 0)
        self.assertNotIn("git commit", self.nomi())
        self.assertNotIn("script:verify", self.nomi())
        self.assertEqual(self.segnalazioni, [(self.vault, "la chiusura", datetime(2026, 11, 3, 18, 30))])
        self.assertIn("claude non autenticato", self.leggi_log())
        self.assertIn("Failed to authenticate", self.leggi_log())
        self.assertFalse(self.lock.exists())


if __name__ == "__main__":
    unittest.main()
