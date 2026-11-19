<#
.SYNOPSIS
Second brain tray icon for Windows: dashboard status, quick job starts, failure notifications.

.DESCRIPTION
Registered by install_jobs.py as the job "second-brain.tray" (at logon). Native only: Windows PowerShell 5.1,
System.Windows.Forms and System.Drawing, no third-party module.

Security notes:
- Every task name and command comes from the fixed lists below; nothing read from the system, the network or the
  menu is ever used to build a task name or a command. Names read back from Task Scheduler only end up in balloon text.
- The health check talks only to 127.0.0.1:8765, with the system proxy disabled.
- "Avvia / riavvia" stops a process only when it listens on 127.0.0.1:8765 and its command line names the server.py of
  this vault. The PID read from netstat goes to Get-CimInstance and Stop-Process as an [int], never into a command line.

This file is ASCII only on purpose: PowerShell 5.1 reads a file without a BOM in the ANSI code page.

.PARAMETER SelfTest
No UI: prints the health-check result, the job items the menu would show and the exact commands each item runs,
then exits 0.
#>
[CmdletBinding()]
param([switch]$SelfTest)

Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'

$Prefix = 'second-brain'
# PORTA of server.py: jobs.json passes no other port and config.json has none.
$DashboardPort = 8765
$DashboardUrl = "http://127.0.0.1:$DashboardPort/"
# Cheapest GET of the dashboard: it reads config.json only. The Host header (127.0.0.1:8765) is the one the server allows.
$HealthUrl = "http://127.0.0.1:$DashboardPort/api/moduli"
# The server.py of this vault: "Avvia / riavvia" stops a process on the dashboard port only if its command line names it.
$ServerScript = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\dashboard\server.py'))
$HealthTimeoutMs = 3000
$PollSeconds = 30
# Fixed allowlist of the "Avvia job" menu: each entry is run in order (feed first, then radar once feed has ended).
$JobGroups = @(
    @('morning'),
    @('feed', 'radar'),
    @('chiusura'),
    @('bozze'),
    @('pulizia')
)
# Tasks whose LastTaskResult is not checked: the dashboard has its own up/down balloon, the tray is this process.
$NoFailureCheck = @('dashboard', 'tray')
# SCHED_S_* informational codes (0x41300-0x41308): ready, running, disabled, has not run, no more runs, not scheduled,
# terminated (also after "Ferma"), no valid triggers, event trigger. None of them is a failure.
$SchedInfoFirst = [uint32]0x41300
$SchedInfoLast = [uint32]0x41308

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Test-Dashboard {
    # Returns @{ Up = bool; Detail = string }. Green only on HTTP 200: a 403 or 500 means something is wrong.
    $request = [System.Net.HttpWebRequest]::Create($HealthUrl)
    $request.Method = 'GET'
    $request.Timeout = $HealthTimeoutMs
    $request.ReadWriteTimeout = $HealthTimeoutMs
    $request.Proxy = $null
    $request.KeepAlive = $false
    try {
        $response = $request.GetResponse()
        try { $code = [int]$response.StatusCode } finally { $response.Close() }
        return @{ Up = ($code -eq 200); Detail = "HTTP $code" }
    } catch [System.Net.WebException] {
        $inner = $_.Exception
        if ($inner.Response) {
            $code = [int]$inner.Response.StatusCode
            $inner.Response.Close()
            return @{ Up = $false; Detail = "HTTP $code" }
        }
        return @{ Up = $false; Detail = [string]$inner.Status }
    }
}

function Get-TaskName([string]$Job) {
    # $Job always comes from $JobGroups, 'dashboard' or a name read back for a balloon: never from user input.
    return "$Prefix.$Job"
}

function Get-RegisteredJobs {
    # Short names of the second-brain.* tasks in the root folder, where install_jobs.py registers them.
    $names = @{}
    $tasks = @(Get-ScheduledTask -TaskPath '\' -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like "$Prefix.*" })
    foreach ($t in $tasks) { $names[$t.TaskName.Substring($Prefix.Length + 1)] = $t }
    return $names
}

function Get-VisibleGroups($Registered) {
    # The allowlisted groups reduced to the tasks that exist; a group with none is hidden.
    $out = @()
    foreach ($group in $JobGroups) {
        $present = @($group | Where-Object { $Registered.ContainsKey($_) })
        if ($present.Count -gt 0) { $out += , $present }
    }
    return , $out
}

# The schtasks argument lists. The click handlers and -SelfTest both use these functions, so -SelfTest prints exactly
# what a click runs.
function Get-RunArgs([string]$Job) { return @('/run', '/tn', (Get-TaskName $Job)) }
function Get-EndArgs([string]$Job) { return @('/end', '/tn', (Get-TaskName $Job)) }
function Format-Command($ArgList) { return 'schtasks.exe ' + ($ArgList -join ' ') }

function Invoke-Schtasks($ArgList) {
    $output = & schtasks.exe @ArgList 2>&1
    return @{ Ok = ($LASTEXITCODE -eq 0); Output = ($output | Out-String).Trim() }
}

function Get-GroupLabel($Group) { return ($Group -join ' + ') }

# The two OS reads of the dashboard port, behind small functions like Invoke-Schtasks: the tests replace them.
function Get-TcpTable { return @(& netstat.exe -ano -p TCP) }
function Get-ProcessCommandLine([int]$Id) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $Id" -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    return [string]$process.CommandLine
}

