"""Safety checks for model-proposed PowerShell (catalog gap fallback)."""

from __future__ import annotations

import re

_BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bFormat-Volume\b", re.I), "Format-Volume"),
    (re.compile(r"\bClear-Disk\b", re.I), "Clear-Disk"),
    (re.compile(r"\bInitialize-Disk\b", re.I), "Initialize-Disk"),
    (re.compile(r"\bRemove-Computer\b", re.I), "Remove-Computer"),
    (re.compile(r"\bStop-Computer\b|\bRestart-Computer\b", re.I), "shutdown/restart"),
    (re.compile(r"\brm\s+-rf\s+/", re.I), "rm -rf /"),
    (re.compile(r"\bInvoke-Expression\b|\bIEX\b", re.I), "Invoke-Expression"),
    (re.compile(r"DownloadString\s*\(|DownloadFile\s*\(", re.I), "download+execute"),
    (re.compile(r"\|\s*iex\b", re.I), "piped iex"),
    (re.compile(r"\bSet-ExecutionPolicy\b", re.I), "Set-ExecutionPolicy"),
    (re.compile(r"\bNew-Service\b|\bRemove-Service\b", re.I), "service install/remove"),
    (re.compile(r"\bnet\s+user\b|\bnet\s+localgroup\b", re.I), "local user/group changes"),
    (re.compile(
        r"Remove-Item\s+[^\n]*(-Recurse|-r)[^\n]*([A-Za-z]:)\\?\s*([;'\"\s]|$)",
        re.I,
    ), "recursive delete near drive root"),
]

_WRITE_HINTS = re.compile(
    r"\b(Remove-Item|Move-Item|New-Item|Set-Content|Add-Content|Out-File|"
    r"Rename-Item|Set-ItemProperty|Set-Service|Stop-Service|Start-Service|"
    r"Restart-Service|Disable-PnpDevice|Enable-PnpDevice|Set-Printer|"
    r"Add-Printer|Remove-Printer|Stop-Process|taskkill|"
    r"netsh\s+wlan\s+(delete|connect))\b",
    re.I,
)

_MAX_CHARS = 4000


def validate_powershell(command: str) -> tuple[bool, str, bool]:
    """Return (allowed, message, needs_confirm)."""
    cmd = (command or "").strip()
    if not cmd:
        return False, "Empty command.", False
    if len(cmd) > _MAX_CHARS:
        return False, f"Command too long (max {_MAX_CHARS} chars).", False

    for pattern, why in _BLOCK_PATTERNS:
        if pattern.search(cmd):
            return (
                False,
                f"Blocked for safety ({why}). Prefer a catalog tool or a safer command.",
                False,
            )

    return True, "ok", bool(_WRITE_HINTS.search(cmd))


# ----- Bash (Linux / WSL / antiX) -----

_BASH_BLOCK: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-[^\s]*\s+)*(/|/\*|~|/home\s*$|/home/|/var\s*$|/usr\s*$|/etc\s*$)", re.I), "rm near filesystem root"),
    (re.compile(r"\bmkfs\b|\bdd\s+.*\bof=/dev/", re.I), "disk wipe / mkfs"),
    (re.compile(r"\b(shutdown|poweroff|reboot|halt)\b", re.I), "shutdown/reboot"),
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b|\bwget\b.*\|\s*(ba)?sh\b", re.I), "download+pipe to shell"),
    (re.compile(r"\bchmod\s+-R\s+777\s+/", re.I), "chmod 777 /"),
    (re.compile(r":\(\)\{\s*:\|:&\s*\};:", re.I), "fork bomb"),
    (re.compile(r"\buserdel\b|\bpasswd\s+root\b", re.I), "account destruction"),
    (re.compile(r">\s*/etc/(passwd|shadow|sudoers)", re.I), "overwrite critical /etc file"),
]

_BASH_WRITE = re.compile(
    r"\b(rm|mv|cp|chmod|chown|chgrp|mkdir|rmdir|touch|truncate|dd|"
    r"apt(-get)?|dpkg|systemctl|service|kill|pkill|killall|"
    r"useradd|usermod|crontab|iptables|nft|ufw|mount|umount|"
    r"tee|sed\s+-i|perl\s+-i)\b",
    re.I,
)


def validate_bash(command: str) -> tuple[bool, str, bool]:
    """Return (allowed, message, needs_confirm) for a bash one-liner."""
    cmd = (command or "").strip()
    if not cmd:
        return False, "Empty command.", False
    if len(cmd) > _MAX_CHARS:
        return False, f"Command too long (max {_MAX_CHARS} chars).", False
    for pattern, why in _BASH_BLOCK:
        if pattern.search(cmd):
            return (
                False,
                f"Blocked for safety ({why}). Prefer a catalog tool or a safer command.",
                False,
            )
    return True, "ok", bool(_BASH_WRITE.search(cmd))
