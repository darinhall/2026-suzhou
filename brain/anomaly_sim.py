"""行情异动模拟（周末 / 休市演示用）：「行情异动模拟」→ 自选股按剧本出几次异动，走真正的提醒阶梯（brain/alerts.py）。

    steps(day, persona) → [Step, …]，中枢按 delay 一步步演：卡片 + 转头 / 点头 / 摇头 + 念出来

基准价格是最近一个交易日的真实收盘（PandaAI），异动是编出来的：卡片和日志都标「模拟」，不会冒充真实行情。
剧本：瞥一眼（接近阈值）→ 5 分钟急涨（3 级：转头 + 点头）→ 跌破阈值（2 级：转头）→ 放量（3 级）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from brain.alerts import Alert, AlertWatcher, Tick

# (第几只自选, 依次经过的涨跌幅 %, 量比)：最后一个点是"现在"，倒数第二个是 5 分钟前
SCRIPT = [
    (3, [0.2, 0.6, 0.9, 1.2, 1.5], None),     # 接近阈值：1 级，瞥一眼
    (1, [0.3, 0.5, 0.6, 0.8, 2.9], None),     # 5 分钟急涨 2.1%：3 级
    (0, [-0.4, -0.9, -1.4, -1.8, -2.3], None),  # 跌破 -2%：2 级
    (2, [0.4, 0.7, 0.9, 1.2, 1.6], 3.2),      # 放量：3 级
]
GAP_S = 14   # 两次提醒之间隔几秒（现场演示的节奏）


@dataclass
class Step:
    delay: float
    alert: Alert
    card: dict | None   # ≥2 级才换卡片


def _card(base: dict, closes: list[float], pct: float, alert: Alert, vol_ratio) -> dict:
    card = copy.deepcopy(base)
    price = closes[-1]
    card.update({"pct": round(pct, 2), "price": round(price, 2), "spark": [round(x, 2) for x in closes],
                 "high": round(max(card.get("high", price), price), 2), "low": round(min(card.get("low", price), price), 2),
                 "alert": True, "say": alert.say, "level": alert.level, "mode": "sample",
                 "asof": "模拟异动", "legal": "模拟异动 · 基准价为最近收盘 · 不构成投资建议", "hint": "说“停止模拟”结束"})
    if vol_ratio:
        card["vol_ratio"] = vol_ratio
    return card


def steps(day: dict, persona: dict) -> list[Step]:
    from watch import mover_card, stock_state
    p = copy.deepcopy(persona)
    p["alerts"]["cooldown_s"] = 0   # 剧本自己控制节奏
    watcher = AlertWatcher(p)
    n = len(day["stocks"])
    calm = {k: stock_state(day, k, None)["prev_close"] for k in range(n)}
    out: list[Step] = []
    for idx, (k, path, vr) in enumerate(SCRIPT):
        k = k % n
        st = stock_state(day, k, None)
        prev = st["prev_close"]
        closes = [prev * (1 + x / 100) for x in path]
        ticks = []
        for j in range(n):   # 别的自选平静：只有剧本里这一只在动
            if j == k:
                ticks.append(Tick(st["code"], st["name"], path[-1], round(closes[-1], 2), [prev] * 4 + closes, vr))
            else:
                s2 = stock_state(day, j, None)
                ticks.append(Tick(s2["code"], s2["name"], 0.1, calm[j], [calm[j]] * 9))
        alerts = [a for a in watcher.check(ticks) if a.code == st["code"]]
        if not alerts:
            continue
        a = alerts[0]
        card = _card(mover_card(day, k, None, "close", alert=True), closes, path[-1], a, vr) if a.level >= 2 else None
        out.append(Step(4 if idx == 0 else GAP_S, a, card))
    return out
