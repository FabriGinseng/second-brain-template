#!/usr/bin/env python3
"""Scheda Orchestratore: il backend parla con lo smistatore solo lanciando il suo eseguibile (percorso in config.json)."""
import importlib.util
import json
import os
import shlex
import stat
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("orchestratore", RADICE / "scripts" / "dashboard" / "orchestratore.py")
orch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orch)


def eseguibile(cartella: Path, corpo: str) -> Path:
    f = cartella / "smistatore"
    f.write_text("#!/bin/sh\n" + corpo)
    f.chmod(f.stat().st_mode | stat.S_IXUSR)
    return f


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.vault = self.dir / "vault"
        self.vault.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, valore, bom=False):
        (self.vault / "config.json").write_text(("﻿" if bom else "") + json.dumps({"smistatore": str(valore)}), encoding="utf-8")


class Percorso(Base):
    def test_senza_chiave_non_e_attivo(self):
        self.assertIsNone(orch.percorso_smistatore(self.vault))
        (self.vault / "config.json").write_text("{}")
        self.assertIsNone(orch.percorso_smistatore(self.vault))
        self.assertEqual(orch.dati(self.vault), {"attivo": False})

    def test_percorso_non_eseguibile_non_e_attivo(self):
        f = self.dir / "non-eseguibile"
        f.write_text("x")
        self.config(f)
        self.assertIsNone(orch.percorso_smistatore(self.vault))
        self.config(self.dir / "non-esiste")
        self.assertIsNone(orch.percorso_smistatore(self.vault))

    def test_percorso_relativo_non_e_attivo(self):
        eseguibile(self.dir, "echo {}")
        self.config("smistatore")
        self.assertIsNone(orch.percorso_smistatore(self.vault))

    def test_bom_nel_config_json(self):
        f = eseguibile(self.dir, "echo {}")
        self.config(f, bom=True)
        self.assertEqual(orch.percorso_smistatore(self.vault), f)

    def test_config_json_rotto_non_solleva(self):
        (self.vault / "config.json").write_text("{rotto")
        self.assertIsNone(orch.percorso_smistatore(self.vault))


class Chiama(Base):
    def test_chiama_senza_shell(self):
        f = eseguibile(self.dir, 'printf \'{"n": %s}\' "$#"')
        self.config(f)
        strano = "a $(touch /tmp/x-orch) `ls`\n\"b\" «c»"
        r = orch.chiama(self.vault, ["chiedi", strano])
        self.assertEqual(r["n"], 2)
        self.assertFalse(Path("/tmp/x-orch").exists())

    def test_argomenti_arrivano_intatti(self):
        visti = []

        def run(cmd, **kw):
            visti.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        f = eseguibile(self.dir, "true")
        self.config(f)
        orch.chiama(self.vault, ["chiedi", "--x $(y)\nz"], run=run)
        self.assertEqual(visti[0], [str(f), "chiedi", "--x $(y)\nz"])

    def test_timeout_da_errore_timeout(self):
        self.config(eseguibile(self.dir, "sleep 5"))
        with self.assertRaises(orch.OrchestratoreErrore) as c:
            orch.chiama(self.vault, [], timeout=0.2)
        self.assertEqual(c.exception.codice, "timeout")

    def test_uscita_non_json_da_errore_uscita(self):
        self.config(eseguibile(self.dir, "echo Traceback"))
        with self.assertRaises(orch.OrchestratoreErrore) as c:
            orch.chiama(self.vault, [])
        self.assertEqual(c.exception.codice, "uscita")

    def test_uscita_troppo_grande_da_errore_uscita(self):
        self.config(eseguibile(self.dir, "python3 -c \"print('[' + ','.join(['1']*200000) + ']')\""))
        with self.assertRaises(orch.OrchestratoreErrore) as c:
            orch.chiama(self.vault, [])
        self.assertEqual(c.exception.codice, "uscita")

    def test_errore_dello_smistatore_si_inoltra(self):
        self.config(eseguibile(self.dir, "echo '{\"errore\": \"livello enorme\"}'; exit 2"))
        with self.assertRaises(orch.OrchestratoreErrore) as c:
            orch.chiama(self.vault, [])
        self.assertEqual((c.exception.codice, c.exception.testo), ("smistatore", "livello enorme"))

    def test_senza_percorso_da_errore_assente(self):
        with self.assertRaises(orch.OrchestratoreErrore) as c:
            orch.chiama(self.vault, [])
        self.assertEqual(c.exception.codice, "assente")


