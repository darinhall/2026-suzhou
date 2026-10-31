"""网络小工具：找出本机每个网卡的广播地址（中枢发 beacon、discover.py 发询问都用它）。

为什么不直接用 255.255.255.255：有 VPN 的时候默认路由可能走隧道，限制广播会发到隧道里去。
子网广播地址（比如 10.128.9.255）只会走对应网卡，所以优先用它。
"""

import re
import subprocess
import sys


def _run(*cmd) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def broadcast_addrs() -> list[str]:
    """每个有广播地址的 IPv4 网卡的子网广播；找不到就退回 255.255.255.255。"""
    found: list[str] = []
    if sys.platform == "darwin" or sys.platform.startswith(("freebsd", "openbsd")):
        found = re.findall(r"inet \d+\.\d+\.\d+\.\d+ netmask \S+ broadcast (\d+\.\d+\.\d+\.\d+)", _run("ifconfig"))
    elif sys.platform.startswith("linux"):
        found = re.findall(r"inet \d+\.\d+\.\d+\.\d+/\d+ brd (\d+\.\d+\.\d+\.\d+)", _run("ip", "-o", "-4", "addr", "show"))
    return list(dict.fromkeys(found)) or ["255.255.255.255"]
