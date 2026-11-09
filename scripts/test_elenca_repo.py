#!/usr/bin/env python3
"""Test di elenca-repo.py: trova i repo git sotto le cartelle indicate e dice quali il vault non conosce."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("elenca_repo", RADICE / "scripts" / "elenca-repo.py")
er = importlib.util.module_from_spec(spec)
spec.loader.exec_module(er)

OGGI = "2026-11-04"
IGNORATI = "| Repo | Scelta | Fino al | Data |\n|---|---|---|---|\n"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


def nuovo_repo(base, nome, remote=None):
    repo = Path(base) / nome
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("1")
    git(repo, "add", "a")
    git(repo, "commit", "-q", "-m", "x")
    if remote:
        git(repo, "remote", "add", "origin", remote)
    return repo.resolve()


class ElencaRepoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.scan = self.base / "scan"
        self.scan.mkdir()
        self.vault = self.base / "vault"
        (self.vault / "projects" / "p").mkdir(parents=True)
        (self.vault / "scaffold").mkdir()
        (self.vault / "scaffold" / "ignorati.md").write_text(IGNORATI)

    def tearDown(self):
        self._tmp.cleanup()

    def elenco(self, profondita=3, casa=None):
        return er.elenco([self.scan], self.vault, OGGI, profondita, casa or self.base / "altra-casa")

    def percorsi(self, **kw):
        return [r for g in self.elenco(**kw)["gruppi"] for r in g["repo"]]

    def test_trova_un_repo_non_tracciato(self):
        repo = nuovo_repo(self.scan, "a")
        self.assertEqual(self.percorsi(), [repo])

    def test_non_scende_dentro_un_repo(self):
        repo = nuovo_repo(self.scan, "a")
        nuovo_repo(repo, "sotto")
        self.assertEqual(self.percorsi(), [repo])

    def test_rispetta_la_profondita(self):
        nuovo_repo(self.scan / "x" / "y", "vicino")
        lontano = nuovo_repo(self.scan / "x" / "y" / "z" / "w", "lontano")
        trovati = self.percorsi(profondita=3)
        self.assertEqual(len(trovati), 1)
        self.assertNotIn(lontano, trovati)

    def test_salta_node_modules_claude_worktrees_e_nascoste(self):
        for nome in ("node_modules", ".claude", ".worktrees", ".nascosta"):
            nuovo_repo(self.scan / nome, "r")
        self.assertEqual(self.percorsi(), [])

    def test_i_worktree_non_sono_repo_a_parte(self):
        repo = nuovo_repo(self.scan, "a")
        git(repo, "worktree", "add", "-q", str(self.scan / "wt"), "-b", "ramo")
        self.assertEqual(self.percorsi(), [repo])

    def test_tracciato_va_nel_conteggio_non_nell_elenco(self):
        repo = nuovo_repo(self.scan, "a")
        (self.vault / "projects" / "p" / "STATE.md").write_text(f"- **Repo:** {repo}\n")
        out = self.elenco()
        self.assertEqual(out["gruppi"], [])
        self.assertEqual(out["tracciati"], 1)

    def test_tutte_le_righe_repo_contano_come_tracciate(self):
        a, b = nuovo_repo(self.scan, "a"), nuovo_repo(self.scan, "b")
        (self.vault / "projects" / "p" / "STATE.md").write_text(f"- **Repo:** {a}\n- **Repo:** {b}\n")
        out = self.elenco()
        self.assertEqual(out["gruppi"], [])
        self.assertEqual(out["tracciati"], 2)

    def test_ignorato_e_lavoro_non_compaiono(self):
        a = nuovo_repo(self.scan, "a")
        b = nuovo_repo(self.scan, "b")
        er.rnt.registra(a, self.vault, "ignora", OGGI)
        er.rnt.registra(b, self.vault, "lavoro", OGGI)
        self.assertEqual(self.elenco()["gruppi"], [])

    def test_stesso_remote_raggruppato_con_ignora_suggerito(self):
        url = "git@example.com:utente/x.git"
        nuovo_repo(self.scan, "x1", url)
        nuovo_repo(self.scan, "x2", url)
        nuovo_repo(self.scan, "y", "git@example.com:utente/y.git")
        gruppi = {g["remote"]: g for g in self.elenco()["gruppi"]}
        self.assertEqual(len(gruppi), 2)
        self.assertEqual(len(gruppi[url]["repo"]), 2)

    def test_repo_senza_remote_ha_remote_vuoto(self):
        nuovo_repo(self.scan, "a")
        self.assertEqual(self.elenco()["gruppi"][0]["remote"], "")

    def test_la_home_come_repo_non_e_un_progetto_ma_si_scende_dentro(self):
        casa = nuovo_repo(self.scan, "casa")
        dentro = nuovo_repo(casa, "dentro")
        self.assertEqual(self.percorsi(casa=casa), [dentro])

    def test_testo_numerato_in_un_colpo(self):
        nuovo_repo(self.scan, "a")
        nuovo_repo(self.scan, "b")
        testo = er.formatta(self.elenco())
        self.assertIn("1.", testo)
        self.assertIn("2.", testo)
        self.assertIn("a", testo)

    def test_cartella_inesistente_non_esplode(self):
        out = er.elenco([self.base / "non-esiste"], self.vault, OGGI, 3, self.base / "altra-casa")
        self.assertEqual(out["gruppi"], [])


if __name__ == "__main__":
    unittest.main()
