"""盘前简报 / 收盘小结：不用大模型，用规则把天气、指数、日程、自选股拼成三句话（brief 卡）。

    uv run --python 3.12 --with panda-data==1.0.5 python data/brief.py

每一句都很短（屏幕一行 ≈ 22 个汉字），都有来源：天气 → data/weather.py，指数和自选股 → data/watch.py，日程 → data/schedule.json。
某一路拿不到就换成下一个候选，不会编数据；三句凑不齐就少于三句。
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from watch import index_state, load_day, market_weather, stock_state, top_movers   # noqa: E402


def _sgn(p: float) -> str:
    return f"{p:+.1f}%"


def _fit(text: str, em: int = 24) -> str:
    """汉字算 1，其他算 0.6，超过 em 就截断加省略号。"""
    n = 0.0
    for i, ch in enumerate(text):
        n += 1 if ord(ch) > 255 else 0.6
        if n > em:
            return text[:i] + "…"
    return text


def indices_line(day: dict, only: str = "沪深创") -> str:
    short = {"上证指数": "沪", "深证成指": "深", "创业板指": "创"}
    parts = []
    for k, ix in enumerate(day["indices"]):
        pct = round((ix["closes"][-1] / ix["prev_close"] - 1) * 100, 1)
        name = short.get(ix["name"], ix["name"][:1])
        if name in only:
            parts.append(f"{name} {_sgn(pct)}")
    return " ".join(parts)


def morning_brief(weather: dict | None = None, event: dict | None = None, day: dict | None = None, breadth: dict | None = None) -> dict:
    """盘前简报：①天气建议 ②上一个交易日的大盘情绪 ③下一个日程（没有就是自选里最强的一只）。"""
    day = day or load_day()
    items = []
    if weather:
        from weather import advice
        nw = weather["now"]
        items.append(_fit(f"{nw['city']} {round(nw['temp'])}° {nw['text']}，{advice(nw, weather['today'], weather.get('tomorrow'))}"))
    breadth = breadth or market_weather(day)
    d = day["date"]
    items.append(_fit(f"昨收 {indices_line(day, '沪创')}，市场{breadth['word']}"))
    if event:
        items.append(_fit(f"{event['time']} {event['title']} · {event['where']}"))
    else:
        best, _ = top_movers(day)
        items.append(_fit(f"自选最强：{best['name']} {_sgn(best['pct'])}"))
    return {"title": "盘前简报", "items": items, "hint": "按头 = 发到飞书"}


def close_summary(day: dict | None = None, breadth: dict | None = None) -> dict:
    """收盘小结：三大指数、自选最强 / 最弱、市场天气。"""
    day = day or load_day()
    breadth = breadth or market_weather(day)
    best, worst = top_movers(day)
    share = round(breadth["up"] / ((breadth["up"] + breadth["down"]) or 1) * 100)
    items = [_fit(f"指数  {indices_line(day)}"),
             _fit(f"自选 {best['name']} {_sgn(best['pct'])} · {worst['name']} {_sgn(worst['pct'])}") if best["code"] != worst["code"]
             else _fit(f"自选 {best['name']} {_sgn(best['pct'])}"),
             _fit(f"市场{breadth['word']}，{share}% 的股票上涨")]
    d = day["date"]
    return {"title": f"收盘小结 · {d[4:6]}-{d[6:]}", "items": items, "hint": ""}


if __name__ == "__main__":
    from today import next_event
    from weather import get_weather
    print(json.dumps(morning_brief(get_weather(), next_event(datetime.datetime.now().replace(hour=8, minute=0))), ensure_ascii=False, indent=1))
    print(json.dumps(close_summary(), ensure_ascii=False, indent=1))
