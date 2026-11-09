"""Cose che si sono rotte su Windows provando il template: comandi solo macOS e separatore del PATH."""
import importlib.util
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("server", RADICE / "scripts" / "dashboard" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class PrestazioniTest(unittest.TestCase):
    def test_memoria_fuori_da_macos_non_chiama_sysctl(self):
        with mock.patch.object(server.subprocess, "run", side_effect=AssertionError("sysctl non esiste qui")):
            self.assertEqual(server.memoria("win32", ram=lambda: 31.6), {"totaleGb": 31.6, "swapUsatoMb": None})

    def test_memoria_con_ram_sconosciuta(self):
        self.assertEqual(server.memoria("linux", ram=lambda: None), {"totaleGb": None, "swapUsatoMb": None})

    def test_processi_ollama_senza_ps_e_una_lista_vuota(self):
        with mock.patch.object(server.subprocess, "run", side_effect=FileNotFoundError("ps")):
            self.assertEqual(server.processi_ollama(), [])

    def test_prestazioni_non_cade_senza_comandi_di_macos(self):
        with mock.patch.object(server.subprocess, "run", side_effect=FileNotFoundError("sysctl")):
            self.assertEqual(server.memoria("linux", ram=lambda: 8.0)["swapUsatoMb"], None)
            self.assertEqual(server.processi_ollama(), [])


class AmbienteTest(unittest.TestCase):
    def test_il_path_usa_il_separatore_del_sistema(self):
        with mock.patch.object(server.os, "pathsep", ";"):
            percorso = server.ambiente_azione()["PATH"]
        self.assertTrue(percorso.startswith(str(Path.home() / ".local" / "bin") + ";/opt/homebrew/bin;/usr/local/bin;"), percorso[:120])


class PiuRepoTest(unittest.TestCase):
    """Un progetto con più righe Repo: la scheda somma i repo; con una sola riga resta com'era."""

    @staticmethod
    def finta_attivita(repo):
        n = {"/x/backend": 2, "/x/app": 1}.get(repo)
        if n is None:
            return None
        return {"ultimoCommit": 100 * n, "giorni": [{"data": "2026-11-0%d" % d, "n": n} for d in (1, 2)], "branch": "main",
                "nonCommittate": n, "commit": [{"quando": 100 * n, "ramo": "main", "messaggio": repo}]}

    def test_tutte_le_righe_repo(self):
        self.assertEqual(server.repo_di("- **Repo:** /x/backend\n- **Repo:** /x/app\n- **Repo:** /x/backend\n"), ["/x/backend", "/x/app"])

    def test_attivita_sommata_con_il_nome_del_repo(self):
        with mock.patch.object(server, "attivita", self.finta_attivita):
            a = server.attivita_progetto(["/x/backend", "/x/app", "/x/non-esiste"])
        self.assertEqual(a["ultimoCommit"], 200)
        self.assertEqual([g["n"] for g in a["giorni"]], [3, 3])
        self.assertEqual(a["nonCommittate"], 3)
        self.assertEqual(a["branch"], "backend: main · app: main")
        self.assertEqual([c["ramo"] for c in a["commit"]], ["backend main", "app main"])

    def test_un_solo_repo_come_prima(self):
        with mock.patch.object(server, "attivita", self.finta_attivita):
            self.assertEqual(server.attivita_progetto(["/x/backend"]), self.finta_attivita("/x/backend"))
            self.assertIsNone(server.attivita_progetto([]))
            self.assertIsNone(server.attivita_progetto(["nessuno"]))

    def test_immagini_solo_dalle_cartelle_docs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "projects" / "negozio").mkdir(parents=True)
            (vault / "projects" / "INDEX.md").write_text("| [[projects/negozio/STATE\\|negozio]] | x | y | z | 2026-11-01 |\n")
            (vault / "projects" / "negozio" / "STATE.md").write_text("- **Repo:** /x/backend\n- **Repo:** /x/app\n")
            with mock.patch.object(server, "VAULT", vault):
                progetti = server._progetti_con_repo()
        self.assertEqual(progetti, {"negozio": [Path("/x/backend/docs"), Path("/x/app/docs")]})


if __name__ == "__main__":
    unittest.main()
