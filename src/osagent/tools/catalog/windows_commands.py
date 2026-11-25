"""
Maintained Windows command catalog.

Each entry becomes a tool the agent can call. Scripts are PowerShell templates;
placeholders use str.format (escape with doubled braces {{ }} for literal braces).

Add new everyday user actions here instead of one-off refusals in the model prompt.
"""

from __future__ import annotations

# fmt: off
COMMANDS: list[dict] = [
    # ---------- Files: discovery ----------
    {
        "id": "files.find_recent",
        "description": (
            "Find the most recently modified files. Default is a FAST search of "
            "Desktop/Documents/Downloads/Pictures (not entire user profile). "
            "Use for 'latest file I edited'. Pass path= to search one folder; "
            "scope=home for a deeper (slower) home scan."
        ),
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {
            "path": "",
            "count": 5,
            "extension": "",
            "scope": "quick",
            "depth": 6,
        },
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional single root folder (overrides scope)",
                },
                "count": {
                    "type": "integer",
                    "description": "How many newest files (default 5, max 30)",
                },
                "extension": {
                    "type": "string",
                    "description": "Optional extension without dot, e.g. docx, pdf",
                },
                "scope": {
                    "type": "string",
                    "description": "quick (default common folders) or home (user profile, slower)",
                },
                "depth": {
                    "type": "integer",
                    "description": "Max directory depth (default 6)",
                },
            },
        },
        "success_message": "Newest files",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$count = [Math]::Max(1, [Math]::Min(30, {count}))
$depth = [Math]::Max(1, [Math]::Min(12, {depth}))
$ext = '{extension}'.TrimStart('.')
$scope = '{scope}'.ToLower()
$custom = '{path}'

if ($custom) {{
  $roots = @($custom)
}} elseif ($scope -eq 'home') {{
  $roots = @($env:USERPROFILE)
}} else {{
  $roots = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('MyDocuments'),
    [Environment]::GetFolderPath('MyPictures'),
    (Join-Path $env:USERPROFILE 'Downloads'),
    (Join-Path $env:USERPROFILE 'Videos'),
    (Join-Path $env:USERPROFILE 'OneDrive'),
    (Join-Path $env:USERPROFILE 'OneDrive\Documents')
  ) | Where-Object {{ $_ -and (Test-Path -LiteralPath $_) }} | Select-Object -Unique
}}

$exclude = '\\(\.git|node_modules|\.venv|venv|__pycache__|\.cache|AppData)\\'
$bag = New-Object System.Collections.Generic.List[object]
foreach ($root in $roots) {{
  Get-ChildItem -LiteralPath $root -Recurse -File -Force -Depth $depth -ErrorAction SilentlyContinue |
    Where-Object {{
      ($_.FullName -notmatch $exclude) -and
      ((-not $ext) -or ($_.Extension -eq ('.' + $ext)))
    }} |
    ForEach-Object {{
      $bag.Add([PSCustomObject]@{{
        path = $_.FullName
        last_write = $_.LastWriteTime
        size_bytes = $_.Length
        extension = $_.Extension
      }}) | Out-Null
    }}
}}

$bag |
  Sort-Object last_write -Descending |
  Select-Object -First $count |
  ForEach-Object {{
    [PSCustomObject]@{{
      path = $_.path
      last_write = $_.last_write.ToString('s')
      size_bytes = $_.size_bytes
      extension = $_.extension
    }}
  }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "files.find_by_name",
        "description": (
            "Search for files/folders by name pattern under common user folders "
            "(or a given path). Example pattern: '*report*.docx'."
        ),
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {"path": "", "pattern": "*", "count": 20, "depth": 6},
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Wildcard, e.g. *.pdf or *invoice*"},
                "path": {"type": "string", "description": "Optional root folder"},
                "count": {"type": "integer", "description": "Max matches (default 20)"},
                "depth": {"type": "integer", "description": "Max depth (default 6)"},
            },
            "required": ["pattern"],
        },
        "success_message": "Name search matches",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$count = [Math]::Max(1, [Math]::Min(50, {count}))
