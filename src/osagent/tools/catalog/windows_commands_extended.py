"""Extended Windows PowerShell catalog — remaining network/device/system tools."""

from __future__ import annotations

# fmt: off
COMMANDS: list[dict] = [
    # ---------- Wi-Fi ----------
    {
        "id": "windows.wifi.available_networks",
        "description": "Discover available Wi-Fi networks in range.",
        "confirm": "none",
        "timeout": 45,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"netsh wlan show networks mode=bssid",
    },
    {
        "id": "windows.wifi.connect",
        "description": "Connect to a Wi-Fi profile/SSID by name.",
        "confirm": "ask",
        "timeout": 60,
        "result": "text",
        "defaults": {"name": ""},
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "SSID / profile name"}},
            "required": ["name"],
        },
        "script": r"netsh wlan connect name='{name}'",
    },
    {
        "id": "windows.wifi.disconnect",
        "description": "Disconnect from the current Wi-Fi network.",
        "confirm": "ask",
        "timeout": 30,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"netsh wlan disconnect",
    },
    {
        "id": "windows.wifi.forget",
        "description": "Forget a saved Wi-Fi profile.",
        "confirm": "destructive",
        "timeout": 30,
        "result": "text",
        "defaults": {"name": ""},
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "script": r"netsh wlan delete profile name='{name}'",
    },

    # ---------- Network ----------
    {
        "id": "windows.network.diagnostics",
        "description": "Run a quick connectivity diagnostics summary (ping + DNS).",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Network diagnostics",
        "script": r"""
$gw = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1).NextHop
$dns = Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object {{ $_.ServerAddresses }} | Select-Object -First 3 InterfaceAlias, ServerAddresses
$pingGw = $null
if ($gw) {{ $pingGw = Test-Connection -ComputerName $gw -Count 1 -Quiet -ErrorAction SilentlyContinue }}
$pingDns = Test-Connection -ComputerName '1.1.1.1' -Count 1 -Quiet -ErrorAction SilentlyContinue
$pingWeb = Test-Connection -ComputerName 'www.microsoft.com' -Count 1 -Quiet -ErrorAction SilentlyContinue
[PSCustomObject]@{{
  gateway = $gw
  gateway_ok = [bool]$pingGw
  dns_ok = [bool]$pingDns
  internet_ok = [bool]$pingWeb
  dns_servers = @($dns | ForEach-Object {{ [PSCustomObject]@{{ iface = $_.InterfaceAlias; servers = @($_.ServerAddresses) }} }})
}} | ConvertTo-Json -Compress -Depth 4
""",
    },
    {
        "id": "windows.network.test_connectivity",
        "description": "Test gateway, DNS and internet reachability.",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Connectivity test",
        "script": r"""
$gw = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -EA SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1).NextHop
[PSCustomObject]@{{
  gateway = $gw
  gateway_ok = if ($gw) {{ Test-Connection $gw -Count 1 -Quiet -EA SilentlyContinue }} else {{ $false }}
  dns_ok = Test-Connection 1.1.1.1 -Count 1 -Quiet -EA SilentlyContinue
  internet_ok = Test-Connection www.microsoft.com -Count 1 -Quiet -EA SilentlyContinue
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.network.dns_flush",
        "description": "Flush the DNS resolver cache.",
        "confirm": "ask",
        "timeout": 30,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"ipconfig /flushdns",
    },
    {
        "id": "windows.network.proxy.get",
        "description": "Inspect WinINET / system proxy settings.",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Proxy settings",
        "script": r"""
$p = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
[PSCustomObject]@{{
  proxy_enable = [bool]$p.ProxyEnable
  proxy_server = $p.ProxyServer
  proxy_override = $p.ProxyOverride
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.network.proxy.set",
        "description": "Enable/disable or set WinINET proxy server (user-level).",
        "confirm": "destructive",
        "timeout": 20,
        "result": "json",
        "defaults": {"enable": False, "server": ""},
        "parameters": {
            "type": "object",
            "properties": {
                "enable": {"type": "boolean"},
                "server": {"type": "string", "description": "host:port"},
            },
        },
        "success_message": "Proxy updated",
        "script": r"""
$path = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$en = {enable}
$srv = '{server}'
Set-ItemProperty -Path $path -Name ProxyEnable -Value $(if ($en) {{ 1 }} else {{ 0 }})
if ($srv) {{ Set-ItemProperty -Path $path -Name ProxyServer -Value $srv }}
[PSCustomObject]@{{ ok=$true; enable=$en; server=$srv }} | ConvertTo-Json -Compress
""",
    },

    # ---------- Bluetooth ----------
    {
        "id": "windows.bluetooth.pair",
        "description": "Open Bluetooth settings / add device UI (pairing requires user interaction).",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"Start-Process 'ms-settings:bluetooth'",
    },
    {
        "id": "windows.bluetooth.disconnect",
        "description": "Disable a Bluetooth PnP device by friendly name substring (best-effort).",
        "confirm": "ask",
        "timeout": 45,
        "result": "json",
        "defaults": {"name": ""},
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "success_message": "Bluetooth disconnect",
        "script": r"""
$n = '{name}'
$d = Get-PnpDevice -Class Bluetooth -EA SilentlyContinue | Where-Object {{ $_.FriendlyName -like ("*" + $n + "*") }} | Select-Object -First 1
if (-not $d) {{ [PSCustomObject]@{{ ok=$false; message='Device not found' }} | ConvertTo-Json -Compress }}
else {{
  Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -EA SilentlyContinue
  [PSCustomObject]@{{ ok=$true; name=$d.FriendlyName; action='disabled' }} | ConvertTo-Json -Compress
}}
""",
    },
    {
        "id": "windows.bluetooth.remove_pairing",
        "description": "Remove/uninstall a paired Bluetooth device by name substring.",
        "confirm": "destructive",
        "timeout": 45,
        "result": "json",
        "defaults": {"name": ""},
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "success_message": "Bluetooth unpaired",
        "script": r"""
$n = '{name}'
$d = Get-PnpDevice -Class Bluetooth -EA SilentlyContinue | Where-Object {{ $_.FriendlyName -like ("*" + $n + "*") }} | Select-Object -First 1
if (-not $d) {{ [PSCustomObject]@{{ ok=$false; message='Device not found' }} | ConvertTo-Json -Compress }}
else {{
  Remove-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -EA SilentlyContinue
  [PSCustomObject]@{{ ok=$true; name=$d.FriendlyName; action='removed' }} | ConvertTo-Json -Compress
}}
""",
    },

    # ---------- Audio ----------
    {
        "id": "windows.audio.get_default_device",
        "description": "Identify default audio playback / recording devices.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Default audio devices",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$play = Get-AudioDevice -List -EA SilentlyContinue | Where-Object {{ $_.Default -and $_.Type -eq 'Playback' }} | Select-Object -First 1
$rec = Get-AudioDevice -List -EA SilentlyContinue | Where-Object {{ $_.Default -and $_.Type -eq 'Recording' }} | Select-Object -First 1
# Fallback via MMDevices names from registry / CIM is limited; use Sound settings open hint
[PSCustomObject]@{{
  playback = if ($play) {{ $play.Name }} else {{ $null }}
  recording = if ($rec) {{ $rec.Name }} else {{ $null }}
  note = if (-not $play) {{ 'Install AudioDeviceCmdlets or use windows.audio.list_devices / Settings' }} else {{ $null }}
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.audio.set_default_device",
        "description": "Open Sound settings to select default device (automated default switch needs extra modules).",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"name": ""},
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Hint shown to user"}},
        },
        "script": r"Start-Process 'ms-settings:sound'",
    },
    {
        "id": "windows.audio.get_input_level",
        "description": "Best-effort microphone activity check (opens sound settings if metering unavailable).",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Input level",
        "script": r"""
[PSCustomObject]@{{
  ok = $true
  message = 'Live mic metering requires WASAPI; open Sound settings to test input.'
  settings = 'ms-settings:sound'
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.audio.test_output",
        "description": "Play a short system beep to test audio output.",
        "confirm": "none",
        "timeout": 10,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Audio test",
        "script": r"""
[Console]::Beep(880, 250)
Start-Sleep -Milliseconds 100
[Console]::Beep(660, 250)
[PSCustomObject]@{{ ok=$true; message='Played test beeps' }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.audio.set_app_volume",
        "description": "Open volume mixer (per-app volume needs UI / pycaw session API).",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"app": "", "percent": 50},
        "parameters": {
            "type": "object",
            "properties": {
                "app": {"type": "string"},
                "percent": {"type": "integer"},
            },
        },
        "script": r"Start-Process 'ms-settings:apps-volume'",
    },

    # ---------- Display ----------
    {
        "id": "windows.display.set_resolution",
        "description": "Open Display settings to change resolution (safe path).",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"width": 0, "height": 0},
        "parameters": {
            "type": "object",
            "properties": {
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
        },
        "script": r"Start-Process 'ms-settings:display'",
    },
    {
        "id": "windows.display.set_scale",
        "description": "Open Display settings to change UI scaling.",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"scale": 100},
        "parameters": {
            "type": "object",
            "properties": {"scale": {"type": "integer", "description": "100,125,150,…"}},
        },
        "script": r"Start-Process 'ms-settings:display'",
    },
    {
        "id": "windows.display.arrange",
        "description": "Open Display settings to arrange multiple monitors.",
        "confirm": "none",
        "timeout": 20,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"Start-Process 'ms-settings:display'",
    },
    {
        "id": "windows.display.set_refresh_rate",
        "description": "Open advanced display settings to change refresh rate.",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"hz": 60},
        "parameters": {
            "type": "object",
            "properties": {"hz": {"type": "integer"}},
        },
        "script": r"Start-Process 'ms-settings:display-advanced'",
    },

    # ---------- Printers ----------
    {
        "id": "windows.printers.print_file",
        "description": "Print a file using the default verb (Print) or Out-Printer for text.",
        "confirm": "ask",
        "timeout": 60,
        "result": "json",
        "defaults": {"path": "", "printer": ""},
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "printer": {"type": "string"},
            },
            "required": ["path"],
        },
        "success_message": "Print submitted",
        "script": r"""
$p = '{path}'
$printer = '{printer}'
if (-not (Test-Path -LiteralPath $p)) {{
  [PSCustomObject]@{{ ok=$false; message='File not found' }} | ConvertTo-Json -Compress
}} else {{
  if ($printer) {{
    Start-Process -FilePath $p -Verb PrintTo -ArgumentList $printer -ErrorAction SilentlyContinue
  }} else {{
    Start-Process -FilePath $p -Verb Print -ErrorAction SilentlyContinue
  }}
  [PSCustomObject]@{{ ok=$true; path=$p; printer=$(if ($printer) {{ $printer }} else {{ 'default' }}) }} | ConvertTo-Json -Compress
}}
""",
    },
    {
        "id": "windows.printers.cancel_job",
        "description": "Cancel print jobs on a printer (all jobs on that queue).",
        "confirm": "ask",
        "timeout": 45,
        "result": "json",
        "defaults": {"printer": ""},
        "parameters": {
            "type": "object",
            "properties": {"printer": {"type": "string"}},
        },
        "success_message": "Print jobs cancelled",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$name = '{printer}'
$printers = if ($name) {{ Get-Printer -Name $name }} else {{ Get-Printer | Where-Object Type -eq 'Local' | Select-Object -First 1 }}
if (-not $printers) {{ [PSCustomObject]@{{ ok=$false; message='Printer not found' }} | ConvertTo-Json -Compress }}
else {{
  $jobs = Get-PrintJob -PrinterName $printers.Name
  $jobs | Remove-PrintJob
  [PSCustomObject]@{{ ok=$true; printer=$printers.Name; cancelled=@($jobs).Count }} | ConvertTo-Json -Compress
}}
""",
    },
    {
        "id": "windows.printers.clear_queue",
        "description": "Clear all jobs from a printer queue after confirmation.",
        "confirm": "destructive",
        "timeout": 45,
        "result": "json",
        "defaults": {"printer": ""},
        "parameters": {
            "type": "object",
            "properties": {"printer": {"type": "string"}},
        },
        "success_message": "Queue cleared",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$name = '{printer}'
$pr = if ($name) {{ Get-Printer -Name $name }} else {{ Get-Printer | Select-Object -First 1 }}
if (-not $pr) {{ [PSCustomObject]@{{ ok=$false; message='Printer not found' }} | ConvertTo-Json -Compress }}
else {{
  $n = @(Get-PrintJob -PrinterName $pr.Name).Count
  Get-PrintJob -PrinterName $pr.Name | Remove-PrintJob
  [PSCustomObject]@{{ ok=$true; printer=$pr.Name; cleared=$n }} | ConvertTo-Json -Compress
}}
""",
    },
    {
        "id": "windows.printers.troubleshoot",
        "description": "Launch the Windows printer troubleshooter.",
        "confirm": "none",
        "timeout": 20,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"Start-Process 'ms-settings:printers'",
    },

    # ---------- System reports ----------
    {
        "id": "windows.system.health_report",
        "description": "Summarize common system issues (disk, memory, reliability signals).",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Health report",
        "script": r"""
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {{
  [PSCustomObject]@{{ drive=$_.DeviceID; free_gb=[math]::Round($_.FreeSpace/1GB,1); total_gb=[math]::Round($_.Size/1GB,1) }}
}}
$os = Get-CimInstance Win32_OperatingSystem
$memFree = [math]::Round($os.FreePhysicalMemory/1MB,1)
$memTotal = [math]::Round($os.TotalVisibleMemorySize/1MB,1)
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
[PSCustomObject]@{{
  memory_free_gb = $memFree
  memory_total_gb = $memTotal
  memory_used_pct = if ($memTotal -gt 0) {{ [math]::Round((1 - $memFree/$memTotal)*100,1) }} else {{ 0 }}
  cpu_load_pct = $cpu
  disks = @($disk)
  last_boot = $os.LastBootUpTime
}} | ConvertTo-Json -Compress -Depth 4
""",
    },
    {
        "id": "windows.system.storage_report",
        "description": "Explain disk usage by drive (free/total).",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Storage report",
        "script": r"""
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {{
  [PSCustomObject]@{{
    drive = $_.DeviceID
    free_gb = [math]::Round($_.FreeSpace/1GB,2)
    total_gb = [math]::Round($_.Size/1GB,2)
    used_pct = if ($_.Size -gt 0) {{ [math]::Round((($_.Size-$_.FreeSpace)/$_.Size)*100,1) }} else {{ 0 }}
  }}
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.system.memory_report",
        "description": "Identify RAM pressure and top memory consumers.",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Memory report",
        "script": r"""
$os = Get-CimInstance Win32_OperatingSystem
$top = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 8 |
  ForEach-Object {{ [PSCustomObject]@{{ name=$_.Name; pid=$_.Id; mb=[math]::Round($_.WorkingSet64/1MB,1) }} }}
[PSCustomObject]@{{
  free_gb = [math]::Round($os.FreePhysicalMemory/1MB,2)
  total_gb = [math]::Round($os.TotalVisibleMemorySize/1MB,2)
  top = @($top)
}} | ConvertTo-Json -Compress -Depth 4
""",
    },
    {
        "id": "windows.system.cpu_report",
        "description": "Identify sustained CPU usage and top CPU processes.",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "CPU report",
        "script": r"""
$load = (Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average
$top = Get-Process | Sort-Object CPU -Descending | Select-Object -First 8 |
  ForEach-Object {{ [PSCustomObject]@{{ name=$_.Name; pid=$_.Id; cpu=$_.CPU }} }}
[PSCustomObject]@{{ cpu_load_pct=$load; top=@($top) }} | ConvertTo-Json -Compress -Depth 4
""",
    },
    {
        "id": "windows.system.startup_apps.list",
        "description": "List startup apps that may slow boot.",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Startup apps",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = @()
$runKeys = @(
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'
)
foreach ($k in $runKeys) {{
  if (Test-Path $k) {{
    Get-ItemProperty $k | ForEach-Object {{
      $_.PSObject.Properties | Where-Object {{ $_.Name -notmatch '^PS' }} | ForEach-Object {{
        $items += [PSCustomObject]@{{ name=$_.Name; command=[string]$_.Value; hive=$k }}
      }}
    }}
  }}
}}
@($items) | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.system.startup_apps.set_enabled",
        "description": "Open Task Manager Startup apps page to enable/disable startup items.",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"name": "", "enabled": True},
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "enabled": {"type": "boolean"},
            },
        },
        "script": r"Start-Process 'taskmgr' -ArgumentList '/0 /startup'",
    },
    {
        "id": "windows.system.event_logs.search",
        "description": "Find recent System/Application errors matching a query.",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {"query": "error", "count": 15},
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer"},
            },
        },
        "success_message": "Event log hits",
        "script": r"""
$count = [Math]::Max(1, [Math]::Min(50, {count}))
$q = '{query}'.ToLower()
$events = Get-WinEvent -LogName System,Application -MaxEvents 200 -EA SilentlyContinue |
  Where-Object {{ $_.LevelDisplayName -in @('Error','Warning') -and ($_.Message -and $_.Message.ToLower().Contains($q)) }} |
  Select-Object -First $count TimeCreated, Id, LevelDisplayName, ProviderName, Message
@($events | ForEach-Object {{
  [PSCustomObject]@{{
    time = $_.TimeCreated.ToString('s')
    id = $_.Id
    level = $_.LevelDisplayName
    provider = $_.ProviderName
    message = ($_.Message -replace '\s+',' ').Substring(0, [Math]::Min(180, ($_.Message -replace '\s+',' ').Length))
  }}
}}) | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.system.update.status",
        "description": "Check Windows Update last status (COM API best-effort).",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Update status",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
try {{
  $session = New-Object -ComObject Microsoft.Update.Session
  $searcher = $session.CreateUpdateSearcher()
  $history = $searcher.GetTotalHistoryCount()
  $last = if ($history -gt 0) {{ $searcher.QueryHistory(0,1) | Select-Object -First 1 }} else {{ $null }}
  [PSCustomObject]@{{
    history_count = $history
    last_title = if ($last) {{ $last.Title }} else {{ $null }}
    last_date = if ($last) {{ $last.Date.ToString('s') }} else {{ $null }}
    last_result = if ($last) {{ $last.ResultCode }} else {{ $null }}
  }} | ConvertTo-Json -Compress
}} catch {{
  [PSCustomObject]@{{ ok=$false; message=$_.Exception.Message; hint='ms-settings:windowsupdate' }} | ConvertTo-Json -Compress
}}
""",
    },
    {
        "id": "windows.system.update.check",
        "description": "Open Windows Update settings to check for updates.",
        "confirm": "none",
        "timeout": 20,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"Start-Process 'ms-settings:windowsupdate'",
    },
    {
        "id": "windows.system.restore_point.create",
        "description": "Create a system restore point when supported (may need admin).",
        "confirm": "ask",
        "timeout": 120,
        "result": "json",
        "defaults": {"description": "OS Agent restore point"},
        "parameters": {
            "type": "object",
            "properties": {"description": {"type": "string"}},
        },
        "success_message": "Restore point",
        "script": r"""
$ErrorActionPreference = 'Stop'
try {{
  Checkpoint-Computer -Description '{description}' -RestorePointType MODIFY_SETTINGS
  [PSCustomObject]@{{ ok=$true; description='{description}' }} | ConvertTo-Json -Compress
}} catch {{
  [PSCustomObject]@{{ ok=$false; message=$_.Exception.Message }} | ConvertTo-Json -Compress
}}
""",
    },
    {
        "id": "windows.system.reboot",
        "description": "Restart the computer after explicit confirmation.",
        "confirm": "destructive",
        "timeout": 20,
        "result": "text",
        "defaults": {"delay_seconds": 30},
        "parameters": {
            "type": "object",
            "properties": {"delay_seconds": {"type": "integer"}},
        },
        "script": r"shutdown /r /t {delay_seconds} /c 'OS Agent restart'",
    },
    {
        "id": "windows.system.shutdown",
        "description": "Shut down the computer after explicit confirmation.",
        "confirm": "destructive",
        "timeout": 20,
        "result": "text",
        "defaults": {"delay_seconds": 30},
        "parameters": {
            "type": "object",
            "properties": {"delay_seconds": {"type": "integer"}},
        },
        "script": r"shutdown /s /t {delay_seconds} /c 'OS Agent shutdown'",
    },

    # ---------- Screenshot / notifications / datetime / power ----------
    # clipboard set/clear are Python tools (safe escaping) in windows.py
    {
        "id": "windows.screenshot.capture",
        "description": "Capture the virtual desktop to a PNG under config/screenshots.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Screenshot captured",
        "script": r"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$dir = Join-Path $env:USERPROFILE '.osagent\screenshots'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$path = Join-Path $dir ("shot-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".png")
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save($path)
$g.Dispose(); $bmp.Dispose()
[PSCustomObject]@{{ ok=$true; path=$path }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.screenshot.capture_region",
        "description": "Capture a rectangular screen region (x,y,width,height) to PNG.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {"x": 0, "y": 0, "width": 800, "height": 600},
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
        },
        "success_message": "Region captured",
        "script": r"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$dir = Join-Path $env:USERPROFILE '.osagent\screenshots'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$path = Join-Path $dir ("region-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".png")
$x={x}; $y={y}; $w=[Math]::Max(1,{width}); $h=[Math]::Max(1,{height})
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size($w,$h)))
$bmp.Save($path)
$g.Dispose(); $bmp.Dispose()
[PSCustomObject]@{{ ok=$true; path=$path; x=$x; y=$y; width=$w; height=$h }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.notifications.list",
        "description": "Open Notification Center (enumeration APIs vary by Windows build).",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Notifications",
        "script": r"""
[PSCustomObject]@{{ ok=$true; message='Use Action Center (Win+N); programmatic list is limited without private APIs' }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.notifications.dismiss",
        "description": "Best-effort: focus notification area (full dismiss needs private APIs).",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Notifications",
        "script": r"""
[PSCustomObject]@{{ ok=$true; message='Open Action Center (Win+N) to dismiss; no stable public dismiss-all API' }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.datetime.get",
        "description": "Get current local date and time.",
        "confirm": "none",
        "timeout": 10,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Date/time",
        "script": r"""
$n = Get-Date
[PSCustomObject]@{{
  local = $n.ToString('s')
  display = $n.ToString('F')
  timezone = [TimeZoneInfo]::Local.DisplayName
  utc = $n.ToUniversalTime().ToString('s')
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.power.get_plan",
        "description": "Inspect the active power plan.",
        "confirm": "none",
        "timeout": 20,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"powercfg /getactivescheme",
    },
    {
        "id": "windows.power.set_plan",
        "description": "Set power plan by scheme GUID or open power settings.",
        "confirm": "ask",
        "timeout": 30,
        "result": "text",
        "defaults": {"scheme": ""},
        "parameters": {
            "type": "object",
            "properties": {
                "scheme": {"type": "string", "description": "GUID or balanced|power_saver|high_performance"},
            },
        },
        "script": r"""
$s = '{scheme}'.ToLower()
if (-not $s) {{ Start-Process 'ms-settings:powersleep'; 'opened settings'; exit 0 }}
$map = @{{
  'balanced' = '381b4222-f694-41f0-9685-ff5bb260df2e'
  'power_saver' = 'a1841308-3541-4fab-bc81-f71556f20b4a'
  'high_performance' = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
}}
$guid = if ($map.ContainsKey($s)) {{ $map[$s] }} else {{ '{scheme}' }}
powercfg /setactive $guid
""",
    },
    {
        "id": "windows.battery.set_battery_saver",
        "description": "Open Battery saver settings (toggle requires Settings UI on modern Windows).",
        "confirm": "ask",
        "timeout": 20,
        "result": "text",
        "defaults": {"enabled": True},
        "parameters": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
        },
        "script": r"Start-Process 'ms-settings:batterysaver'",
    },
]
# fmt: on
