import importlib.util
import json
import plistlib
import tempfile
import unittest
import xml.dom.minidom
from pathlib import Path, PurePosixPath, PureWindowsPath

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("install_jobs", RADICE / "install_jobs.py")
ij = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ij)

def perc(*parti):
    """Percorso nel formato del sistema su cui gira il test (con / su macOS e Linux, con \\ su Windows)."""
    return str(Path(*parti))


CTX = {"vault": Path("/srv/vault dir"), "home": Path("/srv/u"), "python": "/srv/py/python3", "log": Path("/srv/u/logs"), "etichetta": "second-brain"}
# systemd esiste solo su Linux: i suoi test usano percorsi POSIX anche quando girano su Windows
CTX_POSIX = {**CTX, "vault": PurePosixPath("/srv/vault dir"), "home": PurePosixPath("/srv/u"), "log": PurePosixPath("/srv/u/logs")}
FERIALE = {"description": "d", "command": ["{python}", "-I", "{vault}/scripts/x.py"], "days": [1, 5], "time": "08:05", "at_login": True}
SERVIZIO = {"description": "s", "command": ["{python}", "{vault}/scripts/server.py"], "service": True}
DOMENICA = {"description": "w", "command": ["{python}", "x.py"], "days": [7], "time": "23:00"}


class SelezioneTest(unittest.TestCase):
    JOBS = {"a": {"command": ["x"]}, "b": {"command": ["x"], "default": False}, "c": {"command": ["x"], "os": ["macos"]}}

    def test_di_default_solo_i_job_per_questo_sistema_e_non_facoltativi(self):
        self.assertEqual(list(ij.seleziona(self.JOBS, "linux")), ["a"])
        self.assertEqual(list(ij.seleziona(self.JOBS, "macos")), ["a", "c"])
        self.assertEqual(list(ij.seleziona(self.JOBS, "linux", tutti=True)), ["a", "b"])
        self.assertEqual(list(ij.seleziona(self.JOBS, "linux", solo=["b"])), ["b"])  # chiamato per nome: si installa anche se facoltativo
        self.assertEqual(list(ij.seleziona(self.JOBS, "linux", solo=["c"])), [])  # ma non su un sistema sbagliato


class LaunchdTest(unittest.TestCase):
    def test_giorni_orario_login_e_caffeinate(self):
        p = ij.piano_launchd("m", FERIALE, CTX)
        plist = plistlib.loads(p["file"][0][1])
        self.assertEqual(plist["Label"], "second-brain.m")
        self.assertEqual(plist["StartCalendarInterval"], [{"Weekday": 1, "Hour": 8, "Minute": 5}, {"Weekday": 5, "Hour": 8, "Minute": 5}])
        self.assertTrue(plist["RunAtLoad"])
        self.assertEqual(plist["ProgramArguments"][:2], ["/usr/bin/caffeinate", "-i"])
        self.assertEqual(Path(plist["ProgramArguments"][-1]), Path("/srv/vault dir/scripts/x.py"))  # Path ignora la differenza tra / e \

    def test_la_domenica_per_launchd_e_zero_e_un_servizio_resta_acceso(self):
        self.assertEqual(plistlib.loads(ij.piano_launchd("w", DOMENICA, CTX)["file"][0][1])["StartCalendarInterval"][0]["Weekday"], 0)
        s = plistlib.loads(ij.piano_launchd("s", SERVIZIO, CTX)["file"][0][1])
        self.assertTrue(s["KeepAlive"] and s["RunAtLoad"])
        self.assertNotIn("/usr/bin/caffeinate", s["ProgramArguments"])
        self.assertNotIn("StartCalendarInterval", s)


class SystemdTest(unittest.TestCase):
    def test_timer_persistente_e_servizio_al_login(self):
        p = ij.piano_systemd("m", FERIALE, CTX_POSIX)
        nomi = dict(p["file"])
        self.assertIn("OnCalendar=Mon,Fri 08:05:00", nomi["second-brain.m.timer"])
        self.assertIn("Persistent=true", nomi["second-brain.m.timer"])
        self.assertIn("WantedBy=default.target", nomi["second-brain.m.service"])
        self.assertIn('ExecStart=%s -I "%s/scripts/x.py"' % (CTX_POSIX["python"], CTX_POSIX["vault"]), nomi["second-brain.m.service"])  # percorso con spazio: tra virgolette
        self.assertIn(["systemctl", "--user", "enable", "--now", "second-brain.m.timer"], p["avvia"])

    def test_servizio_senza_timer_e_domenica(self):
        s = ij.piano_systemd("s", SERVIZIO, CTX_POSIX)
        self.assertEqual([n for n, _ in s["file"]], ["second-brain.s.service"])
        self.assertIn("Restart=on-failure", s["file"][0][1])
        self.assertIn("OnCalendar=Sun 23:00:00", dict(ij.piano_systemd("w", DOMENICA, CTX_POSIX)["file"])["second-brain.w.timer"])


