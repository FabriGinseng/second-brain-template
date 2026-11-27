#!/usr/bin/env python3
"""Scheda Orchestratore: il backend parla con lo smistatore solo lanciando il suo eseguibile (percorso in config.json)."""
import importlib.util
import json
import os
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

    def test_senza_la_chiave_e_409_assente(self):
        (self.vault / "config.json").write_text("{}")
        try:
            stato, r = self.post("/api/orchestratore/config", {"azione": "frontiera", "modello": "x"})
        finally:
            (self.vault / "config.json").write_text(json.dumps({"smistatore": str(self.dir / "smistatore")}))
        self.assertEqual((stato, r), (409, {"errore": "assente"}))


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