class Dati(Base):
    def test_dati_attivo_con_config_e_storico(self):
        f = eseguibile(self.dir, 'case "$1" in config) echo \'{"valori": {"frontiera": "opus"}}\';; storico) echo \'[{"tipo_task": "debug"}]\';; esac')
        self.config(f)
        d = orch.dati(self.vault, repo=lambda: {"p/r": Path("/x")})
        self.assertEqual((d["attivo"], d["config"]["valori"]["frontiera"], d["storico"][0]["tipo_task"], d["repo"]), (True, "opus", "debug", ["p/r"]))
        self.assertNotIn("/x", json.dumps(d))

    def test_la_cronologia_chiede_cinquanta_voci(self):
        visti = []

        def run(cmd, **kw):
            visti.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        self.config(eseguibile(self.dir, "true"))
        orch.dati(self.vault, run=run)
        self.assertIn(["--limite", "50"], [c[-2:] for c in visti if "storico" in c])

    def test_un_errore_dello_smistatore_da_attivo_con_errore(self):
        self.config(eseguibile(self.dir, "echo rotto"))
        self.assertEqual(orch.dati(self.vault), {"attivo": True, "errore": "uscita"})


class ConfigArgv(unittest.TestCase):
    def test_azioni_in_tabella_producono_l_argv_giusto(self):
        casi = [
            ({"azione": "tipo", "nome": "ricerca", "descrizione": "cercare cose", "livello": "medio", "modello": "nessuno"},
             ["tipo", "ricerca", "--descrizione", "cercare cose", "--livello", "medio", "--modello", "nessuno"]),
            ({"azione": "tipo", "nome": "debug", "livello": "alto"}, ["tipo", "debug", "--livello", "alto"]),
            ({"azione": "tipo-rimuovi", "nome": "ricerca"}, ["tipo-rimuovi", "ricerca"]),
            ({"azione": "frontiera", "modello": "fable"}, ["frontiera", "fable"]),
            ({"azione": "modello-aperto", "verbo": "aggiungi", "id": "openrouter/x/y"}, ["modello-aperto", "aggiungi", "openrouter/x/y"]),
            ({"azione": "classificatore", "backend": "ollama", "ollama": "qwen3:4b"}, ["classificatore", "--backend", "ollama", "--ollama", "qwen3:4b"]),
        ]
        for corpo, atteso in casi:
            self.assertEqual(orch.config_argv(corpo), atteso, corpo)

    def test_richieste_non_valide_sono_valueerror(self):
        cattivi = [{}, {"azione": "boh"}, {"azione": "riservato", "verbo": "aggiungi", "valore": "/x"},  # i riservati solo da terminale
                   {"azione": "frontiera"}, {"azione": "frontiera", "modello": 5}, {"azione": "frontiera", "modello": ""},
                   {"azione": "frontiera", "modello": "-x"}, {"azione": "tipo", "nome": "a\nb"}, {"azione": "tipo", "nome": "a" * 201},
                   {"azione": "tipo", "nome": "a", "livello": "--descrizione"}, {"azione": "modello-aperto", "verbo": "cancella", "id": "x"},
                   {"azione": "tipo", "nome": "a", "extra": "x"}, {"azione": "tipo", "nome": "a\x00b"}]
        for corpo in cattivi:
            with self.assertRaises(ValueError, msg=str(corpo)):
                orch.config_argv(corpo)


class RotteScrivono(unittest.TestCase):
    """Un server vero sul vault temporaneo con uno smistatore finto che annota gli argomenti ricevuti."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        spec2 = importlib.util.spec_from_file_location("server_orch_post", RADICE / "scripts" / "dashboard" / "server.py")
        cls.server = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(cls.server)
        cls.vault = cls.dir / "vault"
        cls.vault.mkdir()
        cls.annotazioni = cls.dir / "argv.txt"
        script = """for a in "$@"; do printf '%s\\n' "$a"; done > ANNOTAZIONI
