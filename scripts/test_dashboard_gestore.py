#!/usr/bin/env python3
"""Il gestore HTTP della dashboard: solo localhost, Host controllato, POST solo con X-Azione (che obbliga alla preflight), niente CORS.

Un server vero su una porta libera, mai il vault in scrittura: le rotte usate qui non scrivono (403/400 prima di toccare i dati).
"""
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("server_gestore", RADICE / "scripts" / "dashboard" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

# Rotte POST che non devono rispondere a una richiesta senza il header giusto
POST_ROTTE = ("/api/radar/feedback", "/api/assistente/chiedi", "/api/piano/fatto")


class GestoreTest(unittest.TestCase):
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

    def chiedi(self, metodo, percorso, corpo=None, intestazioni=None):
        h = dict(intestazioni or {})
        richiesta = urllib.request.Request("http://127.0.0.1:%d%s" % (self.porta, percorso), data=corpo, headers=h, method=metodo)
        try:
            with urllib.request.urlopen(richiesta) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read(), dict(e.headers)
            finally:
                e.close()

    def test_get_con_host_estraneo_403(self):
        # DNS rebinding: una pagina su un altro nome che punta a 127.0.0.1 manda un Host diverso
        stato, _, _ = self.chiedi("GET", "/api/moduli", intestazioni={"Host": "evil.example"})
        self.assertEqual(stato, 403)

    def test_get_con_host_giusto_200_e_nessun_header_cors(self):
        stato, corpo, h = self.chiedi("GET", "/api/moduli")
        self.assertEqual(stato, 200)
        self.assertIsInstance(json.loads(corpo), dict)
        self.assertNotIn("Access-Control-Allow-Origin", {k.title(): v for k, v in h.items()})

    def test_post_senza_x_azione_403_su_ogni_rotta_provata(self):
        for rotta in POST_ROTTE:
            stato, _, _ = self.chiedi("POST", rotta, b"{}", {"Content-Type": "application/json"})
            self.assertEqual(stato, 403, rotta)

    def test_post_con_host_estraneo_403(self):
        stato, _, _ = self.chiedi("POST", "/api/radar/feedback", b"{}", {"Content-Type": "application/json", "X-Azione": "conferma", "Host": "evil.example"})
        self.assertEqual(stato, 403)

    def test_post_con_x_azione_sbagliato_403(self):
        stato, _, _ = self.chiedi("POST", "/api/radar/feedback", b"{}", {"Content-Type": "application/json", "X-Azione": "si"})
        self.assertEqual(stato, 403)

    def test_corpo_non_json_400(self):
        stato, _, _ = self.chiedi("POST", "/api/radar/feedback", b"questo non e' json", {"Content-Type": "application/json", "X-Azione": "conferma"})
        self.assertEqual(stato, 400)

    def test_preflight_options_non_supportata(self):
        # nessun OPTIONS = nessuna preflight riuscita = un sito esterno non può mandare X-Azione
        stato, _, _ = self.chiedi("OPTIONS", "/api/radar/feedback", intestazioni={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(stato, 501)


if __name__ == "__main__":
    unittest.main()
