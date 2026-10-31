"""自选盯盘的数据：最近一个交易日的 5 分钟行情（回放用）、四个指数、市场天气（全市场涨跌家数），拼成屏幕的 watch / mkt / weather 卡（"C 专业"密度，见 数据清单.md）。

    uv run --python 3.12 --with panda-data==1.0.5 python data/watch.py          # 打印 watch 卡、一张 mkt 卡、市场天气

数据来源 PandaAI（实测 2026-10-31）：
- 股票日线：开高低收、昨收、成交量（股）、成交额（元）、涨停价、跌停价；近 20 日区间、近 5 日均量（量比）都是用它算的。
- 股票 5 分钟线：每天 48 根（09:35…11:30、13:05…15:00），含 high / low / volume / amount。免费账号可用。
- 指数日线 + 指数 1 分钟线：上证 / 深证 / 创业板 / 沪深 300，按 5 分钟的时刻抽样。
- 全市场日线（不传 symbol）：一次 2–3 秒拿到 5000+ 只，所以涨跌家数、涨停 / 跌停家数都是真的数出来的。
- 盘中实时（get_stock_rt_daily / rt_min）：休市时返回空，免费号盘中是否可用没验证过，所以 live 只做尽力而为。

降级顺序：PandaAI → data/cache/*.json（上一次成功的数据）→ 示例数据（mode:"sample"，屏幕上要写"示例数据"）。
分钟线拿不到时，用当天日线的 开 / 高 / 低 / 收 插值出 48 个点（day["interp"] 里记下是哪几只；成交量 / 额按等分摊）。
卡片里**拿不到的字段就不出现**，不会用假值补。
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
WATCHLIST = [("300750", "宁德时代"), ("688981", "中芯国际"), ("600519", "贵州茅台"), ("002594", "比亚迪"), ("600036", "招商银行")]   # 默认自选；profile.watch.codes 可以换
MAX_STOCKS = 8   # 一个自选最多 8 只（watch 列表一页 MAX_ROWS = 5 行，多的翻页）
INDICES = [("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指"), ("000300", "沪深300")]
MAX_ROWS = 5
CACHE_VERSION = 2   # 数据结构变了就加一，旧缓存自动作废


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


TIMES = _make_times()   # 5 分钟线的 48 个时刻：09:35…11:30、13:05…15:00
N = len(TIMES)


def resolve(codes) -> list[tuple[str, str]]:
    """代码列表 → [(代码, 名称)]：名称先查 data/names.py，查不到就用代码当名字（取到行情后会换成行情里的名字）。None = 默认自选。"""
    if not codes:
        return list(WATCHLIST)
    import names
    default = dict(WATCHLIST)
    out = []
    for c in list(codes)[:MAX_STOCKS]:
        c = str(c)
        out.append((c, default.get(c) or names.lookup(c) or c))
    return out


def _key(wl: list[tuple[str, str]]) -> str:
    return "-".join(c for c, _ in wl)


# ---------- 缓存 ----------
def cache_put(name: str, obj: dict) -> None:
    try:
        CACHE.mkdir(exist_ok=True)
        (CACHE / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False))
    except OSError:
        pass


def cache_get(name: str) -> dict | None:
    try:
        return json.loads((CACHE / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


# ---------- 插值 / 示例 ----------
def interpolate_day(o: float, h: float, lo: float, c: float, n: int = N) -> list[float]:
    """分钟线拿不到时，用日线 开高低收 插出 n 个点：先到低点再到高点（收阳），或先高后低（收阴）。"""
    path = [o, lo, h, c] if c >= o else [o, h, lo, c]
    out = []
    for i in range(n):
        x = (i + 1) / n * (len(path) - 1)
        k = min(int(x), len(path) - 2)
        out.append(round(path[k] + (path[k + 1] - path[k]) * (x - k), 3))
    return out


def sample_day(wl: list[tuple[str, str]] | None = None) -> dict:
    """完全没有数据时的示例：固定种子的随机游走。屏幕上标"示例数据"。"""
    rnd = random.Random(1031)
    d = datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)

    def walk(prev: float, drift: float, vol: float) -> list[float]:
        v, out = prev, []
        for _ in range(N):
            v *= 1 + drift / N + rnd.gauss(0, vol)
            out.append(round(v, 2))
        return out

    wl = wl or list(WATCHLIST)
    base = {"300750": (210.0, 0.035), "688981": (100.1, 0.045), "600519": (1450.0, -0.012), "002594": (255.0, -0.03), "600036": (43.3, 0.01)}
    stocks = []
    for j, (c, n) in enumerate(wl):
        p, dr = base.get(c) or (round(20 + rnd.random() * 80, 2), round(rnd.uniform(-0.04, 0.04), 3))
        closes = walk(p, dr, 0.0018)
        hi, lo = max(closes + [p]), min(closes + [p])
        stocks.append({"code": c, "name": n, "prev_close": p, "open": round(p * 1.002, 2), "closes": closes,
                       "highs": [round(v * 1.001, 2) for v in closes], "lows": [round(v * 0.999, 2) for v in closes],
                       "amounts": [2e8] * N, "volumes": [1e6] * N, "daily_high": hi, "daily_low": lo,
                       "daily_volume": 1e6 * N, "daily_amount": 2e8 * N, "vol5": 1e6 * N * 0.9,
                       "limit_up": round(p * 1.1, 2), "limit_down": round(p * 0.9, 2),
                       "range20": {"lo": round(p * 0.93, 2), "hi": round(p * 1.07, 2)}, "interp": False, "daily": walk(p, 0, 0.01)[:24]})
    indices = [{"code": c, "name": n, "prev_close": p, "closes": walk(p, dr, 0.0004), "amount": 5000e8}
               for (c, n), p, dr in zip(INDICES, (3600.0, 11800.0, 2500.0, 4100.0), (0.004, -0.002, -0.012, 0.002))]
    return {"v": CACHE_VERSION, "date": d.strftime("%Y%m%d"), "source": "sample", "stocks": stocks, "indices": indices, "interp": []}


# ---------- 取数 ----------
def _ffill(series: dict, prev: float) -> list[float]:
    """按 TIMES 取值，缺的用前一个补。"""
    out, last = [], prev
    for t in TIMES:
        last = series.get(t, last)
        out.append(round(float(last), 3))
    return out


def _hhmm(minute) -> str:
    s = str(minute).zfill(6)
    return f"{s[:2]}:{s[2:4]}"


def _fetch_day(wl: list[tuple[str, str]]) -> dict:
    from export_game import adjusted
    from panda_client import PandaClient, login

    login()
    c = PandaClient()
    last = c.last_trade_date()
    start = (datetime.datetime.strptime(last, "%Y%m%d") - datetime.timedelta(days=60)).strftime("%Y%m%d")
    codes = [c_ for c_, _ in wl]
    daily = c.get_bars("a", codes, start, last)
    if "trade_status" in daily.columns:
        daily = daily[daily["trade_status"] == 0]
    try:
        mins = c.get_minute("a", codes, last, last, "5m")
    except Exception:
        mins = None

    stocks, interp = [], []
    for code, name in wl:
        df = daily[daily["symbol"].str.startswith(code)]
        if not len(df):
            raise ValueError(f"{code} 没有日线")
        row = df.iloc[-1]
        prev = float(row["pre_close"])
        bars = {}
        if mins is not None and len(mins):
            m = mins[mins["symbol"].str.startswith(code)]
            bars = {_hhmm(r["minute"]): r for _, r in m.iterrows()}
        s = {"code": code, "name": str(row["name"]) if "name" in row else name, "prev_close": prev,
             "open": float(row["open"]), "daily_high": float(row["high"]), "daily_low": float(row["low"]),
             "daily_volume": float(row["volume"]), "daily_amount": float(row["amount"]),
             "limit_up": float(row["limit_up"]) if "limit_up" in row else None,
             "limit_down": float(row["limit_down"]) if "limit_down" in row else None,
             "vol5": float(df["volume"].iloc[-6:-1].mean()) if len(df) > 5 else None,
             "range20": {"lo": float(df["low"].iloc[-20:].min()), "hi": float(df["high"].iloc[-20:].max())},
             "daily": adjusted(df)[-24:]}
        if len(bars) >= 40:
            def ff(col, default):
                out, lastv = [], default
                for t in TIMES:
                    if t in bars:
                        lastv = float(bars[t][col])
                    out.append(lastv)
                return out
            s["closes"] = _ffill({t: float(r["close"]) for t, r in bars.items()}, prev)
            s["highs"], s["lows"] = ff("high", prev), ff("low", prev)
            s["volumes"] = [float(bars[t]["volume"]) if t in bars else 0.0 for t in TIMES]
            s["amounts"] = [float(bars[t]["amount"]) if t in bars else 0.0 for t in TIMES]
            s["interp"] = False
        else:   # 分钟线不够：用日线插值，成交量 / 额等分摊
            s["closes"] = interpolate_day(s["open"], s["daily_high"], s["daily_low"], float(row["close"]))
            s["highs"], s["lows"] = list(s["closes"]), list(s["closes"])
            s["volumes"] = [s["daily_volume"] / N] * N
            s["amounts"] = [s["daily_amount"] / N] * N
            s["interp"] = True
            interp.append(code)
        stocks.append(s)

    indices = []
    idx_daily = c.get_bars("index", [i for i, _ in INDICES], start, last)
    try:
        idx_min = c.get_minute("index", [i for i, _ in INDICES], last, last)
    except Exception:
        idx_min = None
    for code, name in INDICES:
        df = idx_daily[idx_daily["symbol"].str.startswith(code)]
        if not len(df):
            continue   # 某个指数没有数据就少一格，不编
        row = df.iloc[-1]
        prev = float(row["pre_close"])
        series = {}
        if idx_min is not None and len(idx_min):
            m = idx_min[idx_min["symbol"].str.startswith(code)]
            series = {_hhmm(r["minute"]): float(r["close"]) for _, r in m.iterrows()}
        closes = _ffill(series, prev) if len(series) >= 100 else interpolate_day(float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
        indices.append({"code": code, "name": name, "prev_close": prev, "closes": closes, "amount": float(row["amount"])})
    if not indices:
        raise ValueError("指数日线为空")
    return {"v": CACHE_VERSION, "date": last, "source": "panda", "stocks": stocks, "indices": indices, "interp": interp}


_mem: dict = {}


def load_day(max_age: float = 600, codes=None) -> dict:
    """最近一个交易日的数据（codes = 自选代码列表，None = 默认自选）。内存缓存 10 分钟；PandaAI 失败用磁盘缓存；再不行用示例。
    返回的 dict 里 "source" 是 panda / cache / sample，"warn" 是要记日志的原因（没有就是 None）。"""
    wl = resolve(codes)
    key = _key(wl)
    hit = _mem.get(key)
    if hit and time.time() - hit["at"] < max_age:
        return hit["day"]
    cname = "day" if key == _key(WATCHLIST) else "day_" + key
    warn = None
    try:
        day = _fetch_day(wl)
        cache_put(cname, day)
    except BaseException as e:   # login() 缺账号会 SystemExit，也要兜住
        warn = f"{type(e).__name__}: {e}"[:200]
        day = cache_get(cname)
        if day and day.get("v") == CACHE_VERSION and [x["code"] for x in day["stocks"]] == [c for c, _ in wl]:   # 缓存的自选要和现在的一致
            day["source"] = "cache"
        else:
            day = sample_day(wl)
    day["warn"] = warn or ("分钟线缺失，用日线插值：" + ",".join(day["interp"]) if day.get("interp") else None)
    _mem[key] = {"day": day, "at": time.time()}
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
    """第 k 只自选股，到第 i 根 K 线（None = 收盘）为止的状态（所有数值都是"到这一刻为止"）。
    字段拿不到就没有这个 key：pct price prev_close open high low amount(亿) amp(%) vol_ratio volume(万手) limit_up limit_down range20 spark。"""
    s = day["stocks"][k]
    full = i is None or i >= N - 1
    i = N - 1 if i is None else i
    prev, price = s["prev_close"], s["closes"][i]
    out = {"name": s["name"], "code": s["code"], "pct": _pct(price, prev), "price": round(price, 2), "prev_close": round(prev, 2)}
    if s.get("open") is not None:
        out["open"] = round(s["open"], 2)
    hi = s.get("daily_high") if full and s.get("daily_high") is not None else max(s.get("highs", s["closes"])[:i + 1] + [s.get("open", prev)])
    lo = s.get("daily_low") if full and s.get("daily_low") is not None else min(s.get("lows", s["closes"])[:i + 1] + [s.get("open", prev)])
    out["high"], out["low"] = round(hi, 2), round(lo, 2)
    out["amp"] = round((hi - lo) / prev * 100, 2) if prev else 0.0
    amt = s["daily_amount"] if full and s.get("daily_amount") else sum(s.get("amounts", [0])[:i + 1])
    vol = s["daily_volume"] if full and s.get("daily_volume") else sum(s.get("volumes", [0])[:i + 1])
    if amt:
        out["amount"] = round(amt / 1e8, 2)
    if vol:
        out["volume"] = round(vol / 1e6, 1)   # 股 → 万手
    if s.get("vol5"):   # 量比：成交量 / 近 5 日均量（盘中按已过去的时间折算）
        out["vol_ratio"] = round(vol / (s["vol5"] * (1 if full else (i + 1) / N)), 1) if vol else None
        if out["vol_ratio"] is None:
            out.pop("vol_ratio")
    for key in ("limit_up", "limit_down"):
        if s.get(key) is not None:
            out[key] = round(s[key], 2)
    if s.get("range20"):
        out["range20"] = {"lo": round(s["range20"]["lo"], 2), "hi": round(s["range20"]["hi"], 2)}
    out["_series"] = [prev] + s["closes"][:i + 1]
    return out


def indices_state(day: dict, i: int | None = None, with_amount: bool = False) -> list[dict]:
    i = N - 1 if i is None else i
    out = []
    for ix in day["indices"][:4]:
        d = {"name": ix["name"], "value": round(ix["closes"][i], 2), "pct": _pct(ix["closes"][i], ix["prev_close"])}
        if with_amount and ix.get("amount"):
            d["amount"] = round(ix["amount"] / 1e8)   # 亿
        out.append(d)
    return out


def index_state(day: dict, i: int | None = None) -> dict:
    ix = indices_state(day, i)[0]
    return {"name": ix["name"], "pct": ix["pct"]}


def watch_card(day: dict, mode: str = "close", i: int | None = None, alert_codes: tuple = (), start: int = 0) -> dict:
    """watch 卡（v2）：
    {title, asof, mode:close|replay|live|sample, index:{name,pct}（旧字段）,
     indices:[{name,value,pct[,amount(亿，仅收盘)]}]≤4, avg_pct,
     rows:[{name,code,pct,price,open,high,low,prev_close,amount,amp,vol_ratio,spark≤24[,alert]}]≤5（start = 从第几只开始，翻页用）, alert?}"""
    at = None if mode == "close" else i
    rows = []
    for k in range(start, min(start + MAX_ROWS, len(day["stocks"]))):
        r = stock_state(day, k, at)
        series = r.pop("_series")
        for key in ("volume", "limit_up", "limit_down", "range20"):   # 这些只给单股 mkt 卡
            r.pop(key, None)
        r["spark"] = _down(series, 24)
        if r["code"] in alert_codes:
            r["alert"] = True
        rows.append(r)
    card = {"title": "自选", "asof": asof_text(day, i, mode), "mode": card_mode(day, mode),
            "index": index_state(day, at), "indices": indices_state(day, at, with_amount=mode == "close"),
            "avg_pct": round(sum(r["pct"] for r in rows) / len(rows), 2) if rows else 0.0, "rows": rows}
    if alert_codes:
        card["alert"] = True
    return card


def mover_card(day: dict, k: int, i: int | None, mode: str = "replay", alert: bool = True) -> dict:
    """mkt 卡（v2）：原来的 name code pct vol_ratio hint legal，加上
    price prev_close open high low volume(万手) amount(亿) amp limit_up limit_down range20:{lo,hi} spark≤48 asof mode alert。"""
    s = stock_state(day, k, i)
    series = s.pop("_series")
    s["spark"] = _down(series, 48)
    return {**s, "asof": asof_text(day, i, mode), "mode": card_mode(day, mode), "alert": alert,
            "hint": "按头 = 记入模拟单",
            "legal": f"{asof_text(day, i, mode)} · {'回放 · ' if mode == 'replay' else ''}不构成投资建议"}


def top_movers(day: dict, i: int | None = None) -> tuple[dict, dict]:
    """自选里涨得最多 / 跌得最多的两只（可能是同一只）。"""
    sts = [stock_state(day, k, i) for k in range(min(MAX_ROWS, len(day["stocks"])))]
    return max(sts, key=lambda s: s["pct"]), min(sts, key=lambda s: s["pct"])


def live_card(day: dict) -> dict:
    """盘中实时（尽力而为）：用 PandaAI 的当日快照拼 watch 卡，mode:"live"，没有 index / indices 字段。
    休市时快照是空的、免费号盘中是否有权限没验证过：取不到就抛错，调用方退回回放。"""
    from panda_client import PandaClient, login

    login()
    df = PandaClient().get_snapshot([s["code"] for s in day["stocks"][:MAX_ROWS]])
    if df is None or not len(df):
        raise RuntimeError("盘中快照为空（休市，或免费号没有盘中权限）")
    rows = []
    for s in day["stocks"][:MAX_ROWS]:
        r = df[df["symbol"].str.startswith(s["code"])]
        if not len(r):
            raise RuntimeError(f"快照里没有 {s['code']}")
        r = r.iloc[-1]
        price = float(r["close"])
        prev = float(r["pre_close"]) if "pre_close" in r and r["pre_close"] else s["prev_close"]
        row = {"name": s["name"], "code": s["code"], "pct": _pct(price, prev), "price": round(price, 2), "prev_close": round(prev, 2),
               "spark": _down(s.get("daily") or s["closes"], 24)}
        for k_ in ("open", "high", "low"):
            if k_ in r and r[k_]:
                row[k_] = round(float(r[k_]), 2)
        rows.append(row)
    return {"title": "自选", "asof": time.strftime("%H:%M"), "mode": "live", "rows": rows,
            "avg_pct": round(sum(r["pct"] for r in rows) / len(rows), 2)}


# ---------- 市场天气（全市场涨跌家数） ----------
def mood_word(share: float) -> str:
    """上涨家数占比 → 一个 ≤3 字的词。"""
    for lim, word in ((80, "艳阳天"), (62, "晴"), (48, "多云"), (32, "阴"), (16, "偏冷")):
        if share >= lim:
            return word
    return "冰点"


def market_weather(day: dict | None = None) -> dict:
    """{"time","word","up","down","flat","limit_up_n","limit_down_n","source"}：真数家数 / 涨停跌停家数；
    数不了就用上证指数涨跌估一个占比（source=index，只有 up/down 是估的，没有 flat / 涨停跌停）。"""
    day = day or load_day()
    date = day["date"]
    cached = cache_get("breadth")
    if cached and cached.get("date") == date and "limit_up_n" in cached:
        up, down, flat, lu, ld, src = cached["up"], cached["down"], cached["flat"], cached["limit_up_n"], cached["limit_down_n"], "panda"
    else:
        flat = lu = ld = None
        src = "panda"
        try:
            from panda_client import login
            import panda_data
            login()
            df = panda_data.get_stock_daily(start_date=date, end_date=date)
            if "trade_status" in df.columns:
                df = df[df["trade_status"] == 0]
            up, down = int((df["close"] > df["pre_close"]).sum()), int((df["close"] < df["pre_close"]).sum())
            flat = int((df["close"] == df["pre_close"]).sum())
            if up + down < 1000:
                raise ValueError(f"只数到 {up + down} 只")
            lu = int(((df["close"] >= df["limit_up"] - 0.005) & (df["limit_up"] > 0)).sum()) if "limit_up" in df.columns else None
            ld = int(((df["close"] <= df["limit_down"] + 0.005) & (df["limit_down"] > 0)).sum()) if "limit_down" in df.columns else None
            cache_put("breadth", {"date": date, "up": up, "down": down, "flat": flat, "limit_up_n": lu, "limit_down_n": ld})
        except BaseException:
            ix = index_state(day)["pct"]
            share = max(3.0, min(97.0, 50 + ix * 15))   # 估计：指数 +1% ≈ 65% 上涨家数，只在拿不到涨跌家数时用
            up, down, src = round(5000 * share / 100), round(5000 * (100 - share) / 100), "index"
            flat = lu = ld = None
    share = up / ((up + down) or 1) * 100
    out = {"time": "15:00", "word": mood_word(share), "up": up, "down": down, "source": src}
    for k_, v in (("flat", flat), ("limit_up_n", lu), ("limit_down_n", ld)):
        if v is not None:
            out[k_] = v
    return out


if __name__ == "__main__":
    d = load_day()
    print("source:", d["source"], "date:", d["date"], "warn:", d.get("warn"))
    print(json.dumps(watch_card(d), ensure_ascii=False))
    print(json.dumps(watch_card(d, "replay", 20), ensure_ascii=False)[:600])
    print(json.dumps(mover_card(d, 0, 30), ensure_ascii=False))
    print(json.dumps(market_weather(d), ensure_ascii=False))
