"""给「寻找你的交易人格」导出真实行情：每只股票挑一段最有戏剧性的 40 个交易日（大涨 + 大跌）。

    uv run --python 3.12 --with panda-data==1.0.5 python data/export_game.py

输出 sim/game/data/scenarios.json，格式就是游戏 fromBars() 要的 {name, code, period, bars: [{date, close}]}。
价格用 close / pre_close 逐日连乘做了复权，分红除权不会被当成暴跌。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from panda_client import PandaClient, login   # noqa: E402

# 名字大家都认识的票，揭晓时才有"原来是它"的感觉
CANDIDATES = ["300750", "600519", "002594", "601318", "000858", "688981", "300059", "601127", "000333", "600036"]
WINDOW = 40
START = "20240101"
OUT = Path(__file__).resolve().parent.parent / "sim" / "game" / "data" / "scenarios.json"


def adjusted(df):
    """逐日涨跌（close / pre_close）连乘，再缩放到最后一天的真实收盘价。"""
    ratios = (df["close"] / df["pre_close"]).tolist()
    level, series = 1.0, []
    for r in ratios:
        level *= r
        series.append(level)
    scale = df["close"].iloc[-1] / series[-1]
    return [round(v * scale, 2) for v in series]


def best_window(dates, closes):
    """找一段窗口：窗口内最大涨幅（低点→之后高点）和最大跌幅（高点→之后低点）都大。"""
    best = None
    for i in range(0, len(closes) - WINDOW + 1):
        w = closes[i:i + WINDOW]
        run_up = max_drawdown = 0.0
        lo = hi = w[0]
        for p in w:
            lo, hi = min(lo, p), max(hi, p)
            run_up = max(run_up, p / lo - 1)
            max_drawdown = max(max_drawdown, 1 - p / hi)
        score = min(run_up, max_drawdown)   # 两边都要有，才有"追涨 / 抄底"的选择
        if best is None or score > best[0]:
            best = (score, i, run_up, max_drawdown)
    return best


def main():
    login()
    c = PandaClient()
    last = c.last_trade_date()
    scenarios = []
    for code in CANDIDATES:
        df = c.get_bars("a", [code], START, last)
        df = df[df["trade_status"] == 0] if "trade_status" in df.columns else df
        if len(df) < WINDOW:
            print(f"跳过 {code}：只有 {len(df)} 天")
            continue
        closes, dates = adjusted(df), df["date"].astype(str).tolist()
        score, i, up, down = best_window(dates, closes)
        bars = [{"date": d, "close": p} for d, p in zip(dates[i:i + WINDOW], closes[i:i + WINDOW])]
        name, sym = df["name"].iloc[-1], df["symbol"].iloc[-1]
        d0, d1 = bars[0]["date"], bars[-1]["date"]
        scenarios.append({
            "name": name, "code": sym,
            "period": f"{d0[:4]}.{d0[4:6]}.{d0[6:]}–{d1[:4]}.{d1[4:6]}.{d1[6:]} 真实行情（复权）",
            "score": round(score, 3), "run_up": round(up, 3), "drawdown": round(down, 3),
            "bars": bars,
        })
        print(f"{name:6} {sym}  {d0}–{d1}  涨 {up:+.0%}  跌 {-down:+.0%}")

    scenarios.sort(key=lambda s: -s["score"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": "PandaAI panda_data", "exported": last, "scenarios": scenarios},
                              ensure_ascii=False, indent=1))
    print(f"\n写入 {OUT}（{len(scenarios)} 段行情）")


if __name__ == "__main__":
    main()
