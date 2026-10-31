"""汇率：Frankfurter（欧洲央行 ECB 每个工作日发布的参考汇率，免费、不用 key）。

    python3 data/fx.py

注意：这是**日更的参考汇率**，不是实时报价，屏幕上要写「参考汇率」，不能当成交价（合规）。
接口：https://api.frankfurter.dev/v1/{latest | 起止日期}?base=USD&symbols=CNY,HKD,...
"""

from __future__ import annotations

import datetime
import json
import urllib.parse
import urllib.request

PAIRS = [("USD", "CNY"), ("HKD", "CNY"), ("EUR", "CNY"), ("JPY", "CNY")]
NAMES = {"USD": "美元", "HKD": "港币", "EUR": "欧元", "JPY": "日元", "CNY": "人民币"}


def _get(path: str, params: dict, timeout: float = 10) -> dict:
    url = f"https://api.frankfurter.dev/v1/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def get_rates(pairs=PAIRS) -> list[dict]:
    """每对返回：最新价、上一个工作日价、涨跌幅 %。JPY 按 100 日元报价（国内习惯）。"""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=10)   # 跨周末和假期，保证至少有两个工作日
    out = []
    for base, quote in pairs:
        data = _get(f"{start}..{end}", {"base": base, "symbols": quote})["rates"]
        days = sorted(data)
        if len(days) < 2:
            continue
        scale = 100 if base == "JPY" else 1
        last, prev = data[days[-1]][quote] * scale, data[days[-2]][quote] * scale
        out.append({
            "base": base, "quote": quote, "per": scale, "name": f"{scale if scale > 1 else ''}{NAMES[base]}/{NAMES[quote]}",
            "rate": round(last, 4), "prev": round(prev, 4), "pct": round((last / prev - 1) * 100, 2),
            "date": days[-1], "source": "ECB 参考汇率（日更）",
        })
    return out


if __name__ == "__main__":
    for r in get_rates():
        arrow = "▲" if r["pct"] >= 0 else "▼"
        print(f"{r['name']:10} {r['rate']:>8}  {arrow} {r['pct']:+.2f}%   {r['date']}  {r['source']}")