$depth = [Math]::Max(1, [Math]::Min(12, {depth}))
$pattern = '{pattern}'
$custom = '{path}'
if ($custom) {{
  $roots = @($custom)
}} else {{
  $roots = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('MyDocuments'),
    (Join-Path $env:USERPROFILE 'Downloads'),
    [Environment]::GetFolderPath('MyPictures')
  ) | Where-Object {{ $_ -and (Test-Path -LiteralPath $_) }} | Select-Object -Unique
}}
$hits = @()
foreach ($root in $roots) {{
  $hits += Get-ChildItem -LiteralPath $root -Recurse -Force -Depth $depth -ErrorAction SilentlyContinue -Filter $pattern |
    Where-Object {{ $_.FullName -notmatch '\\AppData\\|\\\.git\\|\\node_modules\\' }} |
    Select-Object -First $count
  if ($hits.Count -ge $count) {{ break }}
}}
$hits | Select-Object -First $count | ForEach-Object {{
  [PSCustomObject]@{{
    path = $_.FullName
    type = if ($_.PSIsContainer) {{ 'dir' }} else {{ 'file' }}
    last_write = $_.LastWriteTime.ToString('s')
    size_bytes = if ($_.PSIsContainer) {{ $null }} else {{ $_.Length }}
  }}
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "files.find_largest",
        "description": (
            "Find the largest files under Desktop/Documents/Downloads "
            "(or a given path). Fast scoped search."
        ),
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "defaults": {"path": "", "count": 10, "depth": 6},
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "count": {"type": "integer"},
                "depth": {"type": "integer"},
            },
        },
        "success_message": "Largest files",
        "script": r"""
$ErrorActionPreference = 'SilentlyContinue'
$count = [Math]::Max(1, [Math]::Min(30, {count}))
$depth = [Math]::Max(1, [Math]::Min(12, {depth}))
$custom = '{path}'
if ($custom) {{
  $roots = @($custom)
}} else {{
  $roots = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('MyDocuments'),
    (Join-Path $env:USERPROFILE 'Downloads')
  ) | Where-Object {{ $_ -and (Test-Path -LiteralPath $_) }} | Select-Object -Unique
}}
$bag = New-Object System.Collections.Generic.List[object]
foreach ($root in $roots) {{
  Get-ChildItem -LiteralPath $root -Recurse -File -Force -Depth $depth -ErrorAction SilentlyContinue |
    Where-Object {{ $_.FullName -notmatch '\\AppData\\|\\\.git\\|\\node_modules\\' }} |
    ForEach-Object {{
      $bag.Add([PSCustomObject]@{{
        path = $_.FullName
        size_bytes = $_.Length
        last_write = $_.LastWriteTime
      }}) | Out-Null
    }}
}}
$bag | Sort-Object size_bytes -Descending | Select-Object -First $count | ForEach-Object {{
  [PSCustomObject]@{{
    path = $_.path
    size_bytes = $_.size_bytes
    size_mb = [math]::Round($_.size_bytes / 1MB, 2)
    last_write = $_.last_write.ToString('s')
  }}
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "files.disk_free",
        "description": "Show free/total disk space for fixed drives.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Disk free space",
        "script": r"""
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
  ForEach-Object {{
    [PSCustomObject]@{{
      drive = $_.DeviceID
      free_gb = [math]::Round($_.FreeSpace / 1GB, 2)
      total_gb = [math]::Round($_.Size / 1GB, 2)
      used_pct = if ($_.Size -gt 0) {{ [math]::Round((($_.Size - $_.FreeSpace) / $_.Size) * 100, 1) }} else {{ 0 }}
    }}
  }} | ConvertTo-Json -Compress
""",
    },

    # ---------- Network ----------
    {
        "id": "windows.wifi.list",
        "description": "List known Wi-Fi profiles and show current connection (netsh).",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Wi-Fi profiles / status",
        "script": r"""
