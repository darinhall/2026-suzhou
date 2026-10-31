"""场景引擎：中枢按"一天怎么用"把屏幕要显示的卡片排成播放列表，推给机器人。

场景（详见 场景.md）：
- morning（起床后）：今天 → 天气 → 盘前简报 → 自选（收盘）→ 回到待机
- watch（盯盘中）：自选列表按"回放"一路刷新；谁第一次触及 ±2% / ±3%，跳到那只股票的整屏行情 8 秒再回来
- close（收盘）：市场天气 → 自选（收盘）→ 收盘小结
- booth（展台）：morning → watch 回放 → close，一直循环

控制：{"t":"scene","name":"morning|watch|close|booth|stop", "hold":16, "speed":0.8, "refresh":2, "live":false}
     终端输入 `scene booth`，或网页 relay 过来。
状态：中枢广播 {"t":"scene_state","name":"watch","page":2,"of":5,"label":"自选回放","clock":"13:35","sub":30,"subof":48}；没有场景时 name 为 null。
真机上行：touch = 跳到下一页（回放里 = 结束回放；整屏行情里 = 回到列表），boss（老板键）打开时暂停，关掉后继续。

数据都在线程里取（联网慢），取失败只跳过那一页并记日志，不会编数据；回放用的是最近一个交易日的真实 5 分钟线。
"""

from __future__ import annotations

import asyncio
import datetime
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))

SCENES = {
    "morning": ["today", "sky", "brief", "watch_close"],
    "watch": ["replay", "watch_close"],
    "close": ["weather", "watch_close", "summary"],
    "booth": ["today", "sky", "brief", "watch_close", "replay", "weather", "watch_close", "summary"],
}
LOOPING = {"booth"}
LABEL = {"today": "今天", "sky": "天气", "brief": "盘前简报", "watch_close": "自选（收盘）", "replay": "自选回放",
         "weather": "市场天气", "summary": "收盘小结"}
FAIL_CODE = {"today": "API_TODAY_FAIL", "sky": "API_WEATHER_FAIL"}   # 其余都是 API_MARKET_FAIL
ALERT_LEVELS = (2, 3)   # 涨跌幅第一次触及 ±2% / ±3% 时报警
DEFAULTS = {"hold": 16.0, "speed": 1.0, "refresh": 2.0, "alert_hold": 8.0}


