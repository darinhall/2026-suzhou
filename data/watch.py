"""自选盯盘的数据：最近一个交易日的 5 分钟行情（回放用）、三大指数、市场天气（全市场涨跌家数），拼成屏幕的 watch / mkt / weather 卡。

    uv run --python 3.12 --with panda-data==1.0.5 python data/watch.py          # 打印 watch 卡、一张 mkt 卡、市场天气

数据来源 PandaAI（实测 2026-10-31）：
- 股票 5 分钟线：每天 48 根（09:35…11:30、13:05…15:00），免费账号可用。
- 指数 1 分钟线：可用，这里按 5 分钟的时刻抽样。
- 全市场日线（不传 symbol）：一次 2–3 秒拿到 5000+ 只，所以"涨跌家数"是真的数出来的。
- 盘中实时（get_stock_rt_daily / rt_min）：休市时返回空，免费号盘中是否可用没验证过，所以 live 只做尽力而为。

降级顺序：PandaAI → data/cache/*.json（上一次成功的数据，网络断了也能演）→ 示例数据（mode:"sample"，屏幕上会写"示例数据"，不会冒充真的）。
分钟线拿不到时，用当天日线的 开 / 高 / 低 / 收 插值出 48 个点（day["interp"] 里记下是哪几只）。
"""

from __future__ import annotations

import datetime
import json
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

CACHE = HERE / "cache"
WATCHLIST = [("300750", "宁德时代"), ("600519", "贵州茅台"), ("002594", "比亚迪")]
INDICES = [("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指")]

# 5 分钟线的 48 个时刻：09:35…11:30、13:05…15:00
def _make_times() -> list[str]:
    out, t = [], datetime.datetime(2000, 1, 1, 9, 35)
    while t.hour * 60 + t.minute <= 11 * 60 + 30:
        out.append(t.strftime("%H:%M"))
        t += datetime.timedelta(minutes=5)
    t = datetime.datetime(2000, 1, 1, 13, 5)
    while t.hour * 60 + t.minute <= 15 * 60:
        out.append(t.strftime("%H:%M"))
        t += datetime.timedelta(minutes=5)
    return out


TIMES = _make_times()   # 48 个


# ---------- 缓存 ----------
def _cache_put(name: str, obj: dict) -> None:
    try:
        CACHE.mkdir(exist_ok=True)
        (CACHE / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False))
    except OSError:
        pass