function Get-DashboardListeners {
    # PIDs listening on 127.0.0.1:<port>. netstat, not Get-NetTCPConnection: with two servers on the port
    # Get-NetTCPConnection lists only one. A listening row has remote 0.0.0.0:0; the state word is translated
    # (and can hold a space), so it is never read and the PID is the last field.
    $local = "127.0.0.1:$DashboardPort"
    $ids = @()
    foreach ($line in Get-TcpTable) {
        $fields = @(([string]$line).Trim() -split '\s+')
        if ($fields.Count -lt 5 -or $fields[0] -ne 'TCP' -or $fields[1] -ne $local -or $fields[2] -ne '0.0.0.0:0') { continue }
        $id = 0
        if ([int]::TryParse($fields[$fields.Count - 1], [ref]$id) -and $id -gt 0 -and $ids -notcontains $id) { $ids += $id }
    }
    return $ids
}

function Test-OurServer([int]$Id) {
    # Identity check before any stop: the command line must name the server.py of this vault. A command line that
    # cannot be read (another user's or an elevated process) counts as another program.
    $line = Get-ProcessCommandLine $Id
    if (-not $line) { return $false }
    return $line.Replace('/', '\').IndexOf($ServerScript, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Format-Listeners($Ids) {
    if (@($Ids).Count -eq 0) { return 'free' }
    return (@($Ids | ForEach-Object {
        if (Test-OurServer $_) { "PID $_ (this vault's server.py)" } else { "PID $_ (another program)" }
    }) -join ', ')
}

function New-DotIcon([System.Drawing.Color]$Color) {
    # Drawn in code: no binary asset in the repo.
    $bitmap = New-Object System.Drawing.Bitmap 32, 32
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $brush = New-Object System.Drawing.SolidBrush $Color
        $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(160, 0, 0, 0)), 2
        try {
            $graphics.FillEllipse($brush, 3, 3, 26, 26)
            $graphics.DrawEllipse($pen, 3, 3, 26, 26)
        } finally { $brush.Dispose(); $pen.Dispose() }
    } finally { $graphics.Dispose() }
    # Icon.FromHandle does not own the HICON; the two icons live for the whole process, so the handle is never freed.
    return [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
}

# ---------------------------------------------------------------- self-test (no UI)

if ($SelfTest) {
    $health = Test-Dashboard
    $state = if ($health.Up) { 'OK' } else { 'NON RISPONDE' }
    Write-Output ("health: GET $HealthUrl -> $state ($($health.Detail))")
    $green = New-DotIcon ([System.Drawing.Color]::FromArgb(46, 160, 67))
    $red = New-DotIcon ([System.Drawing.Color]::FromArgb(207, 34, 46))
    Write-Output ("icons: drawn {0}x{1}" -f $green.Width, $green.Height)
    $green.Dispose(); $red.Dispose()
    Write-Output 'menu Dashboard:'
    Write-Output ("  Apri dashboard -> default browser $DashboardUrl")
    Write-Output ("  Avvia / riavvia -> " + (Format-Command (Get-EndArgs 'dashboard')) +
        " ; stop what listens on 127.0.0.1:$DashboardPort if its command line has $ServerScript ; " + (Format-Command (Get-RunArgs 'dashboard')))
    Write-Output ("    now on port ${DashboardPort}: " + (Format-Listeners @(Get-DashboardListeners)))
    Write-Output ("  Ferma (riparte entro 10 min) -> " + (Format-Command (Get-EndArgs 'dashboard')))
    $registered = Get-RegisteredJobs
    Write-Output 'menu Avvia job:'
    $visible = Get-VisibleGroups $registered
    if ($visible.Count -eq 0) { Write-Output '  (nessun job registrato)' }
    foreach ($group in $visible) {
        $commands = @($group | ForEach-Object { Format-Command (Get-RunArgs $_) })
        Write-Output ("  " + (Get-GroupLabel $group) + ' -> ' + ($commands -join ' ; then, after it ends: '))
    }
    $hidden = @($JobGroups | ForEach-Object { $_ } | Where-Object { -not $registered.ContainsKey($_) })
    if ($hidden.Count -gt 0) { Write-Output ('hidden (task not registered): ' + ($hidden -join ', ')) }
    Write-Output 'menu Notifiche: Notifiche attive (on)'
    exit 0
}

