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

场景（hub/scenes.py，详见 场景.md）：
- {"t":"scene","name":"morning|watch|close|booth|stop"}（也可以 relay 过来，或终端输入 scene booth）：中枢按"起床后 / 盯盘 / 收盘 / 展台"的顺序把卡片推给机器人，
  并广播 {"t":"scene_state","name":…,"page":n,"of":m}。机器人上行的 touch = 跳到下一页，boss = 暂停。

日志（sim/logs.html 看）：
- 任何已通过认证的客户端发 {"t":"log","lvl":"info|warn|error","src":"face|body|sim","code":"WIFI_LOST","msg":"…"}，
  中枢补上 ts（毫秒时间戳）和 from（来源地址），存进最近 300 条的环形缓冲，广播给所有人。
  新连上的网页（没报 role 或 role=view）在 hello 之后收到一条 {"t":"logs","items":[…]} 历史。中枢自己的事件（src=hub）也记在里面。终端输入 logs 打印缓冲。令牌永远不进日志。

令牌：
- 现场 WiFi 里有几百人，中枢没有密码的话谁都能连上来让机器人乱动，所以第一条消息必须是 hello，并带上令牌：
  {"t": "hello", "role": "face", "fw": "0.1.0", "token": "<令牌>"}
- 令牌来源：环境变量 DESKBOT_TOKEN，否则读 hub/.token，都没有就随机生成一个存进 hub/.token（已 gitignore）。
  重启中枢令牌不变，所以固件不用重新烧。
- 本机（127.0.0.1）的连接不用令牌，所以电脑上的模拟器照常能用；手机 / 板子 / 别的电脑要带。
- 云端（--proxy，在 nginx 后面）：只听 127.0.0.1，真实地址取 X-Real-IP，**所有连接都要令牌**（经过 nginx 的连接看起来都来自本机），不做 UDP 发现。
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
from collections import deque
import time
from pathlib import Path

from websockets.asyncio.server import serve

import netutil
import modes
import scenes

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data"))   # data/weather.py

NET = json.loads((HERE.parent / "config" / "network.json").read_text())["hub"]
LOCAL = {"127.0.0.1", "::1"}
MAX_FAILS, LOCK_SECONDS = 5, 30

LOG_MAX = 300
LOG_LEVELS = ("info", "warn", "error")
log_buf = deque(maxlen=LOG_MAX)   # 日志环形缓冲
robots = {}   # ws -> role ("face" / "body" / None = 全部)
fails = {}    # ip -> (失败次数, 解锁时间)
TOKEN = ""
AUTH = True
PROXY = False   # --proxy：在 nginx 后面（云端），见文件头「令牌」

engine = None   # 场景引擎（main() 里创建）

ROUTE = {"face": "face", "audio": "face", "pose": "body", "torque": "body"}   # gesture 发给所有人：整机只有一块板（role=face），点头 / 摇头 / 转头都由它做

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


def _log_entry(lvl, src, code, msg, frm="") -> dict:
    return {"t": "log", "ts": int(time.time() * 1000), "lvl": lvl, "src": src,
            "code": str(code)[:40], "msg": str(msg)[:300], "from": frm}


async def hub_log(lvl: str, code: str, msg: str):
    """中枢自己的事件：打印、入缓冲、广播给所有人。"""
    entry = _log_entry(lvl, "hub", code, msg)
    log_buf.append(entry)
    print(f"[{lvl}] {code} {msg}")
    await broadcast_raw(entry)


async def client_log(ws, ip: str, msg: dict):
    lvl = msg.get("lvl") if msg.get("lvl") in LOG_LEVELS else "info"
    src = msg.get("src") if msg.get("src") in ("face", "body", "sim", "hub") else (robots.get(ws) or "sim")
    entry = _log_entry(lvl, src, msg.get("code", "LOG"), msg.get("msg", ""), ip)
    log_buf.append(entry)
    print(f"[{lvl}] {src} {entry['code']} {entry['msg']}")
    await broadcast_raw(entry)


DISPLAY_MODES = ("simple", "compact", "pro")
DISPLAY = {"mode": "pro"}   # 当前显示模式：简洁 / 紧凑 / 专业；真机和网页共用


def note_sent(ws, msg: dict) -> None:
    """记下发给这块板子的最后一张 face 卡（和板子上行的 shown 对账用）。"""
    if msg.get("t") == "face":
        card = msg.get("card") or {}
        sent_face[ws] = {"state": msg.get("state"), "item": card.get("name") or card.get("city") or "", "at": time.monotonic()}


