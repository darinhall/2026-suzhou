"""区间涨跌：A 股 / 指数 / 港股最近 N 个交易日的起止收盘、涨跌幅、最高、最低（Python 算，大模型不心算）。

    period_return("399441.SZ", 5) → {"kind": "index", "name": "生物医药", "change_pct": …, …}

代码怎么分：.HK = 港股；在 PandaAI 指数目录里（2000 多个，带名字）= 指数；其他 = A 股，
A 股代码的数字前缀必须和后缀对上（6/9 → .SH，0/2/3 → .SZ，4/8 → .BJ），对不上直接报错，
**绝不自己换后缀**——000933.SH（800医卫指数）和 000933.SZ（另一只股票）是两个东西（11-01 实际踩过）。
返回结果都带 name，调用方核对是不是自己要的那个。
"""

from __future__ import annotations

import datetime as dt
import json
import time

_catalog: dict = {"names": {}, "at": 0.0}


def index_names() -> dict[str, str]:
    """PandaAI 指数目录：代码 → 名字（一天刷新一次）。"""
    if not _catalog["names"] or time.time() - _catalog["at"] > 86400:
        import panda_data
        from panda_client import login
        login()
        df = panda_data.get_index_detail_all()
        _catalog.update(names=dict(zip(df["symbol"].astype(str), df["name"].astype(str))), at=time.time())
    return _catalog["names"]


def find_index(keyword: str, limit: int = 10) -> list[dict]:
    """按名字找指数（行业 / 主题 / 宽基）。"""
    hits = [(s, n) for s, n in index_names().items() if keyword in n]
    hits.sort(key=lambda x: (len(x[1]), x[0]))   # 名字短的（更通用的）排前面
    return [{"symbol": s, "name": n} for s, n in hits[:limit]]


def stock_suffix_error(symbol: str) -> str | None:
    """A 股代码前缀和后缀对不上 → 错误说明；对得上 → None。"""
    code, _, suf = symbol.upper().partition(".")
    if not (len(code) == 6 and code.isdigit()):
        return f"{symbol} 不是 6 位数字代码"
    want = {"6": "SH", "9": "SH", "0": "SZ", "2": "SZ", "3": "SZ", "4": "BJ", "8": "BJ"}.get(code[0])
    if want and suf != want:
        return f"{symbol}：{code[0]} 开头的股票应该是 .{want}；如果你要的是指数，它不在指数目录里，用 find_index 按名字找。不要自己换后缀"
    return None


def kind_of(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(".HK"):
        return "hk"
    if s in index_names():
        return "index"
    return "stock"


def period_return(symbol: str, days: int) -> dict:
    import pandas as pd
    import panda_data
    from panda_client import PandaClient, login

    symbol = symbol.strip().upper()
    days = max(1, min(int(days), 250))
    login()
    last = PandaClient().last_trade_date()
    start = (dt.datetime.strptime(last, "%Y%m%d") - dt.timedelta(days=int(days * 1.6) + 10)).strftime("%Y%m%d")
    kind = kind_of(symbol)
    name = ""
    if kind == "hk":   # 港股：SDK 没封装，走 MCP
        from brain.panda_mcp import Client
        d = json.loads(Client().open().call("call_pandadata", {"method": "get_hk_daily", "params": {
            "symbol": symbol, "start_date": start, "end_date": last, "fields": ["date", "high", "low", "close", "name"]}})["content"][0]["text"])
        res = d.get("result") or {}
        df = pd.DataFrame(res.get("rows") or [], columns=res.get("columns") or [])
    elif kind == "index":
        name = index_names()[symbol]
        df = panda_data.get_index_daily(symbol=[symbol], start_date=start, end_date=last)
    else:
        err = stock_suffix_error(symbol)
        if err:
            return {"error": err}
        df = panda_data.get_stock_daily(symbol=[symbol], start_date=start, end_date=last)
    if df is None or not len(df):
        return {"error": f"{symbol} 没有数据（{kind}）"}
    df = df.sort_values("date").tail(days + 1)
    first, end = df.iloc[0], df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else first
    return {"symbol": symbol, "kind": {"hk": "港股", "index": "指数", "stock": "A股"}[kind],
            "name": name or str(end.get("name", "")), "days": len(df) - 1,
            "from_date": str(first["date"]), "from_close": round(float(first["close"]), 2),
            "to_date": str(end["date"]), "to_close": round(float(end["close"]), 2),
            "change_pct": round((float(end["close"]) / float(first["close"]) - 1) * 100, 2),
            "last_day_pct": round((float(end["close"]) / float(prev["close"]) - 1) * 100, 2),
            "high": round(float(df["high"].max()), 2), "low": round(float(df["low"].min()), 2)}
