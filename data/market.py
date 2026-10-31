"""行情卡：一只 A 股最近一个交易日的涨跌、量比、走势，拼成屏幕 mkt 这一屏的 card（PandaAI 日线）。

    uv run --python 3.12 --with panda-data==1.0.5 python data/market.py [代码]     # 默认宁德时代 300750

免费账号拿不到盘中实时行情（会员权益里「数据问答·实时行情」未包含），所以这里是**最近一个交易日收盘**，
屏幕上的免责行写成「10-30 收盘 · 不构成投资建议」，不会冒充实时。
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def get_card(code: str = "300750") -> dict:
    from export_game import adjusted           # 复权：按 close / pre_close 逐日连乘
    from panda_client import PandaClient, login   # 没装 panda_data 会 ImportError

    login()
    c = PandaClient()
    last = c.last_trade_date()
    start = (datetime.datetime.strptime(last, "%Y%m%d") - datetime.timedelta(days=60)).strftime("%Y%m%d")
    df = c.get_bars("a", [code], start, last)
    df = df[df["trade_status"] == 0] if "trade_status" in df.columns else df
    if len(df) < 7:
        raise ValueError(f"{code} 只有 {len(df)} 天数据")
    row = df.iloc[-1]
    prev5 = df["volume"].iloc[-6:-1].mean()
    day = str(row["date"])
    return {
        "name": row["name"], "code": row["symbol"],
        "pct": round((row["close"] / row["pre_close"] - 1) * 100, 2),
        "vol_ratio": round(row["volume"] / prev5, 1) if prev5 else None,
        "spark": adjusted(df)[-15:],
        "hint": "按头 = 记入模拟单",
        "legal": f"{day[4:6]}-{day[6:]} 收盘 · 不构成投资建议",
    }


if __name__ == "__main__":
    print(json.dumps(get_card(sys.argv[1] if len(sys.argv) > 1 else "300750"), ensure_ascii=False))