def norm_display(mode) -> str:
    return "pro" if mode == "compact" else str(mode)   # 板子只有简洁 / 专业两档，紧凑按专业画


async def warn_once(ws, code: str, text: str):
    if time.monotonic() - warned_at.get((ws, code), -1e9) >= 30:
        warned_at[(ws, code)] = time.monotonic()
        await hub_log("warn", code, text)


async def on_shown(ws, msg: dict):
    """板子每画完一张卡上行 {"t":"shown","state","mode","item"}：记下来，对一下显示模式。"""
    last_shown[ws] = {"state": msg.get("state"), "mode": msg.get("mode"), "item": msg.get("item", ""), "at": time.monotonic()}
    if msg.get("mode") and msg.get("state") in ("watch", "mkt", "today", "sky", "weather", "brief", "msg", "ask", "agent") \
            and norm_display(msg["mode"]) != norm_display(DISPLAY["mode"]):
        await warn_once(ws, "DISPLAY_MISMATCH", f"真机画的是 {msg.get('mode')} 模式，设置里是 {DISPLAY['mode']}（板子没收到 display，或者本地长按切换了）")


mismatch_since = {}   # ws -> 板子画的和中枢发的对不上，从什么时候开始


async def desync_watch():
    """每 2 秒对一次账：板子上行的最后一条 shown 的状态，和中枢发给它的最后一张 face 卡的状态对不上，连续超过 5 秒，
    记 DESYNC（warn，每块板子 30 秒最多一条）。时钟 / 待机模式中枢不推卡，不查。老固件不发 shown，也不查。"""
    while True:
        await asyncio.sleep(2)
        if engine and engine.name == "idle":
            mismatch_since.clear()
            continue
        for ws, role in list(robots.items()):
            sent, shown = sent_face.get(ws), last_shown.get(ws)
            if role != "face" or not sent or not shown or sent["state"] in ("idle", "decoy"):
                continue
            if shown["state"] == sent["state"]:
                mismatch_since.pop(ws, None)
                continue
            since = mismatch_since.setdefault(ws, time.monotonic())
            if time.monotonic() - since > 5:
                await warn_once(ws, "DESYNC", f"真机上画的是 {shown['state']}，中枢发的是 {sent['state']}（{sent['item']}），已经对不上 {int(time.monotonic() - since)} 秒：板子没画出来？老板键开着？")


async def broadcast_raw(msg: dict, exclude=None):
    """不打印、不按 role 过滤，发给所有人（日志用）。"""
    raw = json.dumps(msg, ensure_ascii=False)
    for w in list(robots):
        if w is exclude:
            continue
        try:
            await w.send(raw)
        except Exception:
            pass