# ---------------------------------------------------------------- tray

# One tray per user session. "Local\" scopes the mutex to this logon session.
$createdNew = $false
$script:Mutex = New-Object System.Threading.Mutex($true, "Local\$Prefix.tray", [ref]$createdNew)
if (-not $createdNew) { exit 0 }

$script:IconUp = New-DotIcon ([System.Drawing.Color]::FromArgb(46, 160, 67))
$script:IconDown = New-DotIcon ([System.Drawing.Color]::FromArgb(207, 34, 46))
$script:DashboardUp = $null          # unknown until the first check: no balloon for the initial state
$script:NotificationsOn = $true
$script:SeenRuns = @{}               # short task name -> LastRunTime already examined
$script:ChainQueue = New-Object System.Collections.Queue
$script:ChainCurrent = $null
$script:ChainStarted = [datetime]::MinValue
$script:ExpectDown = $false          # set by "Ferma", checked by the recheck a few seconds later

$script:Tray = New-Object System.Windows.Forms.NotifyIcon
$script:Tray.Icon = $script:IconDown
$script:Tray.Text = 'Second brain: controllo in corso'

function Show-Balloon([string]$Text, [System.Windows.Forms.ToolTipIcon]$Kind = [System.Windows.Forms.ToolTipIcon]::Info, [switch]$Always) {
    # Answers to a click (-Always) are shown even with notifications off; background events follow the toggle.
    if (-not $Always -and -not $script:NotificationsOn) { return }
    $script:Tray.ShowBalloonTip(5000, 'Second brain', $Text, $Kind)
}

