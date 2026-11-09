#!/usr/bin/env python3
"""Test di attivita(): solo i commit dopo la soglia, su tutti i branch, senza merge."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("attivita_progetti", RADICE / "scripts" / "attivita-progetti.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)


def git(repo, *args, data=None):
    env = {"GIT_AUTHOR_DATE": data, "GIT_COMMITTER_DATE": data} if data else {}
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", **env})


class AttivitaTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a").write_text("1")
        git(self.repo, "add", "a")
        git(self.repo, "commit", "-q", "-m", "vecchio", data="2026-10-20T10:00:00")
        git(self.repo, "switch", "-q", "-c", "feat/x")
        (self.repo / "docs" / "wayfinder").mkdir(parents=True)
        (self.repo / "docs" / "wayfinder" / "t1.md").write_text("ticket")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "nuovo su feat", data="2026-10-26T10:00:00")
        git(self.repo, "switch", "-q", "main")

    def test_solo_dopo_la_soglia_e_su_tutti_i_branch(self):
        soglia = int(__import__("datetime").datetime(2026, 10, 22).timestamp())
        righe = ap.attivita(self.repo, soglia)
        self.assertEqual(len(righe), 2)
        self.assertIn("feat/x: nuovo su feat", righe[0])
        self.assertNotIn("vecchio", "".join(righe))
        self.assertIn("docs/wayfinder/t1.md", righe[1])

    def test_l_output_e_utf8_anche_su_windows(self):
        """Regressione: con -I su Windows l'output andava nella code page ANSI e avvio/chiudi-giornata, che leggono in UTF-8, si rompevano."""
        import shutil
        import sys
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "scripts").mkdir()
            script = Path(shutil.copy(RADICE / "scripts" / "attivita-progetti.py", Path(d) / "scripts"))
            stato = Path(d) / "projects" / "p" / "STATE.md"
            stato.parent.mkdir(parents=True)
            stato.write_text("- **Repo:** %s\n" % self.repo, encoding="utf-8")
            git(self.repo, "commit", "-q", "--allow-empty", "-m", "caffè → fatto")
            r = subprocess.run([sys.executable, "-I", str(script), "--giorni", "1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("caffè → fatto", r.stdout)

    def test_nessun_commit_nuovo_da_lista_vuota(self):
        soglia = int(__import__("datetime").datetime(2026, 10, 27).timestamp())
        self.assertEqual(ap.attivita(self.repo, soglia), [])


class PiuRepoTest(unittest.TestCase):
    """Un progetto con più righe Repo: si leggono tutte; con una sola l'uscita resta quella di prima."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.vault = self.base / "vault"
        (self.vault / "projects" / "negozio").mkdir(parents=True)
        self.repo = {}
        for nome in ("backend", "app", "frontend"):
            repo = self.base / nome
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            git(repo, "commit", "-q", "--allow-empty", "-m", "lavoro su " + nome)
            self.repo[nome] = repo

    def tearDown(self):
        self._tmp.cleanup()

    def esegui(self, *righe_repo):
        import contextlib
        import io
        from unittest import mock
        testo = "# negozio\n" + "".join("- **Repo:** %s\n" % r for r in righe_repo) + "- **Aggiornato:** 2026-11-01\n"
        (self.vault / "projects" / "negozio" / "STATE.md").write_text(testo, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ap, "VAULT", self.vault), mock.patch.object(ap.sys, "argv", ["x", "--giorni", "1"]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ap.main()
        return out.getvalue(), err.getvalue()

    def test_attivita_da_tutti_i_repo_con_il_nome_del_repo(self):
        """Regressione: si leggeva solo la prima riga Repo:, i commit degli altri repo del progetto si perdevano."""
        out, err = self.esegui(*self.repo.values())
        self.assertEqual(err, "")
        righe = out.splitlines()
        self.assertEqual(sum(r.startswith("## ") for r in righe), 1)
        self.assertEqual(righe[0], "## negozio (repo %s)" % ", ".join(str(r) for r in self.repo.values()))
        for nome in self.repo:
            self.assertTrue(any(r.startswith("[%s] - " % nome) and r.endswith("lavoro su " + nome) for r in righe), out)

    def test_un_solo_repo_esce_come_prima(self):
        out, err = self.esegui(self.repo["backend"])
        self.assertEqual(err, "")
        righe = out.splitlines()
        self.assertEqual(len(righe), 2)
        self.assertEqual(righe[0], "## negozio (repo %s)" % self.repo["backend"])
        self.assertRegex(righe[1], r"^- \d{4}-\d\d-\d\d \d\d:\d\d main: lavoro su backend$")

    def test_repo_mancante_o_non_git_saltato_gli_altri_restano(self):
        mancante = self.base / "non-esiste"
        non_git = self.base / "cartella-semplice"
        non_git.mkdir()
        out, err = self.esegui(self.repo["backend"], mancante, non_git, self.repo["app"])
        self.assertIn("lavoro su backend", out)
        self.assertIn("lavoro su app", out)
        self.assertEqual(err.count("repo non leggibile"), 2)

    def test_righe_doppie_lette_una_volta(self):
        out, _ = self.esegui(self.repo["backend"], self.repo["backend"])
        self.assertEqual(out.count("lavoro su backend"), 1)
        self.assertNotIn("[backend]", out)


class SenzaRepoTest(unittest.TestCase):
    def test_repo_nessuno_non_e_un_errore(self):
        """Trovato provando il template: «Repo: nessuno» lanciava git -C nessuno e scriveva un errore nel log."""
        import contextlib
        import io
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            stato = Path(d) / "projects" / "esempio" / "STATE.md"
            stato.parent.mkdir(parents=True)
            stato.write_text("# esempio\n- **Repo:** nessuno\n", encoding="utf-8")
            err = io.StringIO()
            with mock.patch.object(ap, "VAULT", Path(d)), mock.patch.object(ap.sys, "argv", ["x"]), contextlib.redirect_stderr(err):
                ap.main()
            self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