class SceneEngine:
    def __init__(self, broadcast, log):
        """broadcast(msg)：发给所有该收的客户端（face 消息只到 face）；log(lvl, code, msg)：中枢日志。"""
        self.bc, self.log = broadcast, log
        self.task: asyncio.Task | None = None
        self.skip = asyncio.Event()
        self.boss = False
        self.name: str | None = None
        self.opts = dict(DEFAULTS)
        self.last_state: dict = {"t": "scene_state", "name": None, "page": 0, "of": 0}
        self._pre: dict[str, asyncio.Task] = {}
        self._warned: set[int] = set()
        self._cache: dict = {}

    # ---------- 控制 ----------
    async def handle(self, msg: dict) -> None:
        """处理 {"t":"scene",...}。"""
        name = str(msg.get("name", ""))
        if name == "stop":
            await self.stop()
            return
        if name not in SCENES:
            await self.log("warn", "SCENE_BAD", f"不认识的场景：{name[:20]}（morning / watch / close / booth / stop）")
            return
        opts = dict(DEFAULTS)
        for k in ("hold", "speed", "refresh", "alert_hold"):
            try:
                if msg.get(k) is not None:
                    opts[k] = max(0.2, min(120.0, float(msg[k])))
            except (TypeError, ValueError):
                pass
        opts["live"] = bool(msg.get("live", False))
        if name == "booth" and msg.get("speed") is None:
            opts["speed"] = 0.8   # 展台：整个回放约 40 秒
        await self.start(name, opts)

    async def start(self, name: str, opts: dict) -> None:
        await self.stop(quiet=True)
        self.name, self.opts = name, opts
        self.skip.clear()
        self.task = asyncio.create_task(self._run(name))
        await self.log("info", "SCENE_START", f"场景 {name}（每页 {opts['hold']:g} 秒，回放每根 {opts['speed']:g} 秒）")

    async def stop(self, quiet: bool = False) -> None:
        task, self.task = self.task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        for t in self._pre.values():
            t.cancel()
        self._pre.clear()
        if self.name and not quiet:
            await self.log("info", "SCENE_STOP", f"场景 {self.name} 已停止")
        had = self.name
        self.name = None
        if had and not quiet:
            await self._state(None, 0, 0)
            await self.bc({"t": "face", "state": "idle"})

    def event(self, msg: dict) -> None:
        """真机 / 网页上行的 touch（跳页）和 boss（暂停）。"""
        if msg.get("t") == "boss":
            self.boss = bool(msg.get("on"))
        elif msg.get("t") == "touch" and self.task and not self.boss:
            self.skip.set()

    async def warm(self) -> None:
        """中枢启动时先把天气和行情拉一遍放进缓存，第一次开场景就不用等 4–5 秒。失败不要紧，开场景时会再试。"""
        try:
            from today import get_today
            from weather import get_weather
            await asyncio.gather(self._cached("weather", get_weather, 900), self._cached("today", get_today, 120), self._day(), return_exceptions=True)
        except BaseException:
            pass

    # ---------- 状态广播 ----------
    async def _state(self, name, page, of, **extra) -> None:
        self.last_state = {"t": "scene_state", "name": name, "page": page, "of": of, **extra}
        await self.bc(self.last_state)

    # ---------- 等待：可被 touch 跳过，老板键打开时暂停 ----------
    async def _sleep_or_skip(self, s: float) -> bool:
        try:
            await asyncio.wait_for(self.skip.wait(), s)
        except asyncio.TimeoutError:
            return False
        self.skip.clear()
        return True

    async def _wait(self, seconds: float) -> bool:
        """等 seconds 秒（老板键打开的时间不算）。返回 True = 被 touch 跳过。"""
        left = seconds
        while left > 0:
            if self.boss:
                self.skip.clear()
                await asyncio.sleep(0.25)
                continue
            step = min(0.25, left)
            if await self._sleep_or_skip(step):
                return True
            left -= step
        return False

    async def _unpaused(self) -> None:
        while self.boss:
            self.skip.clear()
            await asyncio.sleep(0.25)

    # ---------- 取数 ----------
    async def _thread(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *a)

    async def _cached(self, key: str, fn, ttl: float = 300):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        val = await self._thread(fn)
        self._cache[key] = (time.time(), val)
        return val

    async def _day(self) -> dict:
        from watch import load_day
        day = await self._thread(load_day)
        if id(day) not in self._warned:   # 同一份数据只记一次
            self._warned.add(id(day))
            if day["source"] != "panda":
                await self.log("warn", "API_MARKET_FAIL", f"行情走 {day['source']}（{day.get('warn') or '没有账号 / 没网'}）；示例数据会在屏幕上标明")
            elif day.get("interp"):
                await self.log("warn", "REPLAY_INTERP", "5 分钟线不够，这几只用日线插值：" + ",".join(day["interp"]))
        return day

    async def _build(self, key: str):
        """返回 (state, card)。"""
        if key == "today":
            from today import get_today
            return "today", (await self._cached("today", get_today, 120))["card"]
        if key == "sky":
            from weather import get_weather, to_card
            return "sky", to_card(await self._cached("weather", get_weather, 900))
        if key == "brief":
            from brief import morning_brief
            from today import next_event
            from weather import get_weather
            try:
                weather = await self._cached("weather", get_weather, 900)
            except Exception as e:   # 没网：简报少一句天气，不整页跳过
                weather = None
                await self.log("warn", "API_WEATHER_FAIL", f"简报里没有天气：{type(e).__name__}: {e}"[:200])
            day = await self._day()
            return "brief", await self._thread(morning_brief, weather, next_event(datetime.datetime.now()), day)
        if key == "watch_close":
            from watch import watch_card
            return "watch", watch_card(await self._day(), "close")
        if key == "weather":
            from watch import market_weather
            day = await self._day()
            w = await self._thread(market_weather, day)
            card = {k: w[k] for k in ("time", "word", "up", "down")}
            if day["source"] == "sample":
                card["mode"] = "sample"      # 示例数据：屏幕上要标明
            elif w["source"] == "index":
                card["mode"] = "estimate"    # 涨跌家数是用指数涨跌估的，不是数出来的
                await self.log("warn", "API_MARKET_FAIL", "涨跌家数取不到，市场天气按上证涨跌估算")
            return "weather", card
        if key == "summary":
            from brief import close_summary
            return "brief", await self._thread(close_summary, await self._day())
        raise KeyError(key)

    async def _get(self, key: str):
        task = self._pre.pop(key, None) or asyncio.ensure_future(self._build(key))
        try:
            return await task
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            await self.log("warn", FAIL_CODE.get(key, "API_MARKET_FAIL"), f"{LABEL[key]}这一页取数失败，跳过：{type(e).__name__}: {e}"[:300])
            return None

    def _prefetch(self, key: str | None) -> None:
        if key and key != "replay" and key not in self._pre:
            self._pre[key] = asyncio.ensure_future(self._build(key))

    # ---------- 播放 ----------
    async def _run(self, name: str) -> None:
        pages = SCENES[name]
        try:
            while True:
                shown = 0
                for n, key in enumerate(pages):
                    self._prefetch(pages[n + 1] if n + 1 < len(pages) else (pages[0] if name in LOOPING else None))
                    await self._unpaused()
                    if key == "replay":
                        await self._replay(name, n + 1, len(pages))
                        shown += 1
                        continue
                    built = await self._get(key)
                    if not built:
                        continue
                    await self._unpaused()
                    state, card = built
                    await self._state(name, n + 1, len(pages), label=LABEL[key])
                    await self.bc({"t": "face", "state": state, "card": card})
                    await self.log("info", "SCENE_PAGE", f"{name} {n + 1}/{len(pages)} {LABEL[key]}")
                    shown += 1
                    await self._wait(self.opts["hold"])
                if name not in LOOPING:
                    break
                if not shown:   # 一页都出不来（全断网）：别空转
                    await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            await self.log("error", "SCENE_CRASH", f"场景 {name} 出错退出：{type(e).__name__}: {e}"[:300])
        finally:
            if self.task is asyncio.current_task():   # 自己播完（不是被 stop 取消）：回到待机
                self.task = None
                self.name = None
                await self._state(None, 0, 0)
                await self.bc({"t": "face", "state": "idle"})
                await self.log("info", "SCENE_STOP", f"场景 {name} 播完了")

    async def _replay(self, name: str, page: int, of: int) -> None:
        """回放最近一个交易日：每根 5 分钟线 opts.speed 秒；每 opts.refresh 秒推一次 watch 卡；
        第一次触及 ±2% / ±3% 的股票跳到整屏 mkt 卡 alert_hold 秒。touch = 结束回放。"""
        from watch import TIMES, mover_card, stock_state, watch_card

        o = self.opts
        day = await self._day()
        if o.get("live"):
            if await self._live(name, page, of, day):
                return
        n, seen, since = len(TIMES), set(), 1e9
        for i in range(n):
            alert = None   # (k, pct, level)
            for k in range(min(3, len(day["stocks"]))):
                pct = stock_state(day, k, i)["pct"]
                for lvl in ALERT_LEVELS:
                    key = (day["stocks"][k]["code"], pct > 0, lvl)
                    if abs(pct) >= lvl and key not in seen:
                        seen.add(key)
                        alert = (k, pct, lvl)
            await self._unpaused()
            if alert:
                k, pct, lvl = alert
                s = day["stocks"][k]
                text = f"{s['name']} {pct:+.2f}% · 触及 ±{lvl}% · {TIMES[i]}"
                await self.log("info", "SCENE_ALERT", text)
                await self.bc({"t": "notice", "level": "info", "text": text})
                await self._state(name, page, of, label="异动", clock=TIMES[i], sub=i + 1, subof=n)
                await self.bc({"t": "face", "state": "mkt", "card": mover_card(day, k, i)})
                await self._wait(o["alert_hold"])
                since = 1e9   # 回到列表立刻刷一次
            if since >= o["refresh"] or i == n - 1:
                since = 0
                await self._state(name, page, of, label=LABEL["replay"], clock=TIMES[i], sub=i + 1, subof=n)
                await self.bc({"t": "face", "state": "watch", "card": watch_card(day, "replay", i, tuple(day["stocks"][k]["code"] for k in ([alert[0]] if alert else [])))})
            if await self._wait(o["speed"]):
                return
            since += o["speed"]
        await self.log("info", "SCENE_PAGE", f"{name} {page}/{of} 回放结束")
        await self._wait(min(6.0, o["hold"]))   # 停在收盘那一帧一会儿

    async def _live(self, name: str, page: int, of: int, day: dict) -> bool:
        """盘中实时（尽力而为）：每 60 秒取一次快照刷新。取不到（休市 / 免费号没权限）就返回 False，退回回放。"""
        from watch import live_card
        try:
            card = await self._thread(live_card, day)
        except BaseException as e:
            await self.log("warn", "API_LIVE_FAIL", f"盘中实时取不到，改用回放：{type(e).__name__}: {e}"[:200])
            return False
        while True:
            await self._state(name, page, of, label="自选实时")
            await self.bc({"t": "face", "state": "watch", "card": card})
            if await self._wait(60):
                return True
            try:
                card = await self._thread(live_card, day)
            except BaseException as e:
                await self.log("warn", "API_LIVE_FAIL", f"实时刷新失败，保留上一帧：{type(e).__name__}: {e}"[:200])
