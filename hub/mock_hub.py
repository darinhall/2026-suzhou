"""假的笔记本中枢：用来联调模拟器或真机。

    pip install websockets
    python hub/mock_hub.py              # 启动时会打印局域网地址和令牌（token）
    python hub/mock_hub.py --no-auth    # 关掉令牌检查（只在自己电脑上调试时用）

机器人连上 ws://<本机IP>:8765/robot 后：
- 打印所有上行消息（hello / head_press / touch；state 太多，默认不打印）
- 在终端里输入一行 JSON 回车，就发给机器人
- 输入 demo 回车，跑一遍"飞书 @我"的小剧本；输入 weather / today / market 回车，抓一次实时数据推到屏幕（行情要 PandaAI：用 hub/run.sh 启动）；输入 token 回车，再显示一次令牌

双板（见 双板方案.md）：hello 里带 role=face（T5）或 role=body（ESP32），
face/audio 只发给 face，pose/gesture/torque 只发给 body；没报 role 的（如 sim/）收全部。

自动发现（UDP 8766，来自 config/network.json）：
- 机器人广播 {"t":"deskbot?","v":1}，中枢单播回复 {"t":"hub","v":1,"name":…,"ws_port":8765,"path":"/robot","auth":true}，
  机器人用**回复包的源 IP** 拼出 ws://<IP>:8765/robot。中枢还每 2 秒广播一次同样的消息（beacon），机器人也可以只听不问。
- 用 python3 hub/discover.py 在另一台电脑上测试（广播能不能穿过 WiFi）。discover.py --to <IP> 是单播，排查广播被拦时用。

控制台 / 镜像（模拟器网页就是控制台，也是镜像）：
- 任何已通过认证的客户端发 {"t":"relay","msg":{…}}，中枢把 msg 转给**其他**所有客户端（真机 + 别的网页）。
  模拟器打开「同步到真机」后，它自己要执行的每条指令（演示场景、动作、表情）都会这样转给真机。
- {"t":"req","what":"today"|"sky"|"market"[,"code":"300750"]}：中枢联网抓一份实时数据，作为 face 消息推给所有人。
- 真机 / 网页上行的 head_press、touch、boss 会转给其他客户端，所以网页上的演示脚本能等到真机的"按头"。
- 每次有人连上 / 断开，中枢给所有人发 {"t":"peers","face":n,"body":n,"view":n}。

令牌：
- 现场 WiFi 里有几百人，中枢没有密码的话谁都能连上来让机器人乱动，所以第一条消息必须是 hello，并带上令牌：
  {"t": "hello", "role": "face", "fw": "0.1.0", "token": "<令牌>"}
- 令牌来源：环境变量 DESKBOT_TOKEN，否则读 hub/.token，都没有就随机生成一个存进 hub/.token（已 gitignore）。
  重启中枢令牌不变，所以固件不用重新烧。
- 本机（127.0.0.1）的连接不用令牌，所以电脑上的模拟器照常能用；手机 / 板子 / 别的电脑要带。
- 同一个地址连续 5 次令牌错误，锁 30 秒。首条消息不是 hello、5 秒没发，或超过 64 KB，直接断开。
"""

import argparse
import asyncio
import hmac
import json
import os
import re
import secrets
import socket
import sys
import time
from pathlib import Path

from websockets.asyncio.server import serve

import netutil

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data"))   # data/weather.py

NET = json.loads((HERE.parent / "config" / "network.json").read_text())["hub"]
LOCAL = {"127.0.0.1", "::1"}
MAX_FAILS, LOCK_SECONDS = 5, 30

robots = {}   # ws -> role ("face" / "body" / None = 全部)
fails = {}    # ip -> (失败次数, 解锁时间)
TOKEN = ""
AUTH = True

ROUTE = {"face": "face", "audio": "face", "pose": "body", "gesture": "body", "torque": "body"}

DEMO = [
    {"t": "pose", "yaw": 35, "pitch": 5, "ms": 600},
    {"t": "gesture", "name": "nod", "times": 1},
    {"t": "sleep", "ms": 100},  # 两块板：动作先走，卡片晚 100ms
    {"t": "face", "state": "msg",
     "card": {"title": "飞书 · 产品群 @你", "body": "评审会改到 16:00", "hint": "按一下我的头 = 已读"}},
]


def load_token() -> str:
    env = os.environ.get("DESKBOT_TOKEN", "").strip()
    if env:
        return env
    f = HERE / ".token"
    if f.exists() and f.read_text().strip():
        return f.read_text().strip()
    token = secrets.token_hex(6)   # 12 位十六进制，好输入，也够防住随手乱试
    f.write_text(token + "\n")
    f.chmod(0o600)
    return token


