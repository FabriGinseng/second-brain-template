import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from xml.sax.saxutils import unescape

RADICE = Path(__file__).resolve().parent.parent
TRAY_PS1 = RADICE / "scripts" / "tray" / "tray.ps1"
spec = importlib.util.spec_from_file_location("install_jobs", RADICE / "install_jobs.py")
ij = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ij)

JOBS = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
TRAY = JOBS["tray"]
CTX = {"vault": Path("/srv/vault dir"), "home": Path("/srv/u"), "python": "/srv/py/python3", "log": Path("/srv/u/logs"), "etichetta": "second-brain"}
POWERSHELL = shutil.which("powershell.exe") if sys.platform == "win32" else None
SOLO_WINDOWS = unittest.skipUnless(POWERSHELL, "needs Windows PowerShell")
JOB_AMMESSI = r"second-brain\.(morning|feed|radar|chiusura|bozze|pulizia)"


def xml_windows(ctx=CTX):
    return ij.piano_windows("tray", TRAY, ctx)["file"][0][1].decode("utf-16")


def argomenti_task(xml):
    """The <Arguments> of the task as Task Scheduler passes them to conhost.exe."""
    return unescape(re.search(r"<Arguments>(.*?)</Arguments>", xml).group(1))


class RegistrazioneTest(unittest.TestCase):
    def test_tray_su_windows_e_macos_non_su_linux(self):
        self.assertIn("tray", ij.seleziona(JOBS, "windows"))
        self.assertIn("tray", ij.seleziona(JOBS, "macos"))
        self.assertNotIn("tray", ij.seleziona(JOBS, "linux"))
        self.assertNotIn("tray", ij.seleziona(JOBS, "linux", tutti=True))

    def test_windows_powershell_nascosto_con_virgolette_e_all_accesso(self):
        testo = xml_windows()
        args = argomenti_task(testo)
        script = PureWindowsPath("/srv/vault dir/scripts/tray/tray.ps1")
        self.assertRegex(args, r'^--headless cmd\.exe /c ""[^"]*powershell\.exe" "-NoProfile" "-NonInteractive" '
                               r'"-ExecutionPolicy" "Bypass" "-WindowStyle" "Hidden" "-File" ')
        self.assertIn('"-File" "%s" >> "' % script, args)  # vault with a space: one quoted argument
        self.assertTrue(args.endswith(' 2>&1"'))
        self.assertIn("<LogonTrigger><Enabled>true</Enabled><UserId>", testo)

    def test_windows_nessun_limite_di_tempo_ma_esci_la_chiude_davvero(self):
        """Regression guard: as a plain job Task Scheduler would kill it after 2 hours; as a service the watchdog would
        bring it back after "Esci"."""
        testo = xml_windows()
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", testo)
        self.assertNotIn("<Repetition>", testo)
        self.assertNotIn("<RestartOnFailure>", testo)
        self.assertNotIn("<CalendarTrigger>", testo)

    def test_macos_binario_compilato_senza_caffeinate_ne_keepalive(self):
        p = ij.piano_launchd("tray", TRAY, CTX)
        plist = plistlib.loads(p["file"][0][1])
        binario = str(Path("/srv/u") / "Library" / "Application Support" / "second-brain" / "SecondBrainTray")
        self.assertEqual([str(Path(a)) for a in plist["ProgramArguments"]], [binario])  # no caffeinate: it would keep the Mac awake
        self.assertTrue(plist["RunAtLoad"])
        self.assertNotIn("KeepAlive", plist)  # "Esci" must stay closed until the next login
        self.assertNotIn("StartCalendarInterval", plist)
        swiftc = [c for c in p["avvia"] if c[0] == "swiftc"]
        self.assertEqual(len(swiftc), 1)
        self.assertEqual(Path(swiftc[0][-1]), Path("/srv/vault dir/scripts/tray/SecondBrainTray.swift"))
        self.assertEqual(str(Path(swiftc[0][swiftc[0].index("-o") + 1])), binario)
        self.assertLess(p["avvia"].index(swiftc[0]), [c[1] if c[0] == "?" else c[0] for c in p["avvia"]].index("launchctl"))  # build before load

    def test_gli_altri_job_non_cambiano(self):
        self.assertEqual(ij.preparazione(JOBS["morning"], CTX, "macos"), [])
        self.assertEqual(ij.comando(JOBS["morning"], CTX, "macos")[1:], ["-I", "%s/scripts/avvio.py" % CTX["vault"]])
        self.assertIn("<ExecutionTimeLimit>PT2H</ExecutionTimeLimit>", ij.piano_windows("m", JOBS["morning"], CTX)["file"][0][1].decode("utf-16"))