async def handler(ws):
    ip = (ws.request.headers.get("X-Real-IP") if PROXY else None) or ws.remote_address[0]
    trusted = (not AUTH) or (ip in LOCAL and not PROXY)
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
        if ip not in LOCAL:
            await hub_log("warn", "HELLO_MISSING", f"{ip} 第一条消息不是 hello，已断开")
        return
    if not trusted and not hmac.compare_digest(str(hello.get("token", "")).encode(), TOKEN.encode()):
        n = note_fail(ip)
        await ws.close(code=1008, reason="bad token")
        print(f"[x] {ip} 令牌错误（第 {n} 次）" + ("，锁 30 秒" if n >= MAX_FAILS else ""))
        await hub_log("warn", "AUTH_LOCKED" if n >= MAX_FAILS else "AUTH_BAD_TOKEN",
                      f"{ip} 令牌错误（第 {n} 次）" + ("，锁 30 秒" if n >= MAX_FAILS else ""))
        return
    fails.pop(ip, None)

    robots[ws] = robots_role = hello.get("role")
    ips[ws] = ip
    if robots_role in ("face", "body") and ip not in LOCAL:   # 同一块板子重启 / 重新烧录后重连：旧连接还没被 ping 超时清掉，直接换掉它
        for old, role in list(robots.items()):
            if old is not ws and role == robots_role and ips.get(old) == ip:
                asyncio.create_task(old.close(1000, "replaced by a newer connection"))
    print(f"[+] robot connected {ip}  role = {robots[ws] or '全部'}  fw = {hello.get('fw', '?')}")
    await announce_peers()
    try:
        await ws.send(json.dumps(engine.last_state, ensure_ascii=False))   # 新连上的人马上知道现在是哪个场景、第几页
    except Exception:
        pass
    try:
        await ws.send(json.dumps({"t": "display", "mode": DISPLAY["mode"]}))   # 新连上的人马上知道现在是哪种显示模式
        await ws.send(json.dumps({"t": "profile", "profile": engine.public_profile()}, ensure_ascii=False))   # 和当前设置
        if engine.last_face and robots[ws] != "body":   # 以及现在屏幕上的那张卡（不用等下一次刷新）
            await ws.send(json.dumps(engine.last_face, ensure_ascii=False))
            note_sent(ws, engine.last_face)
    except Exception:
        pass
    if robots[ws] not in ("face", "body"):   # 网页：补发历史日志
        try:
            await ws.send(json.dumps({"t": "logs", "items": list(log_buf)}, ensure_ascii=False))
        except Exception:
            pass
    if robots[ws] in ("face", "body") or ip not in LOCAL:   # 本机开网页调试的连上断开不记，免得日志全是这个
        await hub_log("info", "CLIENT_UP", f"{ip} 已连上（{robots[ws] or 'view'}，固件 {str(hello.get('fw', '?'))[:20]}）")
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict) or msg.get("t") in ("state", "hello"):
                continue
            t = msg.get("t")
            if t == "log":
                await client_log(ws, ip, msg)
                continue
            if t == "profile":                                          # 设置：深度合并 → 保存 → 广播完整设置
                asyncio.create_task(handle_profile(ws, msg))   # 查城市要联网（几秒），别堵住这个连接的其他消息
                continue
            if t == "mode":                                             # 切模式：watch / weather / today / clock / idle / booth
                name = str(msg.get("name", ""))
                if not await engine.set_mode(name):
                    text = "天气 / 时钟 / 今天功能已移除，可用：" + " / ".join(modes.MODES) if name in modes.REMOVED else "不认识的模式：" + name[:20]
                    await ws.send(json.dumps({"t": "notice", "level": "error", "text": text}, ensure_ascii=False))
                continue
            if t == "shown":                                            # 板子画完一张卡：记下来、转给网页，不打印
                await on_shown(ws, msg)
                await broadcast(msg, exclude=ws)
                continue
            if t == "mode_ctl":                                         # 上一个 / 下一个 / 暂停 / 继续
                await engine.ctl(str(msg.get("op", "")))
                continue
            if t == "open":                                             # 点了某只股票：整屏行情停 12 秒
                await engine.open(str(msg.get("code", "")))
                continue
            if t == "symbols":                                          # 搜股票：按名称或代码
                items = await engine.symbols(str(msg.get("q", "")))
                await ws.send(json.dumps({"t": "symbols_result", "q": str(msg.get("q", ""))[:20], "items": items}, ensure_ascii=False))
                continue
            if t == "display":                                          # 显示模式：simple / compact / pro，存下来并广播给其他人
                mode = msg.get("mode")
                if mode in DISPLAY_MODES:
                    DISPLAY["mode"] = mode
                    await engine.set_display(mode)   # 也记进设置里，重启后还在
                    await broadcast({"t": "display", "mode": mode}, exclude=ws)
                    await hub_log("info", "DISPLAY_MODE", f"显示模式 → {mode}")
                continue
            if t == "scene":                                            # 场景：morning / watch / close / booth / stop
                await engine.handle(msg)
                continue
            if t == "relay" and isinstance(msg.get("msg"), dict):      # 控制台 → 其他所有人（真机 + 镜像）
                if msg["msg"].get("t") == "scene":
                    await engine.handle(msg["msg"])
                else:
                    await broadcast(msg["msg"], exclude=ws)
                continue
            if t == "req":                                              # 联网抓数据很慢，不要堵住这个连接的消息循环
                asyncio.create_task(serve_request(ws, msg))
                continue
            print(f"↑ {raw[:160]}")
            if t in UPSTREAM:
                engine.event(msg)   # touch = 场景跳页，boss = 场景暂停
                await broadcast(msg, exclude=ws)
            if t == "head_press":
                await broadcast({"t": "face", "state": "happy"})
    finally:
        robots.pop(ws, None)
        sink = sinks.pop(ws, None)
        if sink:
            sink.close()
        print(f"[-] robot disconnected {ip}")
        sent_face.pop(ws, None)
        last_shown.pop(ws, None)
        mismatch_since.pop(ws, None)
        ips.pop(ws, None)
        await announce_peers()
        if robots_role in ("face", "body") or ip not in LOCAL:
            await hub_log("info", "CLIENT_DOWN", f"{ip} 已断开（{robots_role or 'view'}）")