def lan_ip() -> str:
    """本机在局域网里的地址（UDP connect 不会真的发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_locked(ip: str) -> bool:
    n, until = fails.get(ip, (0, 0.0))
    return n >= MAX_FAILS and time.time() < until


def note_fail(ip: str) -> int:
    n, _ = fails.get(ip, (0, 0.0))
    fails[ip] = (n + 1, time.time() + LOCK_SECONDS)
    return n + 1


async def handler(ws):
    ip = ws.remote_address[0]
    trusted = (not AUTH) or ip in LOCAL
    if ws.request.path != "/robot":
        await ws.close(code=1008, reason="path must be /robot")
        return
    if not trusted and is_locked(ip):
        await ws.close(code=1008, reason="locked, try later")
        return

    # 第一条必须是 hello，5 秒内
    try:
        hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert isinstance(hello, dict) and hello.get("t") == "hello"
    except Exception:
        await ws.close(code=1008, reason="first message must be hello")
        print(f"[x] {ip} 第一条不是 hello，已断开")
        return
    if not trusted and not hmac.compare_digest(str(hello.get("token", "")).encode(), TOKEN.encode()):
        n = note_fail(ip)
        await ws.close(code=1008, reason="bad token")
        print(f"[x] {ip} 令牌错误（第 {n} 次）" + ("，锁 30 秒" if n >= MAX_FAILS else ""))
        return
    fails.pop(ip, None)

    robots[ws] = hello.get("role")
    print(f"[+] robot connected {ip}  role = {robots[ws] or '全部'}  fw = {hello.get('fw', '?')}")
    await announce_peers()
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict) or msg.get("t") in ("state", "hello"):
                continue
            t = msg.get("t")
            if t == "relay" and isinstance(msg.get("msg"), dict):      # 控制台 → 其他所有人（真机 + 镜像）
                await broadcast(msg["msg"], exclude=ws)
                continue
            if t == "req":                                              # 联网抓数据很慢，不要堵住这个连接的消息循环
                asyncio.create_task(serve_request(ws, msg))
                continue
            print(f"↑ {raw[:160]}")
            if t in UPSTREAM:
                await broadcast(msg, exclude=ws)
            if t == "head_press":
                await broadcast({"t": "face", "state": "happy"})
    finally:
        robots.pop(ws, None)
        print(f"[-] robot disconnected {ip}")
        await announce_peers()


async def broadcast(msg, exclude=None):
    raw = json.dumps(msg, ensure_ascii=False)
    target = ROUTE.get(msg.get("t"))
    print(f"↓ {raw[:160]}" + (f"  → {target}" if target else ""))
    for ws, role in list(robots.items()):
        if ws is exclude or not (target is None or role is None or role == target):
            continue
        try:
            await ws.send(raw)
        except Exception:   # 这个连接正好断了，别让它拖垮别人
            pass


def peer_counts() -> dict:
    c = {"face": 0, "body": 0, "view": 0}
    for role in robots.values():
        c[role if role in ("face", "body") else "view"] += 1
    return c


async def announce_peers():
    await broadcast({"t": "peers", **peer_counts()})


UPSTREAM = ("head_press", "touch", "boss")   # 真机 / 网页上行的事件，转给其他客户端（让网页上的脚本能等到真机的按头）


async def live_message(what: str, req: dict | None = None) -> dict:
    """联网抓一份实时数据，返回可以直接广播的 face 消息。慢（要联网），放进线程里跑。"""
    loop = asyncio.get_running_loop()
    if what == "today":
        from today import get_today
        out = await loop.run_in_executor(None, get_today)
        print(f"  交易日来源：{out['market_source']}")
        return {"t": "face", "state": "today", "card": out["card"]}
    if what == "sky":
        from weather import get_weather, to_card
        return {"t": "face", "state": "sky", "card": to_card(await loop.run_in_executor(None, get_weather))}
    if what == "market":
        code = str((req or {}).get("code", "300750"))
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError(f"股票代码要 6 位数字：{code!r}")
        try:
            from market import get_card
            return {"t": "face", "state": "mkt", "card": await loop.run_in_executor(None, get_card, code)}
        except ImportError:
            raise RuntimeError("行情要 PandaAI：用 hub/run.sh 启动中枢（需要 panda-data 和 data/.env 里的账号）") from None
    raise ValueError(f"不认识的 req：{what!r}")


async def serve_request(ws, req: dict):
    """处理 req：成功就推给所有人，失败只告诉发请求的那一个。"""
    what = str(req.get("what"))
    try:
        await broadcast(await live_message(what, req))
    except Exception as e:
        text = f"{what} 获取失败：{e}" if isinstance(e, (ValueError, RuntimeError)) else f"{what} 获取失败：{type(e).__name__}: {e}"
        print(text)
        try:
            await ws.send(json.dumps({"t": "notice", "level": "error", "text": text}, ensure_ascii=False))
        except Exception:
            pass


class Discovery(asyncio.DatagramProtocol):
    """UDP 发现：回应 {"t":"deskbot?"}，忽略其他一切（过大、不是 JSON、别的类型），每个地址最多每 0.2 秒回一次。"""

    def __init__(self, reply: bytes):
        self.reply, self.transport, self.last = reply, None, {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if len(data) > 256:
            return
        try:
            msg = json.loads(data)
        except ValueError:
            return
        if not isinstance(msg, dict) or msg.get("t") != "deskbot?":
            return
        now = time.time()
        if now - self.last.get(addr[0], 0) < 0.2:
            return
        self.last[addr[0]] = now
        self.transport.sendto(self.reply, addr)
        print(f"[?] 发现询问来自 {addr[0]}，已回复")


async def start_discovery(port: int):
    """起 UDP 发现服务 + 定时 beacon。端口被占用也不影响中枢本身（只是机器人得手动填 IP）。"""
    reply = json.dumps({"t": "hub", "v": 1, "name": socket.gethostname(), "ws_port": port,
                        "path": NET["ws_path"], "auth": AUTH}, ensure_ascii=False).encode()
    loop = asyncio.get_running_loop()
    kw = {"reuse_port": True} if hasattr(socket, "SO_REUSEPORT") else {}   # 同一台电脑上也能再开一个 discover.py --listen
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: Discovery(reply), local_addr=("0.0.0.0", NET["discovery_port"]), allow_broadcast=True, **kw)
    except OSError as e:
        print(f"⚠️ 自动发现没启动（UDP {NET['discovery_port']}：{e}）；机器人要手动填中枢地址")
        return

    async def beacon():
        while True:
            for target in netutil.broadcast_addrs():
                try:
                    transport.sendto(reply, (target, NET["discovery_port"]))
                except OSError:
                    pass   # 某个网卡刚断开，下一轮再试
            await asyncio.sleep(NET["beacon_seconds"])

    asyncio.create_task(beacon())
    print(f"自动发现：UDP {NET['discovery_port']}，每 {NET['beacon_seconds']} 秒广播到 {', '.join(netutil.broadcast_addrs())}")


async def push_live(what: str):
    try:
        await broadcast(await live_message(what))
    except Exception as e:
        print(f"{what} 获取失败：{type(e).__name__}: {e}")


async def stdin_loop():
    loop = asyncio.get_running_loop()
    while True:
        raw = await loop.run_in_executor(None, sys.stdin.readline)
        if raw == "":   # EOF：没有键盘（后台运行 / 重定向），别空转，中枢继续服务就行
            await asyncio.Event().wait()
        line = raw.strip()
        if not line:
            continue
        if line == "demo":
            for msg in DEMO:
                if msg["t"] == "sleep":
                    await asyncio.sleep(msg["ms"] / 1000)
                    continue
                await broadcast(msg)
                await asyncio.sleep(0.8)
            continue
        if line in ("weather", "today", "market"):
            await push_live("sky" if line == "weather" else line)
            continue
        if line == "token":
            print(f"令牌：{TOKEN}" if AUTH else "（令牌检查已关闭）")
            continue
        try:
            await broadcast(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")


async def main(port: int):
    async with serve(handler, "0.0.0.0", port, max_size=64 * 1024):
        await start_discovery(port)
        print(f"mock hub  ws://{lan_ip()}:{port}/robot   （本机 ws://localhost:{port}/robot）")
        print(f"令牌：{TOKEN}（也在 hub/.token；本机连接不用）" if AUTH
              else "⚠️ 令牌检查已关闭（--no-auth）：同一个 WiFi 里的任何人都能连上来控制机器人")
        print("输入 JSON、demo、weather、today、market 或 token")
        await stdin_loop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-auth", action="store_true", help="不检查令牌（只在自己电脑上调试时用）")
    ap.add_argument("--port", type=int, default=NET["ws_port"])
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)   # 重定向到文件 / nohup 时日志也要立刻写出来
    AUTH = not a.no_auth
    TOKEN = load_token() if AUTH else ""
    asyncio.run(main(a.port))
