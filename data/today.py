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

from weather import get_weather, to_wx   # noqa: E402

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


def next_open(now: datetime.datetime) -> tuple[str, str] | None:
    """下一次 A 股开盘（09:30）："11-02 09:30" 和距现在多久 "1 天 19 小时"。
    用 PandaAI 交易日历（会算上节假日），没有就按周一到周五估算。"""
    days: list[datetime.date] = []
    try:
        from panda_client import PandaClient, login
        login()
        end = now.date() + datetime.timedelta(days=20)
        cal = PandaClient().trade_days(now.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        days = sorted(datetime.datetime.strptime(str(d), "%Y%m%d").date() for d in cal["nature_date"])
    except BaseException:
        days = [now.date() + datetime.timedelta(days=i) for i in range(10) if (now.date() + datetime.timedelta(days=i)).weekday() < 5]
    for d in days:
        opening = datetime.datetime.combine(d, datetime.time(9, 30))
        if opening > now:
            mins = int((opening - now).total_seconds() // 60)
            if mins >= 24 * 60:
                left = f"{mins // 1440} 天 {mins % 1440 // 60} 小时"
            elif mins >= 60:
                left = f"{mins // 60} 小时 {mins % 60} 分"
            else:
                left = f"{mins} 分钟"
            return opening.strftime("%m-%d %H:%M"), left
    return None


def upcoming_events(now: datetime.datetime, n: int = 3) -> tuple[list[dict], bool]:
    """接下来的 n 条日程 [{time,title}] 和"是不是示例"（schedule.json 里写了 sample:true 就是示例，接上飞书日历后改成 false）。"""
    data = json.loads((HERE / "schedule.json").read_text())
    out = []
    for e in sorted(data["events"], key=lambda e: e["time"]):
        h, m = map(int, e["time"].split(":"))
        if now.replace(hour=h, minute=m, second=0, microsecond=0) > now:
            out.append({"time": e["time"], "title": e["title"]})
    return out[:n], bool(data.get("sample", True))


def get_fx() -> list[dict] | None:
    """[{pair:"USD/CNY",rate,pct}]×3（ECB 日更参考汇率，不是实时报价）；JPY 是每 100 日元（带 per:100）。失败用缓存，没有缓存返回 None。"""
    from watch import cache_get, cache_put
    try:
        from fx import get_rates
        rates = get_rates([("USD", "CNY"), ("EUR", "CNY"), ("JPY", "CNY")])
        out = []
        for r in rates:
            item = {"pair": f"{r['base']}/{r['quote']}", "rate": r["rate"], "pct": r["pct"]}
            if r["per"] != 1:
                item["per"] = r["per"]
            out.append(item)
        if not out:
            raise ValueError("没有汇率")
        cache_put("fx", {"items": out})
        return out
    except BaseException:
        c = cache_get("fx")
        return c["items"] if c else None


def get_today(now: datetime.datetime | None = None, place: dict | None = None, codes=None) -> dict:
    """"今天"卡（v2）：旧字段全部保留，另加
    lunar · next_open · open_in · last_idx{name,value,pct} · wx{…} · events[{time,title}]≤3 · fx[{pair,rate,pct}]≤3 · brief · overnight[{name,pct}] · sample{events,overnight}。
    某一项取不到就没有这个 key，不会用假值补；返回的 "warnings" 是 [(日志代码, 说明)]，中枢记进日志。"""
    from concurrent.futures import ThreadPoolExecutor

    now = now or datetime.datetime.now()
    warnings: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_trading = pool.submit(trading_day, now.date())
        f_weather = pool.submit(get_weather, place) if place else pool.submit(get_weather)
        f_open = pool.submit(next_open, now)
        f_fx = pool.submit(get_fx)
        f_over = pool.submit(lambda: __import__("overnight").get_overnight())
        f_day = pool.submit(lambda: __import__("watch").load_day(codes=codes))
        is_trading, source = f_trading.result()
        w = f_weather.result()   # 天气是这一屏的主角：失败就整张卡失败，由调用方决定怎么办
        extras = {}
        for key, fut in (("open", f_open), ("fx", f_fx), ("over", f_over), ("day", f_day)):
            try:
                extras[key] = fut.result()
            except BaseException as e:
                extras[key] = None
                warnings.append(("API_MARKET_FAIL", f"今天这一屏的 {key} 取不到：{type(e).__name__}: {e}"[:200]))
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

    from lunar import lunar_text
    if lunar_text(now.date()):
        card["lunar"] = lunar_text(now.date())
    if extras["open"]:
        card["next_open"], card["open_in"] = extras["open"]
    day = extras["day"]
    if day and day.get("indices"):
        ix = day["indices"][0]
        card["last_idx"] = {"name": "上证", "value": round(ix["closes"][-1], 2), "pct": round((ix["closes"][-1] / ix["prev_close"] - 1) * 100, 2)}
        if day["source"] == "sample":
            card["last_idx"]["sample"] = True
    card["wx"] = to_wx(w)
    events, events_sample = upcoming_events(now)
    if events:
        card["events"] = events
    if extras["fx"]:
        card["fx"] = extras["fx"]
    else:
        warnings.append(("API_FX_FAIL", "汇率（Frankfurter）取不到，今天这一屏不显示汇率"))
    over = extras["over"]
    if over:
        card["overnight"] = over["items"]
    else:
        warnings.append(("API_OVERNIGHT_FAIL", "隔夜外盘（PandaAI 美股指数）取不到，今天这一屏不显示"))
    if day:
        from brief import one_line
        card["brief"] = one_line(w, day, now)
    card["sample"] = {"events": bool(events) and events_sample, "overnight": False}
    return {"card": card, "market_source": source, "warnings": warnings}


if __name__ == "__main__":
    out = get_today()
    print(json.dumps(out["card"], ensure_ascii=False))
    print("交易日来源：", out["market_source"])