class ScriptTest(unittest.TestCase):
    def test_tray_ps1_solo_ascii(self):
        """PowerShell 5.1 reads a file without a BOM in the ANSI code page: an accent would be garbled."""
        TRAY_PS1.read_bytes().decode("ascii")

    def test_menu_dei_job_da_una_lista_fissa(self):
        testo = TRAY_PS1.read_text(encoding="ascii")
        self.assertIn("@('morning'),\n    @('feed', 'radar'),\n    @('chiusura'),\n    @('bozze'),\n    @('pulizia')", testo)
        swift = (RADICE / "scripts" / "tray" / "SecondBrainTray.swift").read_text(encoding="utf-8")
        self.assertIn('[["morning"], ["feed", "radar"], ["chiusura"], ["bozze"], ["pulizia"]]', swift)

    @SOLO_WINDOWS
    def test_tray_ps1_si_analizza_senza_errori(self):
        comando = ("$t = $null; $e = $null; "
                   "[void][System.Management.Automation.Language.Parser]::ParseFile($env:TRAY_PS1, [ref]$t, [ref]$e); "
                   "$e | ForEach-Object { $_.ToString() }; 'errori=' + $e.Count")
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", comando], capture_output=True, text=True,
                           env={**os.environ, "TRAY_PS1": str(TRAY_PS1)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("errori=0", r.stdout, r.stdout)

    @SOLO_WINDOWS
    def test_self_test_con_la_riga_di_comando_del_task(self):
        """Runs the exact cmd.exe line of the generated task (quoting and log redirect included), plus -SelfTest."""
        with tempfile.TemporaryDirectory() as d:
            ctx = {**CTX, "vault": RADICE, "log": Path(d)}
            args = argomenti_task(xml_windows(ctx))
            self.assertTrue(args.startswith("--headless cmd.exe /c "))
            riga = args.removeprefix("--headless ").replace(' >> "', ' -SelfTest >> "', 1)
            # A str is passed to CreateProcess verbatim on Windows: no re-quoting by Python.
            r = subprocess.run(riga, cwd=RADICE, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
            uscita = (Path(d) / "second-brain-tray.log").read_text(encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, uscita)
        self.assertRegex(uscita, r"health: GET http://127\.0\.0\.1:8765/api/moduli -> (OK|NON RISPONDE) \(")
        server = PureWindowsPath(RADICE / "scripts" / "dashboard" / "server.py")
        self.assertIn("Avvia / riavvia -> schtasks.exe /end /tn second-brain.dashboard ; stop what listens on 127.0.0.1:8765 "
                      "if its command line has %s ; schtasks.exe /run /tn second-brain.dashboard" % server, uscita)
        # A real netstat read, nothing stopped: the self-test only describes the step.
        self.assertRegex(uscita, r"port 8765: (free|PID \d+ \((this vault's server\.py|another program)\)(, )?)+")
        self.assertIn("Ferma (riparte entro 10 min) -> schtasks.exe /end /tn second-brain.dashboard", uscita)
        self.assertIn("menu Avvia job:", uscita)
        for riga_job in re.findall(r"^  (?!Apri|Avvia|Ferma)(.+ -> .+)$", uscita, re.M):
            for comando in re.findall(r"schtasks\.exe \S+ /tn (\S+)", riga_job):
                self.assertRegex(comando, "^%s$" % JOB_AMMESSI)
        self.assertIn("menu Notifiche:", uscita)


def ps_str(testo):
    return "'%s'" % testo.replace("'", "''")


SERVER_FINTO = r"C:\vault dir\scripts\dashboard\server.py"
NETSTAT_TESTA = "  Proto  Local Address          Foreign Address        State           PID"
# Loads only the function definitions of tray.ps1 (no UI starts), then replaces the OS calls with recorders.
CARICA_FUNZIONI = r"""
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:TRAY_PS1, [ref]$t, [ref]$e)
foreach ($f in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($f.Extent.Text))
}
$Prefix = 'second-brain'; $DashboardPort = 8765
$global:Calls = New-Object System.Collections.ArrayList
function Get-TcpTable { return $global:Netstat }
function Get-ProcessCommandLine([int]$Id) { return $global:CommandLines[$Id] }
function Stop-Process {
    param([int]$Id, [switch]$Force, $ErrorAction)
    [void]$global:Calls.Add("stop $Id")
    if ($global:StopWorks) { $global:Netstat = @($global:Netstat | Where-Object { $_ -notmatch ('\s' + $Id + '$') }) }
}
function Wait-Process { param([int]$Id, $Timeout, $ErrorAction) }
function Invoke-Schtasks($ArgList) { [void]$global:Calls.Add('schtasks ' + ($ArgList -join ' ')); return @{ Ok = $true; Output = '' } }
function Show-Balloon { param([string]$Text, $Kind, [switch]$Always) [void]$global:Calls.Add("balloon $Text") }
function Write-TrayLog([string]$Text) { }
"""


@SOLO_WINDOWS
class RiavvioDashboardTest(unittest.TestCase):
    """«Avvia / riavvia» on Windows: /end leaves server.py running on the port, so it is stopped before /run, but only
    when it is this vault's server.py. netstat, the process command lines and every action are mocked."""

    def riavvia(self, netstat, righe_comando, stop_funziona=True):
        comando = CARICA_FUNZIONI + "\n".join([
            "$ServerScript = %s" % ps_str(SERVER_FINTO),
            "$global:Netstat = @(%s)" % ", ".join(ps_str(r) for r in [NETSTAT_TESTA] + netstat),
            "$global:CommandLines = @{ %s }" % "; ".join("%d = %s" % (pid, ps_str(r)) for pid, r in righe_comando.items()),
            "$global:StopWorks = $%s" % ("true" if stop_funziona else "false"),
            "Restart-Dashboard",
            "$global:Calls | ForEach-Object { 'CALL ' + $_ }",
        ])
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", comando], capture_output=True, text=True,
                           env={**os.environ, "TRAY_PS1": str(TRAY_PS1)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return [riga[5:] for riga in r.stdout.splitlines() if riga.startswith("CALL ")]

    def test_server_orfano_di_questo_vault_fermato_poi_avviato(self):
        chiamate = self.riavvia(
            ["  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242",
             "  TCP    127.0.0.1:8765         127.0.0.1:50000        TIME_WAIT       0"],
            # The task writes {vault}/scripts/...: mixed separators and another case must still match.
            {4242: r'C:\py\python.exe -I "c:\VAULT DIR/scripts/dashboard/server.py"'})
        self.assertEqual(chiamate[:3], ["schtasks /end /tn second-brain.dashboard", "stop 4242", "schtasks /run /tn second-brain.dashboard"])
        self.assertTrue(chiamate[3].startswith("balloon Dashboard avviata"), chiamate)

    def test_piu_server_sulla_porta_tutti_fermati(self):
        """Python sets SO_REUSEADDR: on Windows each restart could bind one more server.py next to the old ones."""
        chiamate = self.riavvia(
            ["  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242",
             "  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       5353"],
            {4242: '"%s"' % SERVER_FINTO, 5353: '"%s"' % SERVER_FINTO})
        self.assertEqual(chiamate[1:4], ["stop 4242", "stop 5353", "schtasks /run /tn second-brain.dashboard"])

    def test_porta_di_un_altro_programma_non_fermato_e_detto(self):
        chiamate = self.riavvia(
            ["  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242"],
            {4242: r'C:\Tools\other.exe --port 8765'})
        self.assertFalse([c for c in chiamate if c.startswith("stop ")], chiamate)
        self.assertNotIn("schtasks /run /tn second-brain.dashboard", chiamate)
        self.assertIn("balloon La porta 8765 e' occupata da un altro programma (PID 4242): non lo chiudo e non avvio la dashboard.", chiamate)

    def test_riga_di_comando_illeggibile_conta_come_altro_programma(self):
        """Another user's or an elevated process: Win32_Process gives no command line, so nothing is stopped."""
        chiamate = self.riavvia(["  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242"], {})
        self.assertFalse([c for c in chiamate if c.startswith("stop ")], chiamate)
        self.assertNotIn("schtasks /run /tn second-brain.dashboard", chiamate)

    def test_server_di_un_altro_vault_non_fermato(self):
        chiamate = self.riavvia(
            ["  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242"],
            {4242: r'python.exe "C:\other vault\scripts\dashboard\server.py"'})
        self.assertFalse([c for c in chiamate if c.startswith("stop ")], chiamate)

    def test_porta_libera_solo_avvio(self):
        chiamate = self.riavvia(
            # Another port that starts with 8765, a client connection and a server on all addresses are not the dashboard.
            ["  TCP    127.0.0.1:87650        0.0.0.0:0              LISTENING       999",
             "  TCP    127.0.0.1:50000        127.0.0.1:8765         ESTABLISHED     998",
             "  TCP    0.0.0.0:8765           0.0.0.0:0              LISTENING       997"],
            {999: '"%s"' % SERVER_FINTO, 998: '"%s"' % SERVER_FINTO, 997: '"%s"' % SERVER_FINTO})
        self.assertEqual(chiamate[:2], ["schtasks /end /tn second-brain.dashboard", "schtasks /run /tn second-brain.dashboard"])

    def test_stato_tradotto_da_netstat(self):
        """The state word is translated and can have a space ("IN ASCOLTO"): the listener is found without it."""
        chiamate = self.riavvia(["  TCP    127.0.0.1:8765         0.0.0.0:0              IN ASCOLTO      4242"], {4242: '"%s"' % SERVER_FINTO})
        self.assertEqual(chiamate[1:3], ["stop 4242", "schtasks /run /tn second-brain.dashboard"])

    def test_porta_ancora_occupata_dopo_lo_stop_niente_avvio(self):
        chiamate = self.riavvia(["  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242"],
                                {4242: '"%s"' % SERVER_FINTO}, stop_funziona=False)
        self.assertIn("stop 4242", chiamate)
        self.assertNotIn("schtasks /run /tn second-brain.dashboard", chiamate)
        self.assertTrue([c for c in chiamate if c.startswith("balloon Non riesco a fermare")], chiamate)


class RiavvioTestoTest(unittest.TestCase):
    """Runs on every system, CI on Linux included."""

    def test_windows_ferma_il_server_tra_end_e_run(self):
        testo = TRAY_PS1.read_text(encoding="ascii")
        corpo = testo[testo.index("function Restart-Dashboard"):]
        corpo = corpo[:corpo.index("\n}\n")]
        self.assertLess(corpo.index("Get-EndArgs 'dashboard'"), corpo.index("Stop-Process"))
        self.assertLess(corpo.index("Stop-Process"), corpo.index("Start-SecondBrainTask 'dashboard'"))
        self.assertIn("Invoke-Safely {\n        Restart-Dashboard", testo)

    def test_macos_invariato_kickstart_k(self):
        swift = (RADICE / "scripts" / "tray" / "SecondBrainTray.swift").read_text(encoding="utf-8")
        self.assertIn('loaded ? ["kickstart", "-k", serviceTarget("dashboard")]', swift)


if __name__ == "__main__":
    unittest.main()
