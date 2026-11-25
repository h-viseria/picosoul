"""
Declarative Linux command catalog (Debian / Ubuntu / antiX / WSL).

Each entry becomes a tool. Scripts are bash templates; placeholders use
str.format (escape literal braces as {{ }}). Prefer emitting JSON via python3.
"""

from __future__ import annotations

# fmt: off
COMMANDS: list[dict] = [
    # ---------- Files ----------
    {
        "id": "files.find_recent",
        "description": (
            "Find newest files under Desktop/Documents/Downloads/Pictures "
            "(or path=). Use for 'latest file I edited'."
        ),
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "engine": "bash",
        "defaults": {"path": "", "count": 5, "extension": "", "depth": 6},
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "count": {"type": "integer"},
                "extension": {"type": "string"},
                "depth": {"type": "integer"},
            },
        },
        "success_message": "Newest files",
        "phrases": [
            r"\b(latest|newest|recent|last)\b.*\bfiles?\b",
            r"\bfiles?\b.*\b(latest|newest|recent|last\s+updated)\b",
        ],
        "script": r'''
python3 - <<'PY'
import json, os
from pathlib import Path
count = max(1, min(30, int("{count}" or 5)))
depth = max(1, min(12, int("{depth}" or 6)))
ext = "{extension}".strip().lstrip(".")
custom = "{path}".strip()
home = Path.home()
if custom:
    roots = [Path(custom).expanduser()]
else:
    roots = [home/"Desktop", home/"Documents", home/"Downloads", home/"Pictures", home/"Videos"]
    # WSL: Windows profile is where real user files live
    users = Path("/mnt/c/Users")
    if users.is_dir():
        import re as _re
        lu = _re.sub(r"[^a-z0-9]+", "", home.name.lower())
        try:
            entries = list(users.iterdir())
        except OSError:
            entries = []
        for entry in entries:
            try:
                if not entry.is_dir() or entry.name in {{"Public","Default","Default User","All Users"}}:
                    continue
                dl = entry/"Downloads"
                if not dl.is_dir():
                    continue
            except OSError:
                continue
            wu = _re.sub(r"[^a-z0-9]+", "", entry.name.lower())
            if lu and (lu == wu or lu in wu or wu in lu):
                roots = [entry/"Desktop", entry/"Documents", entry/"Downloads", entry/"Pictures", entry/"Videos", entry/"OneDrive", *roots]
                break
exclude = {{".git","node_modules",".venv","venv","__pycache__",".cache","AppData"}}
hits = []
for root in roots:
    if not root.is_dir():
        continue
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) > depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath)/fn
            if ext and p.suffix.lower() != "."+ext.lower():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            hits.append((st.st_mtime, str(p), st.st_size, p.suffix.lower()))
hits.sort(key=lambda x: -x[0])
from datetime import datetime
out = []
for mtime, path, size, suf in hits[:count]:
    out.append({{
        "path": path,
        "last_write": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "size_bytes": size,
        "extension": suf,
    }})
print(json.dumps(out))
PY
''',
    },
    {
        "id": "files.find_by_name",
        "description": "Search files/folders by name substring under common folders or path=.",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "engine": "bash",
        "defaults": {"path": "", "pattern": "", "count": 20, "depth": 6},
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "count": {"type": "integer"},
                "depth": {"type": "integer"},
            },
            "required": ["pattern"],
        },
        "success_message": "Name search matches",
        "phrases": [r"\bfind\s+file\s+named\b", r"\bsearch\s+for\s+file\b"],
        "script": r'''
python3 - <<'PY'
import json, os
from pathlib import Path
count = max(1, min(50, int("{count}" or 20)))
depth = max(1, min(12, int("{depth}" or 6)))
pattern = "{pattern}".strip().lower()
custom = "{path}".strip()
home = Path.home()
roots = [Path(custom).expanduser()] if custom else [home/"Desktop", home/"Documents", home/"Downloads", home/"Pictures"]
exclude = {{".git","node_modules",".venv","venv","__pycache__",".cache"}}
out = []
for root in roots:
    if not root.is_dir():
        continue
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) > depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith(".")]
        for name in dirnames + filenames:
            if pattern and pattern not in name.lower():
                continue
            p = Path(dirpath)/name
            out.append({{"path": str(p), "name": name, "is_dir": p.is_dir()}})
            if len(out) >= count:
                break
        if len(out) >= count:
            break
print(json.dumps(out))
PY
''',
    },
    {
        "id": "files.disk_free",
        "description": "Disk free space as JSON (df).",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Disk space",
        "phrases": [r"\bdisk\s+(free|space|usage)\b", r"\bdf\s+-h\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil
from pathlib import Path
rows = []
seen = set()
# Prefer df -P for portable parsing
import subprocess
code, out, _ = 0, "", ""
try:
    p = subprocess.run(["df","-P","-B1"], capture_output=True, text=True, timeout=10)
    code, out = p.returncode, p.stdout or ""
except Exception as e:
    print(json.dumps([{{"error": str(e)}}])); raise SystemExit
for line in out.splitlines()[1:]:
    parts = line.split()
    if len(parts) < 6:
        continue
    fs, total, used, avail, pct, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
    if mount in seen or mount.startswith("/mnt/wsl") and "docker" in mount:
        pass
    seen.add(mount)
    try:
        total_i, avail_i = int(total), int(avail)
    except ValueError:
        continue
    if total_i <= 0:
        continue
    rows.append({{
        "drive": mount,
        "filesystem": fs,
        "total_gb": round(total_i/1e9, 2),
        "free_gb": round(avail_i/1e9, 2),
        "used_pct": pct.rstrip("%"),
    }})
print(json.dumps(rows))
PY
''',
    },
    # ---------- System reports ----------
    {
        "id": "linux.system.health_report",
        "description": "Quick health: load, memory, disk root, failed units count.",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Health report",
        "phrases": [r"\b(system\s+health|health\s+report|system\s+status)\b"],
        "script": r'''
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (p.stdout or "").strip()
    except Exception as e:
        return str(e)

load = Path("/proc/loadavg").read_text().split()[:3] if Path("/proc/loadavg").is_file() else []
mem = {{}}
for line in Path("/proc/meminfo").read_text().splitlines()[:5] if Path("/proc/meminfo").is_file() else []:
    k,v = line.split(":")
    mem[k.strip()] = v.strip()
failed = 0
out = run(["systemctl","--failed","--no-pager","--plain"])
if out and "0 loaded units" not in out.lower():
    failed = max(0, len([ln for ln in out.splitlines() if ln.strip() and not ln.startswith("UNIT")]))
root = {{}}
try:
    u = os.statvfs("/")
    root = {{"total_gb": round(u.f_blocks*u.f_frsize/1e9,2), "free_gb": round(u.f_bavail*u.f_frsize/1e9,2)}}
except Exception:
    pass
print(json.dumps([{{
    "loadavg": load,
    "memory": mem,
    "root_disk": root,
    "failed_units": failed,
    "uptime": run(["uptime","-p"]),
}}]))
PY
''',
    },
    {
        "id": "linux.system.storage_report",
        "description": "Block devices and mounts (lsblk + df summary).",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Storage report",
        "phrases": [r"\b(storage\s+report|list\s+disks|block\s+devices|lsblk)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (p.stdout or "").strip()
    except Exception as e:
        return str(e)
print(json.dumps([{{
    "lsblk": run(["lsblk","-o","NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT"]),
    "df": run(["df","-h","-x","tmpfs","-x","devtmpfs"]),
}}]))
PY
''',
    },
    {
        "id": "linux.system.memory_report",
        "description": "Detailed memory report (/proc/meminfo + free).",
        "confirm": "none",
        "timeout": 10,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Memory report",
        "phrases": [r"\b(memory\s+report|ram\s+report)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
from pathlib import Path
mem = {{}}
for line in Path("/proc/meminfo").read_text().splitlines()[:20]:
    k,v = line.split(":",1)
    mem[k.strip()] = v.strip()
try:
    free = subprocess.run(["free","-h"], capture_output=True, text=True, timeout=5).stdout
except Exception:
    free = ""
print(json.dumps([{{"meminfo": mem, "free": free}}]))
PY
''',
    },
    {
        "id": "linux.system.cpu_report",
        "description": "CPU model, cores, and load.",
        "confirm": "none",
        "timeout": 10,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "CPU report",
        "phrases": [r"\b(cpu\s+report|cpu\s+info|processor\s+info)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
from pathlib import Path
model = ""
for line in Path("/proc/cpuinfo").read_text().splitlines():
    if line.startswith("model name"):
        model = line.split(":",1)[1].strip(); break
try:
    nproc = subprocess.run(["nproc"], capture_output=True, text=True, timeout=5).stdout.strip()
except Exception:
    nproc = "?"
load = Path("/proc/loadavg").read_text().split()[:3] if Path("/proc/loadavg").is_file() else []
print(json.dumps([{{"model": model, "cores": nproc, "loadavg": load}}]))
PY
''',
    },
    {
        "id": "linux.datetime.get",
        "description": "Current date/time and timezone.",
        "confirm": "none",
        "timeout": 5,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Date/time",
        "phrases": [r"\b(what\s+time|current\s+time|date\s+and\s+time|timezone)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess, time
from datetime import datetime
tz = time.tzname
try:
    td = subprocess.run(["timedatectl"], capture_output=True, text=True, timeout=5).stdout.strip()
except Exception:
    td = ""
now = datetime.now().isoformat(timespec="seconds")
print(json.dumps([{{"local": now, "display": now, "timezone": " ".join(tz), "timedatectl": td[:500]}}]))
PY
''',
    },
    # ---------- Packages ----------
    {
        "id": "linux.packages.upgradable",
        "description": "List packages with available upgrades (apt).",
        "confirm": "none",
        "timeout": 120,
        "result": "json",
        "engine": "bash",
        "defaults": {"limit": 40},
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
        "success_message": "Upgradable packages",
        "phrases": [
            r"\b(upgradable|upgradeable)\s+packages\b",
            r"\bpackages?\s+(to\s+)?upgrade\b",
            r"\bpending\s+updates\b",
        ],
        "script": r'''
python3 - <<'PY'
import json, subprocess
limit = max(1, min(200, int("{limit}" or 40)))
try:
    p = subprocess.run(["apt","list","--upgradable"], capture_output=True, text=True, timeout=90)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln and not ln.startswith("Listing")]
except Exception as e:
    lines = [str(e)]
out = []
for ln in lines[:limit]:
    name = ln.split("/",1)[0].strip()
    out.append({{"package": name, "raw": ln[:200]}})
print(json.dumps(out))
PY
''',
    },
    {
        "id": "linux.packages.autoremove_preview",
        "description": "Show packages apt would autoremove (dry view).",
        "confirm": "none",
        "timeout": 60,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Autoremove candidates",
        "phrases": [r"\b(autoremove|unused\s+packages)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
try:
    p = subprocess.run(["apt-get","-s","autoremove"], capture_output=True, text=True, timeout=60)
    text = (p.stdout or "") + "\n" + (p.stderr or "")
except Exception as e:
    text = str(e)
pkgs = []
for ln in text.splitlines():
    if "Remv " in ln or ln.strip().startswith("Remv"):
        pkgs.append({{"line": ln.strip()[:200]}})
print(json.dumps(pkgs or [{{"summary": text[-1500:]}}]))
PY
''',
    },
    # ---------- Services / journal ----------
    {
        "id": "linux.service.failed",
        "description": "List failed systemd units.",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Failed units",
        "phrases": [r"\b(failed\s+services|failed\s+units)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
try:
    p = subprocess.run(["systemctl","--failed","--no-pager","--plain","--no-legend"], capture_output=True, text=True, timeout=15)
    rows = []
    for ln in (p.stdout or "").splitlines():
        parts = ln.split()
        if parts:
            rows.append({{"unit": parts[0], "raw": ln[:200]}})
    print(json.dumps(rows))
except Exception as e:
    print(json.dumps([{{"error": str(e)}}]))
PY
''',
    },
    {
        "id": "linux.logs.journal_search",
        "description": "Search journalctl for a query (optional unit=).",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "engine": "bash",
        "defaults": {"query": "", "unit": "", "lines": 50},
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "unit": {"type": "string"},
                "lines": {"type": "integer"},
            },
        },
        "success_message": "Journal matches",
        "phrases": [r"\b(search\s+logs|journal\s+search|journalctl)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
query = "{query}".strip()
unit = "{unit}".strip()
lines = max(1, min(200, int("{lines}" or 50)))
cmd = ["journalctl","--no-pager","-n",str(lines)]
if unit:
    cmd.extend(["-u", unit])
if query:
    cmd.extend(["-g", query])
try:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    text = (p.stdout or p.stderr or "")[-8000:]
    print(json.dumps([{{"lines": text.splitlines()[-lines:], "exit": p.returncode}}]))
except Exception as e:
    print(json.dumps([{{"error": str(e)}}]))
PY
''',
    },
    # ---------- Network / firewall ----------
    {
        "id": "linux.firewall.status",
        "description": "Firewall status (ufw or firewalld).",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Firewall status",
        "phrases": [r"\b(firewall\s+status|ufw\s+status)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        return p.returncode, (p.stdout or p.stderr or "").strip()
    except Exception as e:
        return 1, str(e)
if shutil.which("ufw"):
    code, out = run(["ufw","status","verbose"])
    print(json.dumps([{{"tool":"ufw","exit":code,"status":out}}]))
elif shutil.which("firewall-cmd"):
    code, out = run(["firewall-cmd","--state"])
    code2, zones = run(["firewall-cmd","--list-all"])
    print(json.dumps([{{"tool":"firewalld","state":out,"detail":zones}}]))
else:
    print(json.dumps([{{"tool":"none","status":"No ufw/firewalld found"}}]))
PY
''',
    },
    {
        "id": "linux.network.wifi_list",
        "description": "List Wi-Fi networks via nmcli (when NetworkManager available).",
        "confirm": "none",
        "timeout": 30,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Wi-Fi networks",
        "phrases": [r"\b(wifi\s+networks|list\s+wifi|wireless\s+networks)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
if not shutil.which("nmcli"):
    print(json.dumps([{{"error":"nmcli not available (common on WSL)"}}]))
else:
    p = subprocess.run(["nmcli","-t","-f","SSID,SIGNAL,SECURITY","dev","wifi"], capture_output=True, text=True, timeout=25)
    rows = []
    for ln in (p.stdout or "").splitlines():
        parts = ln.split(":")
        if parts and parts[0]:
            rows.append({{"ssid": parts[0], "signal": parts[1] if len(parts)>1 else "", "security": parts[2] if len(parts)>2 else ""}})
    print(json.dumps(rows[:40]))
PY
''',
    },
    {
        "id": "linux.network.wifi_status",
        "description": "Current NetworkManager device/connection status.",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Wi-Fi / NM status",
        "phrases": [r"\b(wifi\s+status|networkmanager\s+status)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
if not shutil.which("nmcli"):
    print(json.dumps([{{"error":"nmcli not available"}}]))
else:
    p = subprocess.run(["nmcli","-t","general","status"], capture_output=True, text=True, timeout=10)
    p2 = subprocess.run(["nmcli","-t","connection","show","--active"], capture_output=True, text=True, timeout=10)
    print(json.dumps([{{"general": (p.stdout or "").strip(), "active": (p2.stdout or "").strip().splitlines()}}]))
PY
''',
    },
    {
        "id": "linux.network.dns_flush",
        "description": "Flush DNS caches (resolvectl or nscd) when available.",
        "confirm": "ask",
        "timeout": 20,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "DNS flush",
        "phrases": [r"\b(flush\s+dns|dns\s+cache\s+clear)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
msgs = []
for cmd in (["resolvectl","flush-caches"], ["systemd-resolve","--flush-caches"]):
    if shutil.which(cmd[0]):
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        msgs.append({{"cmd":" ".join(cmd), "exit": p.returncode, "out": (p.stdout or p.stderr or "")[:300]}})
        break
else:
    msgs.append({{"status":"no resolvectl/systemd-resolve"}})
print(json.dumps(msgs))
PY
''',
    },
    {
        "id": "linux.network.test_connectivity",
        "description": "Ping 1.1.1.1 and resolve example.com.",
        "confirm": "none",
        "timeout": 25,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Connectivity test",
        "phrases": [r"\b(test\s+connectivity|check\s+internet|am\s+i\s+online)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        return p.returncode, (p.stdout or p.stderr or "")[:400]
    except Exception as e:
        return 1, str(e)
c1, o1 = run(["ping","-c","2","-W","2","1.1.1.1"])
c2, o2 = run(["getent","hosts","example.com"])
print(json.dumps([{{"ping_1_1_1_1": {{"exit": c1, "out": o1}}, "dns_example_com": {{"exit": c2, "out": o2}}}}]))
PY
''',
    },
    # ---------- Mounts / cron / docker ----------
    {
        "id": "linux.mounts.list",
        "description": "List mounts (findmnt or /proc/mounts).",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Mounts",
        "phrases": [r"\b(list\s+mounts|show\s+mounts|mounted\s+filesystems)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
if shutil.which("findmnt"):
    p = subprocess.run(["findmnt","-J"], capture_output=True, text=True, timeout=10)
    try:
        data = json.loads(p.stdout or "{{}}")
        filesystems = data.get("filesystems") or []
        print(json.dumps(filesystems[:80] if isinstance(filesystems, list) else [data]))
    except Exception:
        print(json.dumps([{{"raw": (p.stdout or "")[:2000]}}]))
else:
    rows = []
    for ln in open("/proc/mounts"):
        parts = ln.split()
        if len(parts) >= 3:
            rows.append({{"source": parts[0], "target": parts[1], "fstype": parts[2]}})
    print(json.dumps(rows[:80]))
PY
''',
    },
    {
        "id": "linux.cron.list",
        "description": "List current user crontab and /etc/cron.d names.",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Cron",
        "phrases": [r"\b(list\s+cron|crontab|scheduled\s+jobs)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
from pathlib import Path
try:
    p = subprocess.run(["crontab","-l"], capture_output=True, text=True, timeout=8)
    user_cron = (p.stdout or p.stderr or "").splitlines()
except Exception as e:
    user_cron = [str(e)]
system = [p.name for p in Path("/etc/cron.d").glob("*")] if Path("/etc/cron.d").is_dir() else []
print(json.dumps([{{"user_crontab": user_cron, "cron_d": system}}]))
PY
''',
    },
    {
        "id": "linux.docker.ps",
        "description": "List Docker containers if docker is installed.",
        "confirm": "none",
        "timeout": 20,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Docker containers",
        "phrases": [r"\b(docker\s+ps|list\s+containers|running\s+containers)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
if not shutil.which("docker"):
    print(json.dumps([{{"error":"docker not installed"}}]))
else:
    p = subprocess.run(["docker","ps","-a","--format","{{{{json .}}}}"], capture_output=True, text=True, timeout=15)
    rows = []
    for ln in (p.stdout or "").splitlines():
        try:
            rows.append(json.loads(ln))
        except Exception:
            rows.append({{"raw": ln}})
    print(json.dumps(rows[:50] or [{{"status":"no containers","stderr": (p.stderr or "")[:300]}}]))
PY
''',
    },
    {
        "id": "linux.env.list_user",
        "description": "List selected user environment variables (safe subset).",
        "confirm": "none",
        "timeout": 5,
        "result": "json",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Environment",
        "phrases": [r"\b(env\s+vars|environment\s+variables|show\s+path)\b"],
        "script": r'''
python3 - <<'PY'
import json, os
keys = ["HOME","USER","SHELL","PATH","LANG","DISPLAY","WAYLAND_DISPLAY","XDG_SESSION_TYPE","WSL_DISTRO_NAME"]
print(json.dumps([{{k: os.environ.get(k) for k in keys}}]))
PY
''',
    },
    {
        "id": "linux.users.last_logins",
        "description": "Recent logins (last -n).",
        "confirm": "none",
        "timeout": 10,
        "result": "json",
        "engine": "bash",
        "defaults": {"count": 15},
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        },
        "success_message": "Recent logins",
        "phrases": [r"\b(last\s+logins?|recent\s+logins?|login\s+history)\b"],
        "script": r'''
python3 - <<'PY'
import json, shutil, subprocess
n = max(1, min(50, int("{count}" or 15)))
if shutil.which("last"):
    p = subprocess.run(["last","-n",str(n)], capture_output=True, text=True, timeout=8)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip()][:n]
    print(json.dumps([{{"line": ln}} for ln in lines]))
else:
    print(json.dumps([{{"error":"last not available"}}]))
PY
''',
    },
    {
        "id": "linux.processes.top",
        "description": "Top CPU processes as JSON.",
        "confirm": "none",
        "timeout": 15,
        "result": "json",
        "engine": "bash",
        "defaults": {"count": 15},
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        },
        "success_message": "Top processes",
        "phrases": [r"\b(top\s+processes|cpu\s+hogs|highest\s+cpu)\b"],
        "script": r'''
python3 - <<'PY'
import json, subprocess
n = max(1, min(50, int("{count}" or 15)))
p = subprocess.run(["ps","aux","--sort=-%cpu"], capture_output=True, text=True, timeout=10)
lines = (p.stdout or "").splitlines()
header = lines[0] if lines else ""
rows = []
for ln in lines[1:n+1]:
    parts = ln.split(None, 10)
    if len(parts) >= 11:
        rows.append({{"user": parts[0], "pid": parts[1], "cpu": parts[2], "mem": parts[3], "command": parts[10][:160]}})
print(json.dumps(rows))
PY
''',
    },
    {
        "id": "linux.system.reboot",
        "description": "Reboot the machine (requires privileges).",
        "confirm": "destructive",
        "timeout": 10,
        "result": "text",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Reboot requested",
        "phrases": [r"^\s*(reboot|restart\s+(the\s+)?(computer|machine|system))\s*$"],
        "script": r'''
if command -v systemctl >/dev/null 2>&1; then
  sudo -n systemctl reboot && echo ok || systemctl reboot && echo ok
else
  sudo -n reboot && echo ok || reboot && echo ok
fi
''',
    },
    {
        "id": "linux.system.shutdown",
        "description": "Shut down the machine (requires privileges).",
        "confirm": "destructive",
        "timeout": 10,
        "result": "text",
        "engine": "bash",
        "defaults": {},
        "parameters": {"type": "object", "properties": {}},
        "success_message": "Shutdown requested",
        "phrases": [r"^\s*(shutdown|power\s*off|halt)\s*$"],
        "script": r'''
if command -v systemctl >/dev/null 2>&1; then
  sudo -n systemctl poweroff && echo ok || systemctl poweroff && echo ok
else
  sudo -n poweroff && echo ok || poweroff && echo ok
fi
''',
    },
]
# fmt: on