function Write-TrayLog([string]$Text) {
    # Straight to stdout, which install_jobs.py redirects to the job log. Not Write-Output: inside a function that
    # would become part of its return value. Never write task output or personal data here.
    [Console]::Out.WriteLine(('{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Text))
}

function Update-DashboardState {
    $health = Test-Dashboard
    $script:Tray.Icon = if ($health.Up) { $script:IconUp } else { $script:IconDown }
    $script:Tray.Text = if ($health.Up) { 'Second brain: dashboard attiva' } else { 'Second brain: dashboard ferma' }
    if ($null -ne $script:DashboardUp -and $script:DashboardUp -ne $health.Up) {
        if ($health.Up) { Show-Balloon 'La dashboard risponde di nuovo.' }
        else { Show-Balloon "La dashboard non risponde ($($health.Detail))." ([System.Windows.Forms.ToolTipIcon]::Warning) }
    }
    $script:DashboardUp = $health.Up
}

function Test-Failure([uint32]$Code) {
    if ($Code -eq 0) { return $false }
    return -not ($Code -ge $SchedInfoFirst -and $Code -le $SchedInfoLast)
}

function Update-TaskFailures([switch]$Seed) {
    # A run is examined once it has ended (result is not "running"): LastRunTime is set when a run starts, so
    # comparing only LastRunTime would miss a failure that ends after the poll that saw the start.
    $registered = Get-RegisteredJobs
    foreach ($name in $registered.Keys) {
        if ($NoFailureCheck -contains $name) { continue }
        $info = $registered[$name] | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
        if ($null -eq $info) { continue }
        $code = [uint32]([int64]$info.LastTaskResult -band 0xFFFFFFFF)   # same value whether it comes signed or not
        if ($code -eq [uint32]0x41301) { continue }   # still running: look again at the next poll
        $last = $info.LastRunTime
        if ($script:SeenRuns.ContainsKey($name) -and $script:SeenRuns[$name] -eq $last) { continue }
        $script:SeenRuns[$name] = $last
        # At startup old results are only remembered, so a failure is not announced again at every logon.
        if (-not $Seed -and (Test-Failure $code)) {
            Write-TrayLog ("task $Prefix.$name ended with 0x{0:X8}" -f $code)
            Show-Balloon ("Il job $name e' finito con un errore (0x{0:X8}). Vedi il suo log." -f $code) ([System.Windows.Forms.ToolTipIcon]::Error)
        }
    }
}

function Start-SecondBrainTask([string]$Job) {
    $result = Invoke-Schtasks (Get-RunArgs $Job)
    if (-not $result.Ok) {
        Write-TrayLog "schtasks /run $Prefix.$Job failed"
        Show-Balloon "Non riesco ad avviare $Job." ([System.Windows.Forms.ToolTipIcon]::Error) -Always
    }
    return $result.Ok
}

function Start-NextInChain {
    if ($script:ChainQueue.Count -eq 0) { $script:ChainCurrent = $null; $script:ChainTimer.Stop(); return }
    $job = [string]$script:ChainQueue.Dequeue()
    if (Start-SecondBrainTask $job) {
        $script:ChainCurrent = $job
        $script:ChainStarted = Get-Date
        $script:ChainTimer.Start()
    } else {
        $script:ChainQueue.Clear(); $script:ChainCurrent = $null; $script:ChainTimer.Stop()
    }
}

function Restart-Dashboard {
    [void](Invoke-Schtasks (Get-EndArgs 'dashboard'))   # fails harmlessly when it is not running
    # /end ends only conhost.exe, the root of the task: cmd.exe and server.py outlive it and keep the port. Python
    # sets SO_REUSEADDR, so on Windows a new server.py binds next to the old one, which goes on answering.
    # Everything on the port is checked first: if a program that is not ours holds it, nothing is stopped or started.
    $listeners = @(Get-DashboardListeners)
    $foreign = @($listeners | Where-Object { -not (Test-OurServer $_) })
    if ($foreign.Count -gt 0) {
        Write-TrayLog ("port $DashboardPort held by another program (PID " + ($foreign -join ', ') + '): dashboard not started')
        Show-Balloon ("La porta $DashboardPort e' occupata da un altro programma (PID " + ($foreign -join ', ') + '): non lo chiudo e non avvio la dashboard.') ([System.Windows.Forms.ToolTipIcon]::Warning) -Always
        return
    }
    if ($listeners.Count -gt 0) {
        foreach ($id in $listeners) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $id -Timeout 5 -ErrorAction SilentlyContinue   # the port is free only once it has exited
            Write-TrayLog "stopped server.py PID $id left on port $DashboardPort"
        }
        if (@(Get-DashboardListeners).Count -gt 0) {
            Show-Balloon "Non riesco a fermare il server rimasto sulla porta ${DashboardPort}: dashboard non riavviata." ([System.Windows.Forms.ToolTipIcon]::Error) -Always
            return
        }
    }
    if (Start-SecondBrainTask 'dashboard') { Show-Balloon 'Dashboard avviata: l''icona diventa verde quando risponde.' -Always }
}

function Invoke-Safely([scriptblock]$Body) {
    # An exception escaping a WinForms handler would end Application.Run: log it and keep the tray alive.
    try { & $Body } catch { Write-TrayLog ("error: " + $_.Exception.Message) }
}

$script:Menu = New-Object System.Windows.Forms.ContextMenuStrip

# --- Dashboard
$dashboardMenu = New-Object System.Windows.Forms.ToolStripMenuItem 'Dashboard'
$openItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Apri dashboard'
$openItem.add_Click({ Invoke-Safely { Start-Process $DashboardUrl } })
$restartItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Avvia / riavvia'
$restartItem.add_Click({
    Invoke-Safely {
        Restart-Dashboard
        $script:ExpectDown = $false
        $script:RecheckTimer.Start()
    }
})
$stopItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Ferma (riparte entro 10 min)'
$stopItem.add_Click({
    Invoke-Safely {
        $result = Invoke-Schtasks (Get-EndArgs 'dashboard')
        if ($result.Ok) { Show-Balloon 'Dashboard fermata. Il controllo di Windows la riavvia entro 10 minuti.' -Always }
        else { Show-Balloon 'Non riesco a fermare la dashboard.' ([System.Windows.Forms.ToolTipIcon]::Error) -Always }
        $script:ExpectDown = $result.Ok
        $script:RecheckTimer.Start()
    }
})
[void]$dashboardMenu.DropDownItems.Add($openItem)
[void]$dashboardMenu.DropDownItems.Add($restartItem)
[void]$dashboardMenu.DropDownItems.Add($stopItem)

# --- Avvia job (rebuilt every time it opens, so a job registered later shows up)
$jobsMenu = New-Object System.Windows.Forms.ToolStripMenuItem 'Avvia job'
[void]$jobsMenu.DropDownItems.Add('(caricamento)')
$jobsMenu.add_DropDownOpening({
    Invoke-Safely {
        $jobsMenu.DropDownItems.Clear()
        $visible = Get-VisibleGroups (Get-RegisteredJobs)
        if ($visible.Count -eq 0) {
            $empty = New-Object System.Windows.Forms.ToolStripMenuItem '(nessun job registrato)'
            $empty.Enabled = $false
            [void]$jobsMenu.DropDownItems.Add($empty)
        }
        foreach ($group in $visible) {
            $item = New-Object System.Windows.Forms.ToolStripMenuItem (Get-GroupLabel $group)
            # The handler reads the group from Tag: a scriptblock does not capture the loop variable.
            $item.Tag = $group
            $item.add_Click({
                param($menuItem, $clickArgs)
                Invoke-Safely {
                    if ($null -ne $script:ChainCurrent) {
                        Show-Balloon "Aspetto la fine di $($script:ChainCurrent) prima di avviare altro." -Always
                        return
                    }
                    $script:ChainQueue.Clear()
                    foreach ($job in @($menuItem.Tag)) { $script:ChainQueue.Enqueue([string]$job) }
                    Show-Balloon ("Avvio: " + (Get-GroupLabel @($menuItem.Tag))) -Always
                    Start-NextInChain
                }
            })
            [void]$jobsMenu.DropDownItems.Add($item)
        }
    }
})

# --- Notifiche
$notifyMenu = New-Object System.Windows.Forms.ToolStripMenuItem 'Notifiche'
$toggleItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Notifiche attive (questa sessione)'
$toggleItem.CheckOnClick = $true
$toggleItem.Checked = $true
$toggleItem.add_CheckedChanged({ $script:NotificationsOn = $toggleItem.Checked })
[void]$notifyMenu.DropDownItems.Add($toggleItem)

$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Esci'
$exitItem.add_Click({ [System.Windows.Forms.Application]::Exit() })

[void]$script:Menu.Items.Add($dashboardMenu)
[void]$script:Menu.Items.Add($jobsMenu)
[void]$script:Menu.Items.Add($notifyMenu)
[void]$script:Menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))
[void]$script:Menu.Items.Add($exitItem)
$script:Tray.ContextMenuStrip = $script:Menu
$script:Tray.add_DoubleClick({ Invoke-Safely { Start-Process $DashboardUrl } })