FACE_GAP = 1.0   # 同一块真机上，两张 face 卡片之间至少隔这么久（秒）：板子渲染一张卡要时间，发太快会拖死它的网络循环


class FaceSink:
    """真机的发送队列：face 卡片最快每 FACE_GAP 秒发一张；队列里连续的 watch 刷新只留最新一张（板子落后时丢掉中间帧），
    其他状态（mkt / today / idle …）一张不丢、顺序不变。"""

    def __init__(self, ws):
        self.ws, self.q, self.last, self.task, self.dropped, self.warned = ws, deque(), 0.0, None, 0, 0.0

    def push(self, msg: dict, raw: str):
        last = self.q[-1][0] if self.q else None
        if last and msg.get("state") in ("watch", "mkt") and last.get("state") == msg.get("state") and \
                (msg["state"] == "watch" or (last.get("card") or {}).get("code") == (msg.get("card") or {}).get("code")):
            self.q[-1] = (msg, raw)
            self.dropped += 1
        else:
            self.q.append((msg, raw))
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())

    async def _run(self):
        while self.q:
            wait = self.last + FACE_GAP - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            if not self.q:
                return
            msg, raw = self.q.popleft()
            try:
                await self.ws.send(raw)
                note_sent(self.ws, msg)
            except Exception:   # 连接断了：队列没用了
                self.q.clear()
                return
            self.last = time.monotonic()
            if self.dropped and time.monotonic() - self.warned > 60:   # 同一块板子一分钟最多记一条
                self.warned, n, self.dropped = time.monotonic(), self.dropped, 0
                await hub_log("info", "FACE_COALESCE", f"真机收卡片比发送慢（每 {FACE_GAP:g} 秒 1 张），合并掉 {n} 张中间的 watch 刷新")

    def close(self):
        self.q.clear()
        if self.task and not self.task.done():
            self.task.cancel()


sinks = {}   # ws -> FaceSink（只有 role=face 的真机）
ips = {}          # ws -> ip
sent_face = {}    # ws -> {"state","item","at"}：中枢最后一张真正发给这块板子的 face 卡
last_shown = {}   # ws -> 板子上行的最后一条 shown：{"state","mode","item","at"}
warned_at = {}    # (ws, 代码) -> 上次记这条 warn 的时间（每 30 秒最多一条）


async def broadcast(msg, exclude=None):
    raw = json.dumps(msg, ensure_ascii=False)
    target = ROUTE.get(msg.get("t"))
    if msg.get("t") != "shown":
        print(f"↓ {raw[:160]}" + (f"  → {target}" if target else ""))
    for ws, role in list(robots.items()):
        if ws is exclude or not (target is None or role is None or role == target):
            continue
        if role == "face" and msg.get("t") == "face":   # 真机：限速 + 合并
            sinks.setdefault(ws, FaceSink(ws)).push(msg, raw)
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


UPSTREAM = ("head_press", "touch", "boss", "shown")   # 真机 / 网页上行的事件，转给其他客户端（让网页上的脚本能等到真机的按头）


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


FAIL_INFO = {   # what -> (日志代码, 给人看的中文)
    "today": ("API_TODAY_FAIL", "今天的日期 / 交易日获取失败，先显示本地日期"),
    "sky": ("API_WEATHER_FAIL", "天气获取失败（Open-Meteo 连不上）"),
    "market": ("API_MARKET_FAIL", "行情获取失败（PandaAI 连不上或没有数据，休市时看上一个交易日）"),
}


async def handle_profile(ws, msg: dict):
    ok, err, field = await engine.profile_set(msg.get("set"))
    try:
        await ws.send(json.dumps({"t": "profile_result", "ok": ok, **({} if ok else {"error": err, **({"field": field} if field else {})})}, ensure_ascii=False))
    except Exception:
        pass


async def serve_request(ws, req: dict):
    """处理 req：成功就推给所有人；失败记日志，并告诉发请求的那一个（notice），屏幕不会没反应。"""
    what = str(req.get("what"))
    try:
        await broadcast(await live_message(what, req))
    except Exception as e:
        code, friendly = FAIL_INFO.get(what, ("REQ_BAD", f"不认识的请求：{what[:20]}"))
        if isinstance(e, (ValueError, RuntimeError)):
            code = "REQ_BAD" if isinstance(e, ValueError) else code
            detail = str(e)
        else:
            detail = f"{type(e).__name__}: {e}"
        text = (detail if code == "REQ_BAD" else f"{friendly}：{detail}")[:300]
        await hub_log("error", code, text)
        try:
            await ws.send(json.dumps({"t": "notice", "level": "error", "text": text}, ensure_ascii=False))
        except Exception:
            pass


