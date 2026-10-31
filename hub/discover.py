"""找中枢：参考实现 + 测试工具（固件里的发现逻辑就是这个流程）。

    python3 hub/discover.py                 # 广播一次询问，等 3 秒，打印找到的中枢
    python3 hub/discover.py --listen        # 不问，只听中枢每 2 秒一次的广播
    python3 hub/discover.py --to 10.128.8.184   # 单播直接问某个 IP（广播被网络拦住时用来排查）

在**另一台设备**（队友的电脑）上跑才能测出广播能不能穿过 WiFi；在中枢同一台电脑上跑只能测协议。
找到了退出码 0，没找到 1。
"""

import argparse
import json
import pathlib
import socket
import sys
import time

import netutil

NET = json.loads((pathlib.Path(__file__).resolve().parent.parent / "config" / "network.json").read_text())["hub"]
QUERY = json.dumps({"t": "deskbot?", "v": 1}).encode()


def ask(targets: list[str], wait: float, listen_only: bool) -> tuple[dict[str, dict], dict[str, str]]:
    """返回 ({中枢IP: 回复内容}, {发送失败的地址: 原因})。机器人固件做的就是：发 QUERY（或只听），收到 t=hub 的包，取源 IP。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    # 只听 beacon 要绑发现端口；询问用临时端口，回复会单播回来
    s.bind(("", NET["discovery_port"] if listen_only else 0))
    found: dict[str, dict] = {}
    errors: dict[str, str] = {}
    deadline, next_send = time.time() + wait, 0.0
    while time.time() < deadline:
        if not listen_only and time.time() >= next_send:   # 每秒重发一次，丢一个包也没事
            for t in targets:
                try:
                    s.sendto(QUERY, (t, NET["discovery_port"]))
                except OSError as e:
                    errors[t] = str(e)   # 比如有 VPN 时 255.255.255.255 会 "No route to host"，子网广播照样能用
            next_send = time.time() + 1
        s.settimeout(0.3)
        try:
            data, addr = s.recvfrom(512)
        except socket.timeout:
            continue
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        if isinstance(msg, dict) and msg.get("t") == "hub" and addr[0] not in found:
            found[addr[0]] = msg
    return found, errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", action="store_true", help="只听 beacon，不发询问")
    ap.add_argument("--to", help="单播询问这个 IP")
    ap.add_argument("--wait", type=float, default=3.0)
    a = ap.parse_args()
    targets = [a.to] if a.to else netutil.broadcast_addrs() + ["255.255.255.255"]
    print(("监听中枢广播" if a.listen else f"询问 {', '.join(targets)}") + f"（UDP {NET['discovery_port']}，{a.wait:g} 秒）…")
    hubs, errors = ask(targets, a.wait, a.listen)
    for ip, m in hubs.items():
        print(f"✓ 找到中枢 {m.get('name', '?')}  ws://{ip}:{m['ws_port']}{m['path']}  " + ("需要令牌" if m.get("auth") else "不需要令牌"))
    if not hubs:
        for t, why in errors.items():
            print(f"  发往 {t} 失败：{why}")
        print("✗ 没找到。这台设备和中枢在同一个 WiFi 吗？试试 --to <中枢IP>（单播）：单播通广播不通 = 网络把广播拦了")
    sys.exit(0 if hubs else 1)