# Forms timers tick on the UI thread, inside Application.Run (System.Timers.Timer would not).
$script:PollTimer = New-Object System.Windows.Forms.Timer
$script:PollTimer.Interval = $PollSeconds * 1000
$script:PollTimer.add_Tick({ Invoke-Safely { Update-DashboardState; Update-TaskFailures } })

# One extra check a few seconds after "Avvia / riavvia" or "Ferma", so the icon does not wait for the next poll.
$script:RecheckTimer = New-Object System.Windows.Forms.Timer
$script:RecheckTimer.Interval = 5000
$script:RecheckTimer.add_Tick({
    $script:RecheckTimer.Stop()
    Invoke-Safely {
        Update-DashboardState
        # /end stops the task; if the server process outlived it, say so instead of showing a stop that did not happen.
        if ($script:ExpectDown -and $script:DashboardUp) {
            Show-Balloon 'La dashboard risponde ancora dopo Ferma: il processo del server e'' rimasto attivo.' ([System.Windows.Forms.ToolTipIcon]::Warning) -Always
        }
        $script:ExpectDown = $false
    }
})

# feed + radar: the next job starts when the current task is no longer running (2 h cap, like the job time limit).
$script:ChainTimer = New-Object System.Windows.Forms.Timer
$script:ChainTimer.Interval = 5000
$script:ChainTimer.add_Tick({
    Invoke-Safely {
        if ($null -eq $script:ChainCurrent) { $script:ChainTimer.Stop(); return }
        $elapsed = (Get-Date) - $script:ChainStarted
        if ($elapsed.TotalSeconds -lt 10) { return }
        $task = Get-ScheduledTask -TaskPath '\' -TaskName (Get-TaskName $script:ChainCurrent) -ErrorAction SilentlyContinue
        if ($null -ne $task -and [string]$task.State -eq 'Running' -and $elapsed.TotalHours -lt 2) { return }
        Start-NextInChain
    }
})

try {
    Invoke-Safely { Update-DashboardState; Update-TaskFailures -Seed }
    $script:Tray.Visible = $true
    $script:PollTimer.Start()
    Write-TrayLog 'tray started'
    [System.Windows.Forms.Application]::Run()
} finally {
    $script:PollTimer.Stop(); $script:RecheckTimer.Stop(); $script:ChainTimer.Stop()
    $script:Tray.Visible = $false   # otherwise a dead icon stays in the tray until the mouse passes over it
    $script:Tray.Dispose()
    $script:Mutex.ReleaseMutex()
    $script:Mutex.Dispose()
    Write-TrayLog 'tray closed'
}
