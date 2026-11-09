#!/usr/bin/env python3
"""Le rotte GET della dashboard rispondono come prima del refactor (tabella delle rotte, JS e CSS in file).

Forma, non dati: stato HTTP, tipo e chiavi di primo livello. Legge il vault vero in sola lettura. `/api/aspetta` non c'è: avvia la lettura del Calendario.
"""
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("server_rotte", RADICE / "scripts" / "dashboard" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

# (tipo, chiavi di primo livello o None se non si controllano)
FORME = {
    "/api/stato": ("dict", None), "/api/piano": ("list", None), "/api/oggi": ("dict", ["conData", "senzaData"]),
    "/api/attesa": ("dict", ["conteggi", "fatto", "voci"]), "/api/moduli": ("dict", ["assistente", "bozze", "modello", "radar", "riservata", "servizi"]),
    "/api/configurazione": ("dict", None), "/api/prestazioni": ("dict", None),
    "/api/esecuzioni": ("dict", ["bozze", "chiudi-giornata", "commit", "controllo-skill", "morning", "pulizia", "radar", "richieste"]),
    "/api/servizi": ("list", None), "/api/post/aperte": ("dict", ["aperte"]), "/api/post": ("list", None),
    "/api/avvii": ("dict", ["job", "macAcceso"]), "/api/bozze": ("dict", ["instagram", "linkedin"]),
}


class RotteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Gestore)
        cls.porta = cls.srv.server_address[1]
        server.HOST_OK.add("127.0.0.1:%d" % cls.porta)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, percorso):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.porta, percorso), timeout=30) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            try:
                return e.code, "", b""
            finally:
                e.close()

    def test_ogni_rotta_json_risponde_con_la_forma_di_prima(self):
        for percorso, (tipo, chiavi) in FORME.items():
            stato, tipo_http, corpo = self.get(percorso)
            self.assertEqual(stato, 200, percorso)
            self.assertIn("application/json", tipo_http, percorso)
            dati = json.loads(corpo)
            self.assertEqual(type(dati).__name__, tipo, percorso)
            if chiavi is not None:
                self.assertEqual(sorted(dati), chiavi, percorso)

    def test_js_e_css_sono_file_serviti_dal_server(self):
        for percorso, tipo in (("/dashboard.js", "javascript"), ("/dashboard.css", "text/css")):
            stato, tipo_http, corpo = self.get(percorso)
            self.assertEqual(stato, 200, percorso)
            self.assertIn(tipo, tipo_http, percorso)
            self.assertGreater(len(corpo), 1000, percorso)
        pagina = self.get("/")[2].decode("utf-8")
        self.assertIn('<script src="/dashboard.js"', pagina)
        self.assertIn('<link rel="stylesheet" href="/dashboard.css"', pagina)
        self.assertNotIn("<script>", pagina)  # niente più codice dentro la pagina
        self.assertNotIn("<style>", pagina)

    def test_i_file_statici_sono_solo_quelli_dell_elenco(self):
        import http.client
        for percorso in ("/dashboard.py", "/server.py", "/../server.py", "/scripts/dashboard/server.py", "/dashboard.js/../server.py"):
            c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
            c.request("GET", percorso)
            self.assertEqual(c.getresponse().status, 404, percorso)
            c.close()

    def test_il_javascript_e_sintatticamente_valido(self):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node non installato")
        r = subprocess.run(["node", "--check", str(RADICE / "scripts" / "dashboard" / "dashboard.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_il_server_non_ripete_json_dumps_in_ogni_rotta(self):
        sorgente = (RADICE / "scripts" / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertLessEqual(sorgente.count('"application/json; charset=utf-8"'), 3, "usa l'helper _json")
        self.assertNotIn('corpo = json.loads(self.rfile.read(lunghezza)) if 0 < lunghezza <= 4096', sorgente, "usa _corpo_json")

    def test_la_pagina_e_una_rotta_sconosciuta(self):
        stato, tipo, corpo = self.get("/")
        self.assertEqual(stato, 200)
        self.assertIn("text/html", tipo)
        self.assertIn(b"<title>Second brain</title>", corpo)
        self.assertEqual(self.get("/api/inesistente")[0], 404)
        self.assertEqual(self.get("/etc/passwd")[0], 404)
        self.assertEqual(self.get("/?v=2")[0], 200)  # un parametro in più non dà 404


if __name__ == "__main__":
    unittest.main()