def _cache_get(name: str) -> dict | None:
    try:
        return json.loads((CACHE / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


# ---------- 插值 / 示例 ----------
def interpolate_day(o: float, h: float, lo: float, c: float, n: int = len(TIMES)) -> list[float]:
    """分钟线拿不到时，用日线 开高低收 插出 n 个点：先到低点再到高点（收阳），或先高后低（收阴）。"""
    path = [o, lo, h, c] if c >= o else [o, h, lo, c]
    out = []
    for i in range(n):
        x = (i + 1) / n * (len(path) - 1)
        k = min(int(x), len(path) - 2)
        out.append(round(path[k] + (path[k + 1] - path[k]) * (x - k), 3))
    return out


def sample_day() -> dict:
    """完全没有数据时的示例：固定种子的随机游走。屏幕上标"示例数据"。"""
    rnd = random.Random(1031)
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)

    def walk(prev: float, drift: float, vol: float) -> list[float]:
        v, out = prev, []
        for i in range(len(TIMES)):
            v *= 1 + drift / len(TIMES) + rnd.gauss(0, vol)
            out.append(round(v, 2))
        return out

    stocks = [{"code": c, "name": n, "prev_close": p, "closes": walk(p, dr, 0.0018), "interp": False}
              for (c, n), p, dr in zip(WATCHLIST, (210.0, 1450.0, 255.0), (0.035, -0.012, -0.03))]
    indices = [{"code": c, "name": n, "prev_close": p, "closes": walk(p, dr, 0.0004)}
               for (c, n), p, dr in zip(INDICES, (3600.0, 11800.0, 2500.0), (0.004, -0.002, -0.012))]
    return {"date": d.strftime("%Y%m%d"), "source": "sample", "stocks": stocks, "indices": indices, "interp": []}


# ---------- 取数 ----------
def _ffill(series: dict, prev: float) -> list[float]:
    """按 TIMES 取收盘价，缺的用前一个补。"""
    out, last = [], prev
    for t in TIMES:
        last = series.get(t, last)
        out.append(round(float(last), 3))
    return out


def _fetch_day() -> dict:
    from export_game import adjusted
    from panda_client import PandaClient, login

    login()
    c = PandaClient()
    last = c.last_trade_date()
    start = (datetime.datetime.strptime(last, "%Y%m%d") - datetime.timedelta(days=60)).strftime("%Y%m%d")
    codes = [c_ for c_, _ in WATCHLIST]
    daily = c.get_bars("a", codes, start, last)
    if "trade_status" in daily.columns:
        daily = daily[daily["trade_status"] == 0]

    try:
        mins = c.get_minute("a", codes, last, last, "5m")
    except Exception:
        mins = None

    stocks, interp = [], []
    for code, name in WATCHLIST:
        df = daily[daily["symbol"].str.startswith(code)]
        if not len(df):
            raise ValueError(f"{code} 没有日线")
        row = df.iloc[-1]
        prev = float(row["pre_close"])
        series = {}
        if mins is not None and len(mins):
            m = mins[mins["symbol"].str.startswith(code)]
            series = {f"{str(r['minute'])[:2]}:{str(r['minute'])[2:4]}": float(r["close"]) for _, r in m.iterrows()}
        if len(series) >= 40:
            closes = _ffill(series, prev)
        else:   # 分钟线不够：用日线插值
            closes = interpolate_day(float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
            interp.append(code)
        stocks.append({"code": code, "name": str(row["name"]) if "name" in row else name, "prev_close": prev,
                       "closes": closes, "interp": code in interp,
                       "daily": adjusted(df)[-24:]})

    indices = []
    idx_daily = c.get_bars("index", [i for i, _ in INDICES], start, last)
    try:
        idx_min = c.get_minute("index", [i for i, _ in INDICES], last, last)
    except Exception:
        idx_min = None
    for code, name in INDICES:
        df = idx_daily[idx_daily["symbol"].str.startswith(code)]
        row = df.iloc[-1]
        prev = float(row["pre_close"])
        series = {}
        if idx_min is not None and len(idx_min):
            m = idx_min[idx_min["symbol"].str.startswith(code)]
            series = {f"{str(r['minute'])[:2]}:{str(r['minute'])[2:4]}": float(r["close"]) for _, r in m.iterrows()}
        closes = _ffill(series, prev) if len(series) >= 100 else interpolate_day(float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
        indices.append({"code": code, "name": name, "prev_close": prev, "closes": closes})

    return {"date": last, "source": "panda", "stocks": stocks, "indices": indices, "interp": interp}


_mem: dict = {}


def load_day(max_age: float = 600) -> dict:
    """最近一个交易日的数据。内存缓存 10 分钟；PandaAI 失败用磁盘缓存；再不行用示例。
    返回的 dict 里 "source" 是 panda / cache / sample，"warn" 是要记日志的原因（没有就是 None）。"""
    if _mem.get("day") and time.time() - _mem["at"] < max_age:
        return _mem["day"]
    warn = None
    try:
        day = _fetch_day()
        _cache_put("day", day)
    except BaseException as e:   # login() 缺账号会 SystemExit，也要兜住
        warn = f"{type(e).__name__}: {e}"[:200]
        day = _cache_get("day")
        if day:
            day["source"] = "cache"
        else:
            day = sample_day()
    day["warn"] = warn or ("分钟线缺失，用日线插值：" + ",".join(day["interp"]) if day.get("interp") else None)
    _mem.update(day=day, at=time.time())
    return day


# ---------- 卡片 ----------
def _pct(price: float, prev: float) -> float:
    return round((price / prev - 1) * 100, 2) if prev else 0.0


def _down(seq: list[float], n: int) -> list[float]:
    """均匀抽到最多 n 个点（保留首尾）。"""
    if len(seq) <= n:
        return [round(v, 2) for v in seq]
    return [round(seq[round(i * (len(seq) - 1) / (n - 1))], 2) for i in range(n)]


def _fmt_date(date: str) -> str:
    return f"{date[4:6]}-{date[6:]}"


def asof_text(day: dict, i: int | None, mode: str) -> str:
    if day["source"] == "sample":
        return "示例数据"
    if mode == "replay" and i is not None:
        return f"{_fmt_date(day['date'])} {TIMES[i]}"
    return f"{_fmt_date(day['date'])} 收盘"


def card_mode(day: dict, mode: str) -> str:
    return "sample" if day["source"] == "sample" else mode


def stock_state(day: dict, k: int, i: int | None = None) -> dict:
    """第 k 只自选股，到第 i 根 K 线（None = 收盘）为止的状态。"""
    s = day["stocks"][k]
    i = len(TIMES) - 1 if i is None else i
    price = s["closes"][i]
    return {"name": s["name"], "code": s["code"], "pct": _pct(price, s["prev_close"]), "price": round(price, 2),
            "prev_close": round(s["prev_close"], 2), "spark": _down([s["prev_close"]] + s["closes"][:i + 1], 24)}


def index_state(day: dict, i: int | None = None) -> dict:
    ix = day["indices"][0]
    i = len(TIMES) - 1 if i is None else i
    return {"name": ix["name"], "pct": _pct(ix["closes"][i], ix["prev_close"])}


def watch_card(day: dict, mode: str = "close", i: int | None = None, alert_codes: tuple = ()) -> dict:
    """watch 卡：{"title","asof","mode","index":{name,pct},"rows":[{name,code,pct,price,spark}…≤3]}。
    mode=close 用收盘价；replay 用第 i 根；alert_codes 里的股票行多一个 alert:true。"""
    rows = []
    for k in range(min(3, len(day["stocks"]))):
        r = stock_state(day, k, None if mode == "close" else i)
        r.pop("prev_close")
        if r["code"] in alert_codes:
            r["alert"] = True
        rows.append(r)
    card = {"title": "自选", "asof": asof_text(day, i, mode), "mode": card_mode(day, mode),
            "index": index_state(day, None if mode == "close" else i), "rows": rows}
    if alert_codes:
        card["alert"] = True
    return card


def mover_card(day: dict, k: int, i: int | None, mode: str = "replay", alert: bool = True) -> dict:
    """一只股票的整屏 mkt 卡。"""
    s = stock_state(day, k, i)
    card = {**s, "asof": asof_text(day, i, mode), "mode": card_mode(day, mode), "alert": alert,
            "hint": "按头 = 记入模拟单",
            "legal": f"{asof_text(day, i, mode)} · {'回放 · ' if mode == 'replay' else ''}不构成投资建议"}
    return card


def top_movers(day: dict, i: int | None = None) -> tuple[dict, dict]:
    """自选里涨得最多 / 跌得最多的两只（可能是同一只）。"""
    sts = [stock_state(day, k, i) for k in range(min(3, len(day["stocks"])))]
    return max(sts, key=lambda s: s["pct"]), min(sts, key=lambda s: s["pct"])


def live_card(day: dict) -> dict:
    """盘中实时（尽力而为）：用 PandaAI 的当日快照拼 watch 卡，mode:"live"，没有 index 字段。
    休市时快照是空的、免费号盘中是否有权限没验证过：取不到就抛错，调用方退回回放。"""
    from panda_client import PandaClient, login

    login()
    df = PandaClient().get_snapshot([s["code"] for s in day["stocks"][:3]])
    if df is None or not len(df):
        raise RuntimeError("盘中快照为空（休市，或免费号没有盘中权限）")
    rows = []
    for s in day["stocks"][:3]:
        r = df[df["symbol"].str.startswith(s["code"])]
        if not len(r):
            raise RuntimeError(f"快照里没有 {s['code']}")
        r = r.iloc[-1]
        price = float(r["close"])
        prev = float(r["pre_close"]) if "pre_close" in r and r["pre_close"] else s["prev_close"]
        rows.append({"name": s["name"], "code": s["code"], "pct": _pct(price, prev), "price": round(price, 2),
                     "spark": _down(s.get("daily") or s["closes"], 24)})
    return {"title": "自选", "asof": time.strftime("%H:%M"), "mode": "live", "rows": rows}


# ---------- 市场天气（全市场涨跌家数） ----------
def mood_word(share: float) -> str:
    """上涨家数占比 → 一个 ≤3 字的词。"""
    for lim, word in ((80, "艳阳天"), (62, "晴"), (48, "多云"), (32, "阴"), (16, "偏冷")):
        if share >= lim:
            return word
    return "冰点"


def market_weather(day: dict | None = None) -> dict:
    """{"time","word","up","down"}：真数家数；数不了就用上证指数涨跌估一个占比（fallback，卡片 source=index）。"""
    day = day or load_day()
    date = day["date"]
    cached = _cache_get("breadth")
    if cached and cached.get("date") == date:
        up, down, src = cached["up"], cached["down"], "panda"
    else:
        up = down = 0
        src = "panda"
        try:
            from panda_client import login
            import panda_data
            login()
            df = panda_data.get_stock_daily(start_date=date, end_date=date)
            if "trade_status" in df.columns:
                df = df[df["trade_status"] == 0]
            up, down = int((df["close"] > df["pre_close"]).sum()), int((df["close"] < df["pre_close"]).sum())
            if up + down < 1000:
                raise ValueError(f"只数到 {up + down} 只")
            _cache_put("breadth", {"date": date, "up": up, "down": down})
        except BaseException:
            ix = index_state(day)["pct"]
            total = 5000
            share = max(3.0, min(97.0, 50 + ix * 15))   # 估计：指数 +1% ≈ 65% 上涨家数，只在拿不到涨跌家数时用
            up, down, src = round(total * share / 100), round(total * (100 - share) / 100), "index"
    share = up / ((up + down) or 1) * 100
    return {"time": "15:00", "word": mood_word(share), "up": up, "down": down, "source": src}


if __name__ == "__main__":
    d = load_day()
    print("source:", d["source"], "date:", d["date"], "warn:", d.get("warn"))
    print(json.dumps(watch_card(d), ensure_ascii=False))
    print(json.dumps(watch_card(d, "replay", 20), ensure_ascii=False))
    print(json.dumps(mover_card(d, 0, 30), ensure_ascii=False))
    print(json.dumps(market_weather(d), ensure_ascii=False))
