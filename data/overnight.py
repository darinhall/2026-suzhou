"""隔夜外盘：纳斯达克综合指数、标普 500 上一个美股交易日的涨跌幅（PandaAI 美股指数日线，实测 2026-10-31 可用，最新到 10-30）。

    uv run --python 3.12 --with panda-data==1.0.5 python data/overnight.py

symbol 不带后缀：IXIC、SPX（带 .NB 会查不到）。拿不到时用上一次的缓存；缓存也没有就返回 None（卡片里不出现 overnight）。
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from watch import cache_get, cache_put   # noqa: E402

INDEXES = [("IXIC", "纳指"), ("SPX", "标普")]


def get_overnight() -> dict | None:
    """{"date":"20261030","items":[{"name":"纳指","pct":-0.8},…],"source":"panda|cache"}；没有就 None。"""
    try:
        import panda_data
        from panda_client import login

        login()
        items, date = [], ""
        for sym, name in INDEXES:
            df = panda_data.get_us_index_daily(symbol=sym, start_date=(datetime.date.today() - datetime.timedelta(days=45)).strftime("%Y%m%d"), end_date=datetime.date.today().strftime("%Y%m%d"))
            df = df.sort_values("date").tail(1)
            if not len(df):
                raise ValueError(f"{sym} 没有数据")
            r = df.iloc[0]
            items.append({"name": name, "pct": round((float(r["close"]) / float(r["pre_close"]) - 1) * 100, 2)})
            date = max(date, str(r["date"]))
        out = {"date": date, "items": items, "source": "panda"}
        cache_put("overnight", out)
        return out
    except BaseException:   # login() 缺账号会 SystemExit
        out = cache_get("overnight")
        if out:
            out["source"] = "cache"
        return out


if __name__ == "__main__":
    print(json.dumps(get_overnight(), ensure_ascii=False))
