"""「今天」：日期 + A 股交易状态 + 天气 + 下一个日程，拼成屏幕 face 消息里的 card。

    python3 data/today.py                                            # 交易日历用"周一到周五"估算
    uv run --python 3.12 --with panda-data==1.0.5 python data/today.py   # 用 PandaAI 的交易日历（要 data/.env 里的账号）

日程来自 data/schedule.json（示例），以后换成飞书日历。
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from weather import get_weather   # noqa: E402

WEEK = "一二三四五六日"


def trading_day(day: datetime.date) -> tuple[bool, str]:
    """今天是不是 A 股交易日。有 panda_data 和账号就问 PandaAI 的交易日历（会算上节假日），否则按周一到周五估。"""
    try:
        from panda_client import PandaClient, login   # 没装 panda_data 会 ImportError
        login()
        d = day.strftime("%Y%m%d")
        return len(PandaClient().trade_days(d, d)) > 0, "PandaAI 交易日历"
    except Exception:
        return day.weekday() < 5, "估算：周一到周五，没查节假日"


def market_status(now: datetime.datetime, is_trading: bool) -> str:
    """休市 / 盘前 / 交易中 / 午休 / 已收盘（A 股：9:30–11:30，13:00–15:00）。"""
    if not is_trading:
        return "休市"
    t = now.hour * 60 + now.minute
    if t < 9 * 60 + 30:
        return "盘前"
    if t < 11 * 60 + 30:
        return "交易中"
    if t < 13 * 60:
        return "午休"
    if t < 15 * 60:
        return "交易中"
    return "已收盘"


def next_event(now: datetime.datetime) -> dict | None:
    events = json.loads((HERE / "schedule.json").read_text())["events"]
    for e in sorted(events, key=lambda e: e["time"]):
        h, m = map(int, e["time"].split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if start > now:
            mins = int((start - now).total_seconds() // 60)
            return {**e, "in": f"{mins} 分钟后" if mins < 60 else f"{round(mins / 60)} 小时后"}
    return None


def get_today(now: datetime.datetime | None = None) -> dict:
    now = now or datetime.datetime.now()
    is_trading, source = trading_day(now.date())
    w = get_weather()
    nw, tm, ev = w["now"], w["tomorrow"], next_event(now)
    r = lambda v: None if v is None else round(v)   # noqa: E731
    card = {
        "month": now.month, "day": now.day, "weekday": "周" + WEEK[now.weekday()],
        "market": market_status(now, is_trading),
        "city": nw["city"], "temp": r(nw["temp"]), "text": nw["text"],
        "tmr_text": tm["text"], "tmr_lo": r(tm["low"]), "tmr_hi": r(tm["high"]),
    }
    if ev:
        card.update(next_time=ev["time"], next_in=ev["in"], next_title=ev["title"], next_where=ev["where"])
    return {"card": card, "market_source": source}


if __name__ == "__main__":
    out = get_today()
    print(json.dumps(out["card"], ensure_ascii=False))
    print("交易日来源：", out["market_source"])