class WindowsTest(unittest.TestCase):
    def xml(self, job):
        p = ij.piano_windows("m", job, CTX)
        testo = p["file"][0][1].decode("utf-16")
        xml.dom.minidom.parseString(testo.split("?>", 1)[1])  # ben formato
        return testo, p

    def test_giorni_recupero_dopo_il_mancato_avvio_e_login(self):
        testo, p = self.xml(FERIALE)
        self.assertIn("<DaysOfWeek><Monday /><Friday /></DaysOfWeek>", testo)
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", testo)
        self.assertIn("<LogonTrigger>", testo)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", testo)
        self.assertEqual(p["avvia"][0][:3], ["schtasks", "/create", "/tn"])

    def test_l_accesso_vale_per_il_tuo_utente_cosi_non_serve_l_amministratore(self):
        """Trovato provando su Windows: un LogonTrigger senza UserId chiede i diritti di amministratore."""
        p = ij.piano_windows("m", FERIALE, {**CTX, "utente": "PC\\ada & co"})
        testo = p["file"][0][1].decode("utf-16")
        self.assertIn("<UserId>PC\\ada &amp; co</UserId></LogonTrigger>", testo)
        self.assertNotIn("<LogonTrigger><Enabled>true</Enabled></LogonTrigger>", self.xml(FERIALE)[0])

    def test_i_percorsi_con_spazi_stanno_tra_virgolette_e_il_log_e_rediretto(self):
        testo, _ = self.xml(FERIALE)
        self.assertIn('"%s"' % PureWindowsPath("/srv/vault dir/scripts/x.py"), testo)  # su Windows tutti i separatori sono \, su qualunque host
        self.assertIn("&gt;&gt;", testo)

    def test_nessuna_finestra_di_console_visibile(self):
        """Regressione: con cmd.exe come comando ogni avvio apriva una finestra CMD vuota sul desktop."""
        testo, _ = self.xml(FERIALE)
        self.assertIn("<Command>conhost.exe</Command><Arguments>--headless cmd.exe /c ", testo)

    def test_morning_del_template_gira_su_windows_feriali_alle_8_e_all_accesso(self):
        """Regressione: morning era solo macOS ("os": ["macos"]) e install_jobs su Windows non lo registrava."""
        jobs = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
        self.assertIn("morning", ij.seleziona(jobs, "windows"))
        self.assertIn("morning", ij.seleziona(jobs, "macos"))
        testo, _ = self.xml(jobs["morning"])
        self.assertIn("<StartBoundary>2026-01-01T08:00:00</StartBoundary>", testo)
        self.assertIn("<DaysOfWeek><Monday /><Tuesday /><Wednesday /><Thursday /><Friday /></DaysOfWeek>", testo)
        self.assertIn("<LogonTrigger>", testo)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", testo)  # un secondo avvio mentre gira è ignorato
        self.assertIn('"%s"' % PureWindowsPath("/srv/vault dir/scripts/avvio.py"), testo)  # vault con spazi: tra virgolette

    def test_servizio_si_riavvia_e_non_ha_limite_di_tempo(self):
        testo, _ = self.xml(SERVIZIO)
        self.assertIn("<RestartOnFailure>", testo)
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", testo)


class ComandoTest(unittest.TestCase):
    def test_il_nome_in_un_comando_e_un_percorso_e_non_si_espande_come_shell(self):
        j = {"command": ["{python}", "{vault}/a; touch x"]}
        self.assertEqual(ij.comando(j, CTX), [CTX["python"], "%s/a; touch x" % CTX["vault"]])  # un solo argomento, mai interpretato dalla shell


class ScrittaTest(unittest.TestCase):
    def test_con_out_scrive_i_file_e_non_lancia_comandi(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ij.main(["--os", "linux", "--out", d]), 0)
            self.assertTrue(list(Path(d).glob("second-brain.*.timer")))

    def test_un_altro_sistema_richiede_out_o_dry_run(self):
        altro = "windows" if ij.sistema_corrente() != "windows" else "linux"
        with self.assertRaises(SystemExit):
            ij.main(["--os", altro])

    def test_jobs_json_del_template_e_ben_formato(self):
        jobs = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
        for nome, j in jobs.items():
            self.assertIsInstance(j["command"], list, nome)
            self.assertTrue(all(isinstance(g, int) and 1 <= g <= 7 for g in j.get("days", [])), nome)
            if "time" in j:
                self.assertRegex(j["time"], r"^\d\d:\d\d$", nome)
                self.assertTrue(j.get("days"), nome)


if __name__ == "__main__":
    unittest.main()
