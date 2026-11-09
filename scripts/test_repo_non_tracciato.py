#!/usr/bin/env python3
"""Test di repo-non-tracciato.py: silenzioso quando non serve, un messaggio quando il repo non è nel vault."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("repo_non_tracciato", RADICE / "scripts" / "repo-non-tracciato.py")
rnt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rnt)

OGGI = "2026-11-03"
IGNORATI = "# Repo ignorati\n\n| Repo | Scelta | Fino al | Data |\n|---|---|---|---|\n"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


def nuovo_repo(base, nome):
    repo = Path(base) / nome
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("1")
    git(repo, "add", "a")
    git(repo, "commit", "-q", "-m", "x")
    return repo.resolve()


class RepoNonTracciatoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.vault = self.base / "vault"
        (self.vault / "projects" / "progetto-a").mkdir(parents=True)
        (self.vault / "scaffold").mkdir()
        (self.vault / "scaffold" / "ignorati.md").write_text(IGNORATI)
        self.repo = nuovo_repo(self.base, "mio-repo")

    def tearDown(self):
        self._tmp.cleanup()

    def msg(self, cwd=None, escludi=()):
        return rnt.messaggio(cwd or self.repo, self.vault, OGGI, escludi)

    def traccia(self, repo, cartella="progetto-a"):
        stato = self.vault / "projects" / cartella
        stato.mkdir(parents=True, exist_ok=True)
        (stato / "STATE.md").write_text(f"# x\n- **Repo:** {repo}\n")

    def ignorati(self):
        return (self.vault / "scaffold" / "ignorati.md").read_text()

    def test_repo_non_tracciato_da_un_messaggio_corto(self):
        out = self.msg()
        self.assertIn("mio-repo", out)
        self.assertIn(str(self.repo), out)
        self.assertLessEqual(len(out.splitlines()), 3)

    def test_il_si_rimanda_al_file_del_comando_perche_fuori_dal_vault_non_esiste(self):
        # /nuovo-progetto è un comando del vault: in una sessione aperta altrove dà «Unknown skill».
        out = self.msg()
        self.assertIn(str(rnt.VAULT / ".claude" / "commands" / "nuovo-progetto.md"), out)
        self.assertNotIn("usa /nuovo-progetto", out)

    def test_fuori_da_un_repo_git_tace(self):
        fuori = self.base / "cartella-semplice"
        fuori.mkdir()
        self.assertEqual(self.msg(fuori), "")

    def test_repo_tracciato_tace(self):
        self.traccia(self.repo)
        self.assertEqual(self.msg(), "")

    def test_piu_righe_repo_tracciano_tutti_i_repo(self):
        """Regressione: si leggeva solo la prima riga Repo:, e il secondo e il terzo repo del progetto restavano «non tracciati»."""
        app, web = nuovo_repo(self.base, "app"), nuovo_repo(self.base, "web")
        stato = self.vault / "projects" / "progetto-a" / "STATE.md"
        stato.write_text(f"# x\n- **Repo:** {self.repo}\n- **Repo:** {app}\n- **Repo:** {web}\n- **Aggiornato:** {OGGI}\n")
        for repo in (self.repo, app, web):
            self.assertTrue(rnt.tracciato(repo, self.vault), repo)
            self.assertEqual(self.msg(repo), "")
        self.assertFalse(rnt.tracciato(nuovo_repo(self.base, "altro"), self.vault))

    def test_sottocartella_del_repo_conta_come_il_repo(self):
        self.traccia(self.repo)
        sotto = self.repo / "src"
        sotto.mkdir()
        self.assertEqual(self.msg(sotto), "")

    def test_il_vault_stesso_tace(self):
        git(self.vault, "init", "-q", "-b", "main")
        self.assertEqual(self.msg(self.vault), "")

    def test_worktree_riportato_al_repo_principale(self):
        wt = self.base / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "-b", "ramo")
        self.assertIn(str(self.repo), self.msg(wt))
        self.assertNotIn(str(wt), self.msg(wt))
        self.traccia(self.repo)
        self.assertEqual(self.msg(wt), "")

    def test_la_cartella_del_lavoro_non_si_legge(self):
        riservata = self.vault / "projects" / "lavoro" / "x"
        riservata.mkdir(parents=True)
        (riservata / "STATE.md").write_text(f"- **Repo:** {self.repo}\n")
        self.assertIn("mio-repo", self.msg())

    def test_la_home_che_e_un_repo_git_tace(self):
        # Se ~ è un repo git, ogni cartella sotto ~ senza un repo suo ricadrebbe lì.
        sotto = self.repo / "sotto"
        sotto.mkdir()
        self.assertEqual(rnt.messaggio(sotto, self.vault, OGGI, (), casa=self.repo), "")
        self.assertIn("mio-repo", rnt.messaggio(sotto, self.vault, OGGI, (), casa=self.base))

    def test_cartelle_escluse_tacciono(self):
        self.assertEqual(self.msg(escludi=(self.base,)), "")

    def test_le_temporanee_di_sistema_sono_escluse_di_default(self):
        self.assertEqual(rnt.messaggio(self.repo, self.vault, OGGI), "")

    def test_ignora_tace_per_sempre(self):
        rnt.registra(self.repo, self.vault, "ignora", OGGI)
        self.assertEqual(self.msg(), "")
        self.assertIn(str(self.repo), self.ignorati())

    def test_lavoro_salva_solo_l_impronta_e_tace(self):
        rnt.registra(self.repo, self.vault, "lavoro", OGGI)
        testo = self.ignorati()
        self.assertNotIn(str(self.repo), testo)
        self.assertNotIn("mio-repo", testo)
        self.assertIn(rnt.impronta(self.repo), testo)
        self.assertEqual(self.msg(), "")

    def test_non_ora_tace_sette_giorni_poi_richiede(self):
        rnt.registra(self.repo, self.vault, "non-ora", OGGI)
        self.assertIn("2026-11-10", self.ignorati())
        self.assertEqual(rnt.messaggio(self.repo, self.vault, "2026-11-10", ()), "")
        self.assertIn("mio-repo", rnt.messaggio(self.repo, self.vault, "2026-11-11", ()))

    def test_scelta_sconosciuta_e_un_errore(self):
        with self.assertRaises(ValueError):
            rnt.registra(self.repo, self.vault, "forse", OGGI)

    def test_senza_file_degli_ignorati_non_esplode(self):
        (self.vault / "scaffold" / "ignorati.md").unlink()
        self.assertIn("mio-repo", self.msg())

    def test_vault_inesistente_tace(self):
        self.assertEqual(rnt.messaggio(self.repo, self.base / "non-esiste", OGGI, ()), "")

    def test_impronta_stabile_e_senza_il_percorso(self):
        a = rnt.impronta(self.repo)
        self.assertEqual(a, rnt.impronta(self.repo))
        self.assertTrue(a.startswith("sha256:"))
        self.assertNotIn("mio-repo", a)


if __name__ == "__main__":
    unittest.main()