class Discovery(asyncio.DatagramProtocol):
    """UDP 发现：回应 {"t":"deskbot?"}，忽略其他一切（过大、不是 JSON、别的类型），每个地址最多每 0.2 秒回一次。"""

    def __init__(self, reply: bytes):
        self.reply, self.transport, self.last, self.logged = reply, None, {}, {}

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
        if now - self.logged.get(addr[0], 0) > 30:   # 机器人每秒问一次，日志里 30 秒记一条就够
            self.logged[addr[0]] = now
            asyncio.get_running_loop().create_task(hub_log("info", "DISCOVERY", f"{addr[0]} 在找中枢，已回复"))


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
        code, friendly = FAIL_INFO.get(what, ("REQ_BAD", what))
        await hub_log("error", code, f"{friendly}：{type(e).__name__}: {e}"[:300])


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
        if line.startswith("mode "):   # mode watch | weather | today | clock | idle | booth
            await engine.set_mode(line.split()[1])
            continue
        if line == "profile":
            print(json.dumps(engine.public_profile(), ensure_ascii=False, indent=1))
            continue
        if line.startswith("scene"):   # scene booth | scene watch speed=0.5 refresh=1 | scene stop
            parts = line.split()
            msg = {"t": "scene", "name": parts[1] if len(parts) > 1 else "stop"}
            for kv in parts[2:]:
                k, _, v = kv.partition("=")
                msg[k] = (v.lower() in ("1", "true", "yes")) if k == "live" else v
            await engine.handle(msg)
            continue
        if line == "logs":
            for e in log_buf:
                print(f"{time.strftime('%H:%M:%S', time.localtime(e['ts'] / 1000))} [{e['lvl']}] {e['src']} {e['code']} {e['msg']}")
            continue
        if line == "token":
            print(f"令牌：{TOKEN}" if AUTH else "（令牌检查已关闭）")
            continue
        try:
            await broadcast(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")


async def main(port: int):
    global engine
    engine = modes.ModeEngine(broadcast, hub_log, Path(os.environ.get("DESKBOT_PROFILE") or HERE / "profile.json"))
    DISPLAY["mode"] = engine.profile["display"]

    async def on_display(mode):   # profile.set 里改了 display：和 {"t":"display"} 一样同步给所有人
        DISPLAY["mode"] = mode
        await broadcast({"t": "display", "mode": mode})
    engine.display_hook = on_display
    asyncio.create_task(engine.boot())
    asyncio.create_task(desync_watch())
    # 保活：每 20 秒 ping 一次，60 秒没回才断（默认是 20 秒）。真机的 WebSocketsClient 只在 ws.loop() 里回 pong，
    # 板子画一张卡 / 扫 WiFi 的几百毫秒到几秒里不会回；网页标签页在后台时浏览器也会推迟回 pong。
    async with serve(handler, "127.0.0.1" if PROXY else "0.0.0.0", port, max_size=64 * 1024, ping_interval=20, ping_timeout=60):
        if not PROXY:
            await start_discovery(port)
        print(f"mock hub  ws://{lan_ip()}:{port}/robot   （本机 ws://localhost:{port}/robot）")
        print(f"令牌：{TOKEN}（也在 hub/.token；本机连接不用）" if AUTH
              else "⚠️ 令牌检查已关闭（--no-auth）：同一个 WiFi 里的任何人都能连上来控制机器人")
        print("输入 JSON、demo、weather、today、market、mode <watch|list|idle|booth>、profile、scene <…>、logs 或 token")
        await hub_log("info", "HUB_START", f"中枢启动 ws://{lan_ip()}:{port}/robot" + ("" if AUTH else "（无令牌）"))
        await stdin_loop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-auth", action="store_true", help="不检查令牌（只在自己电脑上调试时用）")
    ap.add_argument("--port", type=int, default=NET["ws_port"])
    ap.add_argument("--proxy", action="store_true", help="云端：在 nginx 后面，只听 127.0.0.1，所有连接都要令牌，不做 UDP 发现")
    a = ap.parse_args()
    PROXY = a.proxy
    sys.stdout.reconfigure(line_buffering=True)   # 重定向到文件 / nohup 时日志也要立刻写出来
    AUTH = not a.no_auth
    TOKEN = load_token() if AUTH else ""
    asyncio.run(main(a.port))