$profiles = netsh wlan show profiles | Select-String 'All User Profile\s*:\s*(.+)$' | ForEach-Object {{ $_.Matches[0].Groups[1].Value.Trim() }}
$iface = netsh wlan show interfaces | Out-String
[PSCustomObject]@{{
  profiles = @($profiles)
  interfaces_raw = $iface.Trim()
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.wifi.status",
        "description": "Show current Wi-Fi interface status (SSID, signal, state).",
        "confirm": "none",
        "timeout": 30,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"""
netsh wlan show interfaces
""",
    },
    {
        "id": "windows.network.ipconfig",
        "description": "Show IP configuration summary (ipconfig).",
        "confirm": "none",
        "timeout": 30,
        "result": "text",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "script": r"""
ipconfig
""",
    },

    # ---------- Processes / power ----------
    {
        "id": "windows.processes.top",
        "description": "List top processes by CPU or memory usage.",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {"sort_by": "memory", "count": 15},
        "parameters": {
            "type": "object",
            "properties": {
                "sort_by": {"type": "string", "description": "cpu or memory"},
                "count": {"type": "integer"},
            },
        },
        "success_message": "Top processes",
        "script": r"""
$count = [Math]::Max(1, [Math]::Min(50, {count}))
$sort = '{sort_by}'.ToLower()
$procs = Get-Process | Where-Object {{ $_.Name -ne 'Idle' }}
if ($sort -eq 'cpu') {{
  $procs = $procs | Sort-Object CPU -Descending
}} else {{
  $procs = $procs | Sort-Object WorkingSet64 -Descending
}}
$procs | Select-Object -First $count |
  ForEach-Object {{
    [PSCustomObject]@{{
      name = $_.Name
      pid = $_.Id
      cpu = $_.CPU
      mem_mb = [math]::Round($_.WorkingSet64 / 1MB, 1)
    }}
  }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.processes.find",
        "description": "Find running processes by name substring.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {"name": ""},
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "success_message": "Matching processes",
        "script": r"""
$name = '{name}'
Get-Process | Where-Object {{ $_.Name -like ("*" + $name + "*") }} |
  ForEach-Object {{
    [PSCustomObject]@{{ name = $_.Name; pid = $_.Id; mem_mb = [math]::Round($_.WorkingSet64 / 1MB, 1) }}
  }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.battery.status",
        "description": "Show battery charge percent and status if present.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Battery status",
        "script": r"""
$b = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue
if (-not $b) {{
  [PSCustomObject]@{{ present = $false }} | ConvertTo-Json -Compress
}} else {{
  @($b) | ForEach-Object {{
    [PSCustomObject]@{{
      present = $true
      name = $_.Name
      estimated_charge_remaining = $_.EstimatedChargeRemaining
      battery_status = $_.BatteryStatus
    }}
  }} | ConvertTo-Json -Compress
}}
""",
    },

    # ---------- System / updates ----------
    {
        "id": "windows.system.uptime",
        "description": "Show last boot time and approximate uptime.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Uptime",
        "script": r"""
$os = Get-CimInstance Win32_OperatingSystem
$boot = $os.LastBootUpTime
$uptime = (Get-Date) - $boot
[PSCustomObject]@{{
  last_boot = $boot.ToString('s')
  uptime = $uptime.ToString()
  caption = $os.Caption
  version = $os.Version
}} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.clipboard.get_text",
        "description": "Read current clipboard text (if any).",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Clipboard text",
        "script": r"""
Add-Type -AssemblyName System.Windows.Forms
$t = [System.Windows.Forms.Clipboard]::GetText()
[PSCustomObject]@{{ text = $t; length = $t.Length }} | ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.services.list_running",
        "description": "List running Windows services (name + display name).",
        "confirm": "none",
        "timeout": 45,
        "result": "json",
        "defaults": {"count": 40},
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        },
        "success_message": "Running services",
        "script": r"""
$count = [Math]::Max(1, [Math]::Min(100, {count}))
Get-Service | Where-Object {{ $_.Status -eq 'Running' }} |
  Select-Object -First $count Name, DisplayName, Status |
  ConvertTo-Json -Compress
""",
    },
    {
        "id": "windows.env.list_user",
        "description": "List user environment variables (names + values, capped).",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "User environment",
        "script": r"""
Get-ChildItem Env: | Sort-Object Name | Select-Object -First 80 |
  ForEach-Object {{ [PSCustomObject]@{{ name = $_.Name; value = $_.Value }} }} |
  ConvertTo-Json -Compress
""",
    },
]
# fmt: on
