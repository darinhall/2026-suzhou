"""主动提醒：提醒阶梯（T15）。纯逻辑，不联网、不碰 WebSocket，中枢每走一格回放调一次 check()。

    0 安静（不返回）· 1 瞥一眼（接近阈值）· 2 转头（触及阈值）· 3 叫你（急涨急跌 / 放量 / 涨跌停）

阈值来自人格（brain/personas.json）。每个"事件"只提醒一次：同一只股票、同一方向、同一种事件。
两次 ≥2 级的提醒之间至少隔 cooldown_s 秒（墙上时间）；冷却中的事件不记为已提醒，过了冷却还满足就再报。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

LEVEL_NAMES = {1: "glance", 2: "look", 3: "call"}


@dataclass
class Tick:
    """某只股票"到这一刻为止"的状态。closes = [昨收, 第 1 根, …, 现在]（data/watch.py 的 _series），用来算 5 分钟变化。"""
    code: str
    name: str
    pct: float
    price: float
    closes: list[float] = field(default_factory=list)
    vol_ratio: float | None = None
    limit_up: float | None = None
    limit_down: float | None = None


@dataclass
class Alert:
    code: str
    name: str
    level: int
    kind: str          # glance | cross | surge | volume | limit
    pct: float
    say: str           # 字幕 / 喇叭念的话（数字都来自 facts）
    facts: dict

    @property
    def gesture(self) -> str:
        return LEVEL_NAMES[self.level]

    def message(self, clock: str = "", persona: str = "") -> dict:
        """protocol.md 的 {"t":"alert"} 消息。"""
        return {"t": "alert", "code": self.code, "name": self.name, "level": self.level, "kind": self.kind,
                "pct": round(self.pct, 2), "clock": clock, "say": self.say, "persona": persona}


def _say(kind: str, t: Tick, extra: dict) -> str:
    up = t.pct >= 0
    if kind == "glance":
        return f"{t.name}{'涨' if up else '跌'}了 {abs(t.pct):.1f}%，我先帮你看着。"
    if kind == "cross":
        return f"{t.name}{'涨' if up else '跌'}到 {abs(t.pct):.1f}%，要看看吗？"
    if kind == "surge":
        d = extra["move_5m_pct"]
        return f"{t.name} 5 分钟{'急涨' if d >= 0 else '急跌'} {abs(d):.1f}%，现在{'涨' if up else '跌'} {abs(t.pct):.1f}%。"
    if kind == "volume":
        return f"{t.name}放量了，量比 {extra['vol_ratio']:.1f}，{'涨' if up else '跌'} {abs(t.pct):.1f}%。"
    if kind == "limit":
        return f"{t.name}{'涨停' if up else '跌停'}了。"
    return t.name


class AlertWatcher:
    def __init__(self, persona: dict, clock=time.monotonic):
        self.persona = persona
        self.cfg = persona["alerts"]
        self.clock = clock
        self.seen: set[tuple] = set()
        self.last_big = -1e9   # 上一次 ≥2 级提醒的时间

    def reset(self) -> None:
        """回放从头开始：所有事件重新可以提醒。"""
        self.seen.clear()
        self.last_big = -1e9

    def set_persona(self, persona: dict) -> None:
        """换人格：阈值立刻生效，已提醒过的事件保留（不会把刚提醒过的再报一遍）。"""
        self.persona, self.cfg = persona, persona["alerts"]

    def _candidates(self, t: Tick) -> list[tuple[int, str, dict]]:
        c = self.cfg
        out: list[tuple[int, str, dict]] = []
        a = abs(t.pct)
        if c.get("down_only") and t.pct > 0:
            return out
        if t.limit_up and t.price >= t.limit_up - 1e-6 or t.limit_down and t.price <= t.limit_down + 1e-6:
            out.append((3, "limit", {}))
        if len(t.closes) >= 3 and t.closes[-2]:   # 第 1 根相对昨收是开盘跳空，不算急涨急跌
            move = (t.closes[-1] / t.closes[-2] - 1) * 100
            if abs(move) >= c["surge_pct_5m"]:
                out.append((3, "surge", {"move_5m_pct": round(move, 2)}))
        # 量比开盘半小时内总是偏高（按已过时间折算），前 6 根不看
        if t.vol_ratio and len(t.closes) > 7 and t.vol_ratio >= c["vol_ratio"] and a >= c["cross_pct"] * c["glance_ratio"]:
            out.append((3, "volume", {"vol_ratio": t.vol_ratio}))
        if a >= c["cross_pct"]:
            out.append((2, "cross", {}))
        elif a >= c["cross_pct"] * c["glance_ratio"]:
            out.append((1, "glance", {}))
        return out

    def check(self, ticks: list[Tick]) -> list[Alert]:
        """返回这一格要提醒的事件，级别高的在前。调用方一般只演第一个 ≥2 级的，其余 1 级可以都演（只是屏幕动画）。"""
        now = self.clock()
        cooling = now - self.last_big < self.cfg["cooldown_s"]
        max_level = self.cfg["max_level"]
        found: list[Alert] = []
        big_taken = False
        for t in ticks:
            for level, kind, extra in self._candidates(t):
                level = min(level, max_level)
                key = (t.code, t.pct >= 0, kind)
                if key in self.seen:
                    continue
                if level >= 2 and (cooling or big_taken):
                    continue   # 冷却中：不记 seen，过了冷却还满足就再报
                self.seen.add(key)
                if kind != "glance":
                    self.seen.add((t.code, t.pct >= 0, "glance"))   # 已经转头了，就别再"瞥一眼"
                facts = {"name": t.name, "code": t.code, "day_pct": round(t.pct, 2), "price": t.price, **extra}
                found.append(Alert(t.code, t.name, level, kind, t.pct, _say(kind, t, extra), facts))
                if level >= 2:
                    big_taken = True
                    self.last_big = now
        found.sort(key=lambda x: (-x.level, -abs(x.pct)))
        return found
