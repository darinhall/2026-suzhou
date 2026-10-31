"""模式引擎：屏幕不再在不相干的页面之间乱跳，而是停在一个"大模式"的整屏版面上，按定时器在这个模式的"条目"里滚动。

模式（详见 场景.md）：
- watch 盯盘：条目 = 自选股。view=single（默认）每只一张整屏 `mkt` 行情卡，每 interval 秒换下一只；view=list 是 `watch` 列表（一页 5 行，多了翻页）。
  行情默认回放最近一个交易日的 5 分钟线（数字在跳），第一次触及 ±2% / ±3% 的股票跳到它的整屏行情 alert_hold 秒。
  真机点一下（touch）= 下一只；{"t":"open","code":"688981"} = 点了列表里的某一行：这只的整屏行情停 12 秒再回来。
- weather 天气：整屏 `sky` 卡，在 weather.cities 里每 interval 秒换一个城市；touch = 下一个城市。
- today 今天（起床后）：`today` 卡，每分钟刷新；today.brief 打开时第二页是盘前简报。
- clock 时钟：老板键的时钟在真机本地画，中枢只是发 face decoy 并停止推卡片。
- idle 待机：停止推卡片，发 face idle，真机自己的待机动画接管。
- booth 展台：watch → weather → today 各停 booth.dwell 秒，一直循环。

设置（profile）由中枢持有，存在 hub/profile.json，所有客户端（网页、真机）都收到同一份：
    {"mode":"watch","display":"pro",
     "watch":{"codes":["300750",…],"view":"single","interval":10},
     "weather":{"cities":[{"name":"苏州","lat":31.27,"lon":120.74},…],"interval":10},
     "today":{"city":"苏州","interval":15,"brief":false},
     "booth":{"enabled":false,"dwell":30},"replay":{"enabled":true,"speed":1.0,"loop":true}}

消息（client = 网页 / 真机）：
    client→hub  {"t":"profile","set":{…部分设置，深度合并…}}      → 回给发送者 {"t":"profile_result","ok":true|false,"error":"…"}
    hub→所有人  {"t":"profile","profile":{…完整设置，watch.stocks 带名称…}}   每次变化、新连上时
    client→hub  {"t":"mode","name":"watch|weather|today|clock|idle|booth"}
    client→hub  {"t":"open","code":"688981"}                      点某只股票看详情
    client→hub  {"t":"symbols","q":"宁德"}                        → 回给发送者 {"t":"symbols_result","items":[{"code","name"},…≤8]}
    hub→所有人  {"t":"scene_state","name":"watch","page":2,"of":5,"label":"中芯国际","item":"中芯国际",["clock":"13:35","sub":30,"subof":48]}
旧的 {"t":"scene",…} 仍然可用：morning→today，watch→watch，booth→booth，stop→idle，close 还是原来的收盘场景。
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
from pathlib import Path

from scenes import DEFAULTS, SceneEngine

MODES = ("watch", "weather", "today", "clock", "idle", "booth")
DISPLAY_MODES = ("simple", "compact", "pro")
ROTATING = ("watch", "weather", "today")
MAX_STOCKS, MAX_CITIES = 8, 6
OPEN_HOLD = 12.0   # 点了某只股票：整屏行情停多久（秒）
REFRESH = 2.0      # 行情卡刷新间隔（秒）
TICK = 0.25

DEFAULT_PROFILE = {
    "mode": "watch",
    "display": "pro",
    "watch": {"codes": ["300750", "688981", "600519", "002594", "600036"], "view": "single", "interval": 10},
    "weather": {"cities": [{"name": "苏州", "lat": 31.27, "lon": 120.74}, {"name": "北京", "lat": 39.9, "lon": 116.4},
                           {"name": "上海", "lat": 31.23, "lon": 121.47}], "interval": 10},
    "today": {"city": "苏州", "interval": 15, "brief": False},
    "booth": {"enabled": False, "dwell": 30},
    "replay": {"enabled": True, "speed": 1.0, "loop": True},
}
LABEL = {"watch": "盯盘", "weather": "天气", "today": "今天", "clock": "时钟", "idle": "待机", "booth": "展台"}


class ProfileError(ValueError):
    """设置不合法。field = 出错的设置块（watch / weather / today / booth / replay / display / mode），界面据此把错误显示在对应控件下面。"""

    def __init__(self, msg: str, field: str = ""):
        super().__init__(msg)
        self.field = field


def _num(v, lo, hi, what):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ProfileError(f"{what} 要是数字", what.split(".")[0]) from None
    return max(lo, min(hi, f))


def _bool(v, what):
    if isinstance(v, bool):
        return v
    raise ProfileError(f"{what} 要是 true / false", what.split(".")[0])


class ModeEngine(SceneEngine):
    def __init__(self, broadcast, log, path: Path):
        super().__init__(broadcast, log)
        self.path = path
        self.profile = self._load()
        self.last_face: dict | None = None   # 最近一张 face 卡：新连上的客户端马上能看到
        self.open_code: str | None = None
        self.sub: str | None = None   # 展台里现在在演哪个模式
        self.paused = False           # 暂停滚动（界面上的暂停键）
        self._wxt: dict = {}          # 城市名 -> (取数时刻, 天气任务)：提前并行取，换城市时不用等
        self._tdt: dict = {}          # 今天卡的同样缓存
        self._plock = asyncio.Lock()  # 设置一次只处理一个（查城市要联网，别互相踩）
        self.step = 0                 # 上一个 / 下一个：-1 / +1，由循环取走
        self.display_hook = None      # mock_hub 注入：显示模式变了要广播 {"t":"display"}
        self._names_try = 0.0

    # ---------- profile 读写 ----------
    def _load(self) -> dict:
        p = copy.deepcopy(DEFAULT_PROFILE)
        try:
            saved = json.loads(self.path.read_text())
            p = self._merge(p, saved, sync=True)
        except (OSError, ValueError, ProfileError):
            pass   # 没有或坏了：用默认值，下一次保存时覆盖
        return p

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.profile, ensure_ascii=False, indent=1))
            tmp.replace(self.path)
        except OSError:
            pass

    def public_profile(self) -> dict:
        """发给客户端的完整设置：watch.stocks = [{code,name}]（名称来自名单 / 行情），today.place = 经纬度。"""
        import names

        out = copy.deepcopy(self.profile)
        out["watch"]["stocks"] = [{"code": c, "name": self._stock_name(c, names)} for c in out["watch"]["codes"]]
        return out

    def _stock_name(self, code: str, names) -> str:
        from watch import WATCHLIST
        return dict(WATCHLIST).get(code) or names.lookup(code) or code

    # ---------- 校验 + 深度合并 ----------
    def _merge(self, base: dict, part: dict, sync: bool = False) -> dict:
        """把 part 合并进 base 的副本，校验并夹紧范围。sync=True（读文件）时不联网，城市必须已带经纬度。
        不认识的键直接报错。联网解析城市 / 股票名在 resolve_* 里（线程）。"""
        if not isinstance(part, dict):
            raise ProfileError("set 要是一个对象", "")
        p = copy.deepcopy(base)
        for key, val in part.items():
            if key == "mode":
                if val not in MODES:
                    raise ProfileError(f"mode 要是 {'/'.join(MODES)} 之一", "mode")
                p["mode"] = val
            elif key == "display":
                if val not in DISPLAY_MODES:
                    raise ProfileError("display 要是 simple / compact / pro", "display")
                p["display"] = val
            elif key == "watch":
                w = p["watch"]
                for k, v in (val or {}).items():
                    if k == "codes":
                        w["codes"] = self._codes(v)
                    elif k == "view":
                        if v not in ("single", "list"):
                            raise ProfileError("watch.view 要是 single / list", "watch")
                        w["view"] = v
                    elif k == "interval":
                        w["interval"] = _num(v, 3, 120, "watch.interval")
                    elif k != "stocks":   # stocks 是只读的名称表，客户端把整份 profile 回传时带着也没关系
                        raise ProfileError(f"不认识的设置项：watch.{k}", "watch")
            elif key == "weather":
                w = p["weather"]
                for k, v in (val or {}).items():
                    if k == "cities":
                        w["cities"] = self._cities(v, sync)
                    elif k == "interval":
                        w["interval"] = _num(v, 3, 120, "weather.interval")
                    else:
                        raise ProfileError(f"不认识的设置项：weather.{k}", "weather")
            elif key == "today":
                t = p["today"]
                for k, v in (val or {}).items():
                    if k == "city":
                        if not isinstance(v, str) or not v.strip():
                            raise ProfileError("today.city 要是城市名", "today")
                        t["city"] = v.strip()[:20]
                    elif k == "interval":
                        t["interval"] = _num(v, 3, 120, "today.interval")
                    elif k == "brief":
                        t["brief"] = _bool(v, "today.brief")
                    else:
                        raise ProfileError(f"不认识的设置项：today.{k}", "today")
            elif key == "booth":
                b = p["booth"]
                for k, v in (val or {}).items():
                    if k == "enabled":
                        b["enabled"] = _bool(v, "booth.enabled")
                    elif k == "dwell":
                        b["dwell"] = _num(v, 5, 300, "booth.dwell")
                    else:
                        raise ProfileError(f"不认识的设置项：booth.{k}", "booth")
            elif key == "replay":
                r = p["replay"]
                for k, v in (val or {}).items():
                    if k == "speed":
                        r["speed"] = _num(v, 0.2, 10, "replay.speed")
                    elif k in ("enabled", "loop"):
                        r[k] = _bool(v, f"replay.{k}")
                    else:
                        raise ProfileError(f"不认识的设置项：replay.{k}", "replay")
            else:
                raise ProfileError(f"不认识的设置项：{str(key)[:20]}")
        return p

    def _codes(self, v) -> list[str]:
        """自选：6 位代码（沪深）或名称（从名单里搜第一个）。最多 8 只，去重，至少 1 只。"""
        import names
        from symbols import a_share

        if not isinstance(v, list) or not v:
            raise ProfileError("watch.codes 要是至少一只股票的列表", "watch")
        out: list[str] = []
        for item in v:
            s = str(item).strip()
            if not re.fullmatch(r"\d{6}", s):
                hit = names.search(s, 1)
                if not hit:
                    raise ProfileError(f"找不到股票：{s[:20]}（用 6 位代码，或名称里的几个字）", "watch")
                s = hit[0]["code"]
            try:
                a_share(s)   # 只认沪深（北交所等 PandaAI 不支持）
            except ValueError as e:
                raise ProfileError(str(e), "watch") from None
            if s not in out:
                out.append(s)
        if len(out) > MAX_STOCKS:
            raise ProfileError(f"自选最多 {MAX_STOCKS} 只", "watch")
        return out

    def _cities(self, v, sync: bool) -> list[dict]:
        """城市：{"name","lat","lon"} 直接用；只有名字就查经纬度（geo.py，联网，第一次要 1–2 秒）。最多 6 个。"""
        from geo import geocode

        if not isinstance(v, list) or not v:
            raise ProfileError("weather.cities 要是至少一个城市的列表", "weather")
        out = []
        for c in v:
            if isinstance(c, str):
                c = {"name": c}
            if not isinstance(c, dict) or not str(c.get("name", "")).strip():
                raise ProfileError("城市要是名字或 {name, lat, lon}", "weather")
            name = str(c["name"]).strip()[:20]
            if c.get("lat") is None or c.get("lon") is None:
                try:
                    c = geocode(name) if not sync else geocode(name, timeout=0.01)
                except LookupError as e:
                    raise ProfileError(str(e), "weather") from None
                except Exception as e:
                    raise ProfileError(f"查不到 {name} 的位置（没网？）：{type(e).__name__}", "weather") from None
            lat, lon = _num(c["lat"], -90, 90, "lat"), _num(c["lon"], -180, 180, "lon")
            if not any(x["name"] == name for x in out):
                out.append({"name": name, "lat": round(lat, 3), "lon": round(lon, 3)})
        if len(out) > MAX_CITIES:
            raise ProfileError(f"城市最多 {MAX_CITIES} 个", "weather")
        return out

    # ---------- 对外：设置 / 模式 / 打开 ----------
    async def profile_set(self, part) -> tuple[bool, str, str]:
        """合并设置。返回 (ok, error)；成功会保存、广播、并按需重启当前模式。联网解析放进线程，不堵消息循环。"""
        async with self._plock:
            return await self._profile_set(part)

    async def _profile_set(self, part) -> tuple[bool, str, str]:
        try:
            new = await self._thread(self._merge, self.profile, part)
        except ProfileError as e:
            await self.log("warn", "PROFILE_BAD", str(e)[:200])
            if "查不到" in str(e) or "找不到城市" in str(e):
                await self.log("warn", "GEOCODE_FAIL", str(e)[:200])
            return False, str(e), getattr(e, "field", "")
        if "mode" not in part:   # 合并期间（联网查城市要几秒）模式可能已经被别人切了：别把它改回去
            new["mode"] = self.profile["mode"]
            if "booth" not in part or "enabled" not in (part.get("booth") or {}):
                new["booth"]["enabled"] = self.profile["booth"]["enabled"]
        if new["booth"]["enabled"] != self.profile["booth"]["enabled"]:   # 展台开关 ⇔ 模式
            new["mode"] = "booth" if new["booth"]["enabled"] else ("watch" if new["mode"] == "booth" else new["mode"])
        new["booth"]["enabled"] = new["mode"] == "booth"
        old, self.profile = self.profile, new
        self._save()
        await self.log("info", "PROFILE_SET", "设置已更新：" + ", ".join(k for k in part if k in new)[:100])
        await self.bc({"t": "profile", "profile": self.public_profile()})
        if new["display"] != old["display"] and self.display_hook:   # 显示模式也可以通过 profile.set 改：同步给 {"t":"display"} 的订阅者
            await self.display_hook(new["display"])
        self.prefetch()
        mode_changed = new["mode"] != old["mode"] or (self.name in MODES and self.name != new["mode"])
        if mode_changed:
            await self.set_mode(new["mode"], persist=False)
        elif self.name in ("watch", "weather", "today", "booth") and any(old[k] != new[k] for k in ("watch", "weather", "today", "booth", "replay")):
            await self._start_mode(self.name)   # 条目变了：从头滚
        return True, "", ""

    async def set_mode(self, name: str, persist: bool = True) -> bool:
        if name not in MODES:
            await self.log("warn", "MODE_BAD", f"不认识的模式：{str(name)[:20]}（{' / '.join(MODES)}）")
            return False
        self.paused = False
        self.profile["mode"] = name
        self.profile["booth"]["enabled"] = name == "booth"   # 展台模式 ⇔ booth.enabled
        if persist:
            self._save()
            await self.bc({"t": "profile", "profile": self.public_profile()})
        await self.log("info", "MODE_CHANGE", f"模式 → {name}（{LABEL[name]}）")
        await self._start_mode(name)
        return True

    async def _start_mode(self, name: str) -> None:
        await self.stop(quiet=True)
        self.name = name
        self.skip.clear()
        self.open_code = None
        self.sub = None
        if name == "clock":
            await self._state("clock", 1, 1, label="时钟", item="时钟")
            await self._face("decoy", None)
        elif name == "idle":
            await self._state("idle", 1, 1, label="待机", item="待机")
            await self._face("idle", None)
        else:
            self.task = asyncio.create_task(self._mode_run(name))

    async def open(self, code: str) -> None:
        """点了某只股票：整屏行情停 OPEN_HOLD 秒。只在盯盘模式里有意义。"""
        if self.name not in ("watch", "booth") or not re.fullmatch(r"\d{6}", str(code)):
            await self.log("warn", "OPEN_BAD", f"现在不在盯盘模式，或代码不对：{str(code)[:10]}")
            return
        self.open_code = str(code)
        self.skip.set()   # 叫醒等待，马上切过去

    async def symbols(self, q: str) -> list[dict]:
        import names

        hits = names.search(str(q)[:20], 8)
        if not hits and time.time() - self._names_try > 600 and names.known_count() < 1000:   # 名单还是内置的小份：试着从 PandaAI 更新一次
            self._names_try = time.time()
            try:
                n = await self._thread(names.refresh)
                await self.log("info", "NAMES_REFRESH", f"股票名单已更新：{n} 只")
                hits = names.search(str(q)[:20], 8)
            except BaseException as e:
                await self.log("warn", "NAMES_FAIL", f"股票名单更新失败，只能搜内置的常见股票：{type(e).__name__}: {e}"[:200])
        return hits

    async def set_display(self, mode: str) -> None:
        if mode in DISPLAY_MODES and self.profile["display"] != mode:
            self.profile["display"] = mode
            self._save()
            await self.bc({"t": "profile", "profile": self.public_profile()})

    async def boot(self) -> None:
        """中枢启动：先把天气 / 行情拉进缓存，再进入上次保存的模式（真机一连上就有画面，不用等）。"""
        self.prefetch()
        await self.warm()
        await self.set_mode(self.profile["mode"], persist=False)

    # ---------- 旧的 scene 消息 ----------
    async def handle(self, msg: dict) -> None:
        name = str(msg.get("name", ""))
        if name in ("morning", "today"):
            await self.set_mode("today")
        elif name == "watch":
            await self.set_mode("watch")
        elif name == "booth":
            await self.set_mode("booth")
        elif name == "stop":
            await self.set_mode("idle")
        else:
            await super().handle(msg)   # close（收盘场景）和不认识的名字

    async def start(self, name: str, opts: dict) -> None:   # 旧 close 场景走这里：停掉模式
        await super().start(name, opts)

    async def _state(self, name, page, of, **extra) -> None:
        await super()._state(name, page, of, paused=self.paused, **extra)

    # ---------- 提前取数（联网慢：天气一个城市 2–10 秒，今天卡 9 秒）----------
    def _wx_task(self, place: dict):
        from weather import get_weather
        hit = self._wxt.get(place["name"])
        if hit and time.time() - hit[0] < (900 if not (hit[1].done() and hit[1].exception()) else 30):
            return hit[1]
        t = asyncio.ensure_future(self._thread(get_weather, {"city": place["name"], "lat": place["lat"], "lon": place["lon"]}))
        t.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)   # 没人等的失败也不要报 "never retrieved"
        self._wxt[place["name"]] = (time.time(), t)
        return t

    def _today_task(self, city: str):
        from geo import geocode
        from today import get_today
        hit = self._tdt.get(city)
        if hit and time.time() - hit[0] < (60 if not (hit[1].done() and hit[1].exception()) else 15):
            return hit[1]

        def build():
            try:
                g = geocode(city)
                place = {"city": g["name"], "lat": g["lat"], "lon": g["lon"]}
            except Exception:
                place = None
            return get_today(place=place, codes=self.profile["watch"]["codes"])

        t = asyncio.ensure_future(self._thread(build))
        t.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        self._tdt[city] = (time.time(), t)
        return t

    def prefetch(self) -> None:
        """把设置里的所有城市天气、今天卡、行情都在后台取一遍。"""
        for c in self.profile["weather"]["cities"]:
            self._wx_task(c)
        self._today_task(self.profile["today"]["city"])
        asyncio.ensure_future(self._day_for(self.profile["watch"]["codes"]))

    # ---------- 暂停 / 上一个 / 下一个 ----------
    async def ctl(self, op: str) -> bool:
        """{"t":"mode_ctl","op":"prev|next|pause|resume"}：只对会滚动的模式有意义（watch / weather / today / booth）。"""
        if op not in ("prev", "next", "pause", "resume"):
            await self.log("warn", "MODE_BAD", f"不认识的 mode_ctl：{str(op)[:20]}")
            return False
        if op in ("pause", "resume"):
            self.paused = op == "pause"
            self.last_state = {**self.last_state, "paused": self.paused}
            await self.bc(self.last_state)
            await self.log("info", "MODE_CHANGE", f"{LABEL.get(self.name, self.name)}：{'暂停' if self.paused else '继续'}滚动")
            return True
        if self.task and not self.task.done():
            self.step = 1 if op == "next" else -1
            self.skip.set()
        return True

    async def _wait(self, seconds: float) -> bool:
        """等 seconds 秒；老板键 / 暂停时时间不走。返回 True = 被 touch / 上一个 / 下一个 / 点开某只股票叫醒了（暂停时这三样仍然有效）。"""
        left = seconds
        while left > 0:
            if self.boss or self.paused:
                if self.step or self.open_code:
                    self.skip.clear()
                    return True
                self.skip.clear()
                await asyncio.sleep(0.25)
                continue
            if await self._sleep_or_skip(min(0.25, left)):
                return True
            left -= 0.25
        return False

    def _dir(self) -> int:
        """取走 step：被叫醒后往前还是往后（touch = 往前）。"""
        d, self.step = (self.step or 1), 0
        return d

    # ---------- 发给客户端 ----------
    async def _face(self, state: str, card: dict | None) -> None:
        msg = {"t": "face", "state": state}
        if card is not None:
            msg["card"] = card
        self.last_face = msg
        await self.bc(msg)

    async def _push(self, state: str, card: dict, page: int, of: int, label: str, **extra) -> None:
        if self.sub:
            extra["booth"] = True
        await self._state(self.sub or self.name, page, of, label=label, item=label, **extra)
        await self._face(state, card)

    # ---------- 模式主循环 ----------
    async def _mode_run(self, name: str) -> None:
        try:
            if name == "booth":
                await self._booth()
            else:
                await getattr(self, f"_m_{name}")()
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            await self.log("error", "SCENE_CRASH", f"模式 {name} 出错退出：{type(e).__name__}: {e}"[:300])

    async def _booth(self) -> None:
        dwell = self.profile["booth"]["dwell"]
        while True:
            for m in ROTATING:
                self.sub = m
                body = asyncio.create_task(getattr(self, f"_m_{m}")())
                try:
                    left = dwell
                    while left > 0 and not body.done():   # 暂停时停留时间不走
                        await asyncio.wait([body], timeout=0.25)
                        if not self.paused and not self.boss:
                            left -= 0.25
                    if body.done() and not body.cancelled() and body.exception():   # 这个模式崩了：记日志，下一个
                        await self.log("error", "SCENE_CRASH", f"展台里的 {m} 出错：{body.exception()}"[:300])
                finally:
                    if not body.done():
                        body.cancel()
                        try:
                            await body
                        except BaseException:
                            pass

    async def _day_for(self, codes) -> dict:
        from watch import load_day
        day = await self._thread(load_day, 600, tuple(codes))
        import names
        for st in day["stocks"]:
            names.learn(st["code"], st["name"])
        if id(day) not in self._warned:
            self._warned.add(id(day))
            if day["source"] != "panda":
                await self.log("warn", "API_MARKET_FAIL", f"行情走 {day['source']}（{day.get('warn') or '没有账号 / 没网'}）；示例数据会在屏幕上标明")
            elif day.get("interp"):
                await self.log("warn", "REPLAY_INTERP", "5 分钟线不够，这几只用日线插值：" + ",".join(day["interp"]))
        return day

    # ----- 盯盘 -----
    async def _m_watch(self) -> None:
        from watch import MAX_ROWS, TIMES, mover_card, stock_state, watch_card

        P, R = self.profile["watch"], self.profile["replay"]
        day = await self._day_for(P["codes"])
        n = len(day["stocks"])
        single = P["view"] == "single"
        items = n if single else -(-n // MAX_ROWS)
        nbars = len(TIMES)
        i: int | None = 0 if R["enabled"] else None
        acc = since_push = since_item = 0.0
        item, seen, last_item = 0, set(), -1
        open_until, open_k = 0.0, None
        while True:
            await self._unpaused()
            now = time.monotonic()
            # 点了某只股票：切过去停 OPEN_HOLD 秒
            if self.open_code:
                code, self.open_code = self.open_code, None
                k = next((j for j, s in enumerate(day["stocks"]) if s["code"] == code), None)
                if k is None:   # 不在自选里：单独取这一只
                    day2 = await self._day_for([code])
                    day, k = day2, 0
                    n = len(day["stocks"])
                open_k, open_until, since_push = k, now + OPEN_HOLD, 1e9
            if open_k is not None and now >= open_until:
                open_k, since_item, last_item = None, 0.0, -1
                day = await self._day_for(P["codes"])
                n = len(day["stocks"])
            # 回放里的异动：第一次触及 ±2% / ±3%
            if i is not None and open_k is None:
                alert = None
                for k in range(n):
                    pct = stock_state(day, k, i)["pct"]
                    for lvl in (2, 3):
                        key = (day["stocks"][k]["code"], pct > 0, lvl)
                        if abs(pct) >= lvl and key not in seen:
                            seen.add(key)
                            alert = (k, pct, lvl)
                if alert:
                    k, pct, lvl = alert
                    s = day["stocks"][k]
                    text = f"{s['name']} {pct:+.2f}% · 触及 ±{lvl}% · {TIMES[i]}"
                    await self.log("info", "SCENE_ALERT", text)
                    await self.bc({"t": "notice", "level": "info", "text": text})
                    await self._push("mkt", mover_card(day, k, i), k + 1, n, s["name"], clock=TIMES[i], sub=i + 1, subof=nbars)
                    await self._wait(self.opts["alert_hold"])
                    since_push, since_item, last_item = 1e9, 0.0, -1
            # 推卡
            if open_k is not None:
                if since_push >= REFRESH:
                    since_push = 0
                    s = day["stocks"][open_k]
                    await self._push("mkt", mover_card(day, open_k, i, "close" if i is None else "replay", alert=False), open_k + 1, n, s["name"],
                                     **({} if i is None else {"clock": TIMES[i], "sub": i + 1, "subof": nbars}))
            elif item != last_item or since_push >= REFRESH:
                since_push, last_item = 0, item
                extra = {} if i is None else {"clock": TIMES[i], "sub": i + 1, "subof": nbars}
                mode = "close" if i is None else "replay"
                if single:
                    s = day["stocks"][item]
                    await self._push("mkt", mover_card(day, item, i, mode, alert=False), item + 1, items, s["name"], **extra)
                else:
                    await self._push("watch", watch_card(day, mode, i, (), start=item * MAX_ROWS), item + 1, items, f"自选 {item + 1}/{items}", **extra)
            # 等一小格；touch = 下一只（详情里 = 回到滚动）
            skipped = await self._wait(TICK)
            if self.open_code:
                continue
            if skipped:
                d = self._dir()
                if open_k is not None:
                    open_k, since_item, last_item = None, 0.0, -1
                else:
                    item, since_item = (item + d) % items, 0.0
            elif open_k is None:
                since_item += TICK
                if since_item >= P["interval"]:
                    item, since_item = (item + 1) % items, 0.0
            since_push += TICK
            if i is not None:   # 回放的时钟走一格
                acc += TICK
                while acc >= R["speed"]:
                    acc -= R["speed"]
                    i += 1
                    since_push = max(since_push, 0)
                    if i >= nbars:
                        if R["loop"]:
                            i, seen = 0, set()
                        else:
                            i = None   # 回放结束：停在收盘数据
                        break

    # ----- 天气 -----
    async def _m_weather(self) -> None:
        from weather import to_card

        cities = self.profile["weather"]["cities"]
        gap = self.profile["weather"]["interval"]
        for c in cities:   # 全部城市一起开始取，慢的城市不挡着前面的
            self._wx_task(c)
        idx, fails = 0, 0
        while True:
            await self._unpaused()
            place = cities[idx % len(cities)]
            try:
                w = await asyncio.shield(self._wx_task(place))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                fails += 1
                await self.log("warn", "API_WEATHER_FAIL", f"{place['name']} 的天气取不到，跳过：{type(e).__name__}: {e}"[:200])
                if fails >= len(cities):   # 全断网：别空转
                    fails = 0
                    await self._wait(10)
                idx += 1
                continue
            fails = 0
            await self._push("sky", to_card(w), idx % len(cities) + 1, len(cities), place["name"])
            self._wx_task(cities[(idx + 1) % len(cities)])   # 下一个城市（过期了就重取）
            idx += self._dir() if await self._wait(gap) else 1

    # ----- 今天 -----
    async def _m_today(self) -> None:
        T = self.profile["today"]
        pages = 2 if T["brief"] else 1
        page = 0
        while True:
            await self._unpaused()
            if page == 0:
                try:
                    out = await asyncio.shield(self._today_task(T["city"]))
                    if id(out) not in self._warned:
                        self._warned.add(id(out))
                        for code, text in out.get("warnings", []):
                            await self.log("warn", code, text)
                    await self._push("today", out["card"], 1, pages, "今天")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    await self.log("warn", "API_TODAY_FAIL", f"今天这一屏取不到：{type(e).__name__}: {e}"[:200])
                    await self._wait(10)
                    continue
            else:
                built = await self._get("brief")
                if built:
                    await self._push("brief", built[1], 2, pages, "盘前简报")
            skipped = await self._wait(T["interval"] if pages > 1 else 60)   # 单页：每分钟刷新（日期 / 倒计时 / 天气）
            page = (page + (self._dir() if skipped else 1)) % pages