case "$3" in enorme) echo '{"errore": "livello enorme in CASA/impostazioni.json"}'; exit 2;; esac
echo '{"valori": {}, "origine": {}}'
""".replace("ANNOTAZIONI", str(cls.annotazioni)).replace("CASA", str(Path.home()))
        eseguibile(cls.dir, script)
        (cls.vault / "config.json").write_text(json.dumps({"smistatore": str(cls.dir / "smistatore")}))
        cls.server.VAULT = cls.vault
        cls.srv = cls.server.ThreadingHTTPServer(("127.0.0.1", 0), cls.server.Gestore)
        cls.porta = cls.srv.server_address[1]
        cls.server.HOST_OK.add("127.0.0.1:%d" % cls.porta)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def post(self, percorso, corpo, intestazioni=None):
        h = {"Content-Type": "application/json", "X-Azione": "conferma", **(intestazioni or {})}
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.porta, percorso), data=json.dumps(corpo).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(r) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, (json.loads(e.read() or b"null") if e.headers.get_content_type() == "application/json" else None)
            finally:
                e.close()

    def test_post_senza_x_azione_e_403(self):
        r = urllib.request.Request("http://127.0.0.1:%d/api/orchestratore/config" % self.porta, data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(r)
        self.assertEqual(c.exception.code, 403)
        c.exception.close()

    def test_config_ok_chiama_lo_smistatore_e_risponde_col_suo_json(self):
        stato, r = self.post("/api/orchestratore/config", {"azione": "frontiera", "modello": "fable"})
        self.assertEqual((stato, r), (200, {"valori": {}, "origine": {}}))
        self.assertEqual(self.annotazioni.read_text().split(), ["config", "frontiera", "fable"])

    def test_azione_sconosciuta_e_riservato_sono_400(self):
        for corpo in ({"azione": "boh"}, {"azione": "riservato", "verbo": "aggiungi", "valore": "/x"}):
            self.assertEqual(self.post("/api/orchestratore/config", corpo)[0], 400)

    def test_errore_dello_smistatore_e_409_senza_il_percorso_di_casa(self):
        stato, r = self.post("/api/orchestratore/config", {"azione": "frontiera", "modello": "enorme"})
        self.assertEqual(stato, 409)
        self.assertIn("livello enorme", r["errore"])
        self.assertNotIn(str(Path.home()), r["errore"])

    def test_classifica_e_avvia_validano_prima_di_tutto(self):
        for rotta in ("/api/orchestratore/classifica", "/api/orchestratore/avvia"):
            for corpo in ({}, {"richiesta": "", "repo": "x"}, {"richiesta": "a" * 4001, "repo": "x"}, {"richiesta": "ok", "repo": 5},
                          {"richiesta": 5, "repo": "x"}, {"richiesta": "ok"}, {"richiesta": "ok", "repo": "x", "tipo": 5}):
                self.assertEqual(self.post(rotta, corpo)[0], 400, (rotta, corpo))
            self.assertEqual(self.post(rotta, {"richiesta": "ok", "repo": "non/esiste"})[0], 404, rotta)

    def test_senza_la_chiave_e_409_assente(self):
        (self.vault / "config.json").write_text("{}")
        try:
            stato, r = self.post("/api/orchestratore/config", {"azione": "frontiera", "modello": "x"})
        finally:
            (self.vault / "config.json").write_text(json.dumps({"smistatore": str(self.dir / "smistatore")}))
        self.assertEqual((stato, r), (409, {"errore": "assente"}))


DECISIONE = {"esito": "classificato", "tipo": "ripetitivo", "livello": "basso", "motivo": "", "incerto": False, "backend": "openrouter",
             "costo": 0.0001, "durata": 0.5, "riservato": False, "modello": "m-basso", "esecutore": "paseo"}
ALTO = {**DECISIONE, "tipo": "debug", "livello": "alto", "modello": "opus", "esecutore": "sessione"}


class Avvia(Base):
    def setUp(self):
        super().setUp()
        self.config(eseguibile(self.dir, "true"))
        self.repo_dir = self.dir / "progetto"
        self.repo_dir.mkdir()
        self.elenco = {"p/r": self.repo_dir}
        self.chiamate, self.lanci, self.aperture = [], [], []
        self.decisione = dict(DECISIONE)
        self.avvii = self.dir / "avvii"
        self.t = 100.0
        orch.ULTIMI.clear()

    def finto(self, cmd, **kw):
        self.chiamate.append(cmd)
        if "--solo-classifica" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(self.decisione), stderr="")
        self.aperture.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def lancia(self, cmd, **kw):
        self.lanci.append((cmd, kw))

    def vai(self, richiesta="rinomina x", repo="p/r", **kw):
        return orch.avvia(self.vault, richiesta, repo, self.elenco, run=self.finto, lancia=self.lancia, cartella_avvii=self.avvii,
                          adesso=lambda: self.t, sistema=kw.pop("sistema", "darwin"), **kw)

    def test_il_testo_arriva_intatto_come_argomento(self):
        strano = "rinomina \"a\" «b» $(touch /tmp/x-orch2) `ls`\nriga due"
        self.vai(strano)
        solo = self.chiamate[0]
        self.assertEqual(solo[solo.index("chiedi") + 1], strano)
        self.assertEqual(self.lanci[0][0][self.lanci[0][0].index("chiedi") + 1], strano)
        self.assertFalse(Path("/tmp/x-orch2").exists())

    def test_richiesta_con_trattino_non_diventa_un_flag(self):
        self.vai("--dangerously-skip-permissions")
        for cmd in (self.chiamate[0], self.lanci[0][0]):
            testo = cmd[cmd.index("chiedi") + 1]
            self.assertFalse(testo.startswith("-"))
            self.assertEqual(testo.strip(), "--dangerously-skip-permissions")

    def test_richiesta_vuota_o_oltre_4000_o_con_byte_nulli_e_valueerror(self):
        for r in ("", "  \n", "a" * 4001, "a\x00b", None, 5):
            with self.assertRaises(ValueError):
                self.vai(r)
        self.assertEqual((self.chiamate, self.lanci), ([], []))

    def test_repo_fuori_elenco_e_lookuperror(self):
        for nome in ("altro/repo", "../..", "/etc", "", None):
            with self.assertRaises((LookupError, ValueError)):
                self.vai(repo=nome)
        self.assertEqual((self.chiamate, self.lanci), ([], []))

    def test_il_livello_del_browser_non_vale(self):
        self.decisione = {**ALTO, "riservato": True}
        r = self.vai(livello="basso")
        self.assertIn("--livello", self.chiamate[0])  # lo smistatore riceve la richiesta del browser...
        self.assertEqual((r["esecutore"], r["livello"], self.lanci), ("sessione", "alto", []))  # ...e decide lui: riservato, quindi alto

    def test_basso_parte_staccato_senza_shell(self):
        r = self.vai(tipo="ripetitivo", prima="debug")
        cmd, kw = self.lanci[0]
        self.assertIsInstance(cmd, list)
        self.assertEqual((cmd[0], cmd[cmd.index("--repo") + 1], cmd[cmd.index("--tipo") + 1], cmd[cmd.index("--prima") + 1]),
                         (str(self.dir / "smistatore"), str(self.repo_dir), "ripetitivo", "debug"))
        self.assertNotIn("--solo-classifica", cmd)
        self.assertTrue(kw["start_new_session"])
        self.assertFalse(kw.get("shell"))
        self.assertEqual((r["ok"], r["esecutore"], r["modello"]), (True, "paseo", "m-basso"))

    def test_alto_apre_il_terminale_con_lo_smistatore_non_con_claude(self):
        self.decisione = dict(ALTO)
        r = self.vai("perché si blocca?", prima="ripetitivo")
        self.assertEqual(self.lanci, [])
        cmd, _ = self.aperture[0]
        self.assertEqual(cmd[:3], ["/usr/bin/open", "-a", "Terminal"])
        comando = Path(cmd[3])
        testo_comando = comando.read_text()
        smistatore = str(self.dir / "smistatore")
        # un solo motore: è lo smistatore a lanciare claude, e così scrive la sua riga di registro
        self.assertIn("exec %s chiedi \"$(cat " % shlex.quote(smistatore), testo_comando)
        self.assertIn("--repo %s --tipo debug --prima ripetitivo" % shlex.quote(str(self.repo_dir)), testo_comando)
        self.assertNotIn("claude", testo_comando)
        self.assertNotIn("perché", testo_comando)  # il testo sta nel file del prompt, non nel comando
        prompt = comando.with_suffix(".txt")
        self.assertEqual(prompt.read_text(), "perché si blocca?")
        self.assertEqual(oct(prompt.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(comando.stat().st_mode & 0o777), "0o700")
        self.assertEqual((r["esecutore"], r["modello"]), ("sessione", "opus"))

    def test_tipo_e_prima_con_caratteri_di_shell_sono_quotati(self):
        self.decisione = {**ALTO, "tipo": "x; touch /tmp/x-orch3"}
        self.vai(prima="y $(touch /tmp/x-orch4)")
        testo = Path(self.aperture[0][0][3]).read_text()
        self.assertIn("'x; touch /tmp/x-orch3'", testo)
        self.assertIn("'y $(touch /tmp/x-orch4)'", testo)

    def test_senza_tipo_il_terminale_porta_il_livello(self):
        self.decisione = {**ALTO, "tipo": None}
        self.vai()
        self.assertIn("--livello alto", Path(self.aperture[0][0][3]).read_text())

    def test_doppio_clic_lancia_una_volta(self):
        self.vai()
        with self.assertRaises(RuntimeError) as c:
            self.vai()
        self.assertEqual(str(c.exception), "ripetuto")
        self.assertEqual(len(self.lanci), 1)
        self.t += 11
        self.vai()
        self.assertEqual(len(self.lanci), 2)

    def test_non_macos_e_notimplemented(self):
        with self.assertRaises(NotImplementedError):
            self.vai(sistema="win32")
        self.assertEqual((self.chiamate, self.lanci), ([], []))

    def test_apertura_fallita_e_un_errore_a_codice_fisso(self):
        self.decisione = dict(ALTO)

        def run(cmd, **kw):
            if "--solo-classifica" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(ALTO), stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
        with self.assertRaises(RuntimeError) as c:
            orch.avvia(self.vault, "x", "p/r", self.elenco, run=run, lancia=self.lancia, cartella_avvii=self.avvii, adesso=lambda: 1.0, sistema="darwin")
        self.assertEqual(str(c.exception), "apertura")

    def test_classifica_non_lancia_niente(self):
        r = orch.classifica(self.vault, "rinomina x", "p/r", self.elenco, run=self.finto)
        self.assertEqual((r["tipo"], r["livello"], r["esecutore"]), ("ripetitivo", "basso", "paseo"))
        self.assertEqual((len(self.chiamate), self.lanci, self.aperture), (1, [], []))
        self.assertIn("--solo-classifica", self.chiamate[0])

    def test_il_file_del_prompt_non_si_sovrascrive(self):
        self.decisione = dict(ALTO)
        self.vai("uno")
        self.t += 11
        self.vai("uno")
        self.assertEqual(len(list(self.avvii.glob("*.txt"))), 2)


class ElencoRepo(unittest.TestCase):
    def test_solo_i_repo_avviabili_mai_il_lavoro_ne_un_link_verso_il_lavoro(self):
        spec2 = importlib.util.spec_from_file_location("server_orch_repo", RADICE / "scripts" / "dashboard" / "server.py")
        server = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(server)
        with tempfile.TemporaryDirectory() as t:
            base = Path(t).resolve()
            vault = base / "vault"
            (vault / "projects" / "buono").mkdir(parents=True)
            (vault / "projects" / "lavoro" / "segreto").mkdir(parents=True)
            buono, nel_lavoro = base / "repo-ok", vault / "projects" / "lavoro" / "segreto"
            buono.mkdir()
            link = base / "link-al-lavoro"
            link.symlink_to(nel_lavoro)
            (vault / "projects" / "INDEX.md").write_text("| Progetto | A | B | C | D |\n| [[projects/buono/STATE\\|buono]] | x | y | z | alta |\n")
            (vault / "projects" / "buono" / "STATE.md").write_text("# buono\n- **Repo:** %s\n- **Repo:** %s\n" % (buono, link))
            elenco = server.orchestratore_repo(vault)
            self.assertEqual(sorted(str(v) for v in elenco.values()), [str(buono)])
            self.assertTrue(all(k.startswith("buono/") for k in elenco))

    def test_con_config_json_illeggibile_l_elenco_e_vuoto(self):
        spec2 = importlib.util.spec_from_file_location("server_orch_repo2", RADICE / "scripts" / "dashboard" / "server.py")
        server = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(server)
        with tempfile.TemporaryDirectory() as t:
            vault = Path(t)
            (vault / "projects").mkdir()
            (vault / "config.json").write_text("{rotto")
            self.assertEqual(server.orchestratore_repo(vault), {})


class Rotta(unittest.TestCase):
    def test_rotta_get_risponde_attivo_falso_senza_chiave(self):
        spec2 = importlib.util.spec_from_file_location("server_orch", RADICE / "scripts" / "dashboard" / "server.py")
        server = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(server)
        with tempfile.TemporaryDirectory() as t:
            server.VAULT = Path(t)
            self.assertEqual(server.ROTTE_JSON["/api/orchestratore"](), {"attivo": False})


if __name__ == "__main__":
    unittest.main()
