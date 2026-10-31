"""问答：一句话（打字 / 语音识别结果）→ 屏幕卡片 + 要说的话 + 动作。同步函数，中枢放在线程里跑（要联网取 PandaAI）。

    answer(intent, watch_codes) → dict | None（None = 不是对机器人说的话，什么都不做）

原则（decisions.md §2）：卡片和这句话里的每个数字都来自 PandaAI 数据（data/watch.py 算好的），
大模型只在规则认不出的时候兜底闲聊，不说数字、不给买卖建议。
卡片先复用板子已经会画的两种：mkt（单股整屏行情）和 msg（标题 + 一段话）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))

from brain.router import Intent  # noqa: E402

LEGAL = "不构成投资建议"


def _ud(p: float) -> str:
    return "涨" if p >= 0 else "跌"


def _pct(p: float) -> str:
    return f"{abs(p):.2f}%"


def _day(codes):
    from watch import load_day
    return load_day(600, list(codes))


def _asof(day) -> str:
    from watch import asof_text
    return asof_text(day, None, "close")


def _spoken(day) -> str:
    """念出来的日期：「10月30日收盘」（「10-30」会被念成「十减三十」）。"""
    if day["source"] == "sample":
        return "示例数据里"
    d = day["date"]
    return f"{int(d[4:6])}月{int(d[6:])}日收盘"


def _msg(title: str, body: str, hint: str = "", meta: str = "") -> dict:
    card = {"title": title, "body": body}
    if hint:
        card["hint"] = hint
    if meta:
        card["meta"] = meta
    return {"state": "msg", "card": card}


def _reply(intent: Intent, say: str, face: dict | None, gesture: str | None = None, times: int = 1, action: str | None = None) -> dict:
    return {"intent": intent.kind, "text": intent.text, "codes": intent.codes, "say": say, "face": face,
            "gesture": {"name": gesture, "times": times} if gesture else None, "action": action}


def _quote(intent: Intent) -> dict:
    from watch import mover_card, stock_state
    day = _day(intent.codes[:1])
    s = stock_state(day, 0, None)
    card = mover_card(day, 0, None, "close", alert=False)
    card["hint"] = "说“行情异动模拟”看看我怎么提醒你"
    bits = [f"{s['name']}{_spoken(day)}报 {s['price']:.2f} 元，{_ud(s['pct'])} {_pct(s['pct'])}"]
    if s.get("vol_ratio"):
        bits.append(f"量比 {s['vol_ratio']:.1f}")
    if intent.kind == "yesno":
        head = "涨了。" if s["pct"] > 0 else "跌了。" if s["pct"] < 0 else "平盘。"
        return _reply(intent, head + "，".join(bits) + "。", {"state": "mkt", "card": card},
                      "nod" if s["pct"] > 0 else "shake", 2)
    return _reply(intent, "，".join(bits) + "。", {"state": "mkt", "card": card}, "nod", 1)


def _compare(intent: Intent) -> dict:
    from watch import stock_state
    day = _day(intent.codes[:3])
    sts = [stock_state(day, k, None) for k in range(len(day["stocks"]))]
    best = max(sts, key=lambda s: s["pct"])
    body = "  /  ".join(f"{s['name']} {'+' if s['pct'] >= 0 else '-'}{_pct(s['pct'])}" for s in sts)
    say = "，".join(f"{s['name']}{_ud(s['pct'])} {_pct(s['pct'])}" for s in sts) + f"。{best['name']}更强。"
    return _reply(intent, say, _msg(f"对比 · {_asof(day)}", body, meta=f"PandaAI · {LEGAL}"))


def _overview(intent: Intent, watch_codes) -> dict:
    from watch import indices_state
    day = _day(watch_codes)
    ixs = indices_state(day)
    body = "，".join(f"{x['name']} {'+' if x['pct'] >= 0 else '-'}{_pct(x['pct'])}" for x in ixs)
    up = sum(1 for x in ixs if x["pct"] >= 0)
    mood = "普涨" if up == len(ixs) else "普跌" if up == 0 else "涨跌互现"
    say = f"{_spoken(day)}，大盘{mood}：" + "，".join(f"{x['name']}{_ud(x['pct'])} {_pct(x['pct'])}" for x in ixs[:3]) + "。"
    return _reply(intent, say, _msg(f"大盘 · {_asof(day)}", body, meta=f"PandaAI · {LEGAL}"))


def _sector(intent: Intent) -> dict:
    """行业指数：最新一天涨跌 + 区间涨跌（默认最近 5 个交易日）。数字都是 brain/series.py 用 PandaAI 日线算的。"""
    from brain import series
    alias, code, _ = intent.sector
    days = intent.period_days if intent.period_days > 1 else 5
    r = series.period_return(code, days)
    if "error" in r:
        return _reply(intent, f"{alias}的数据暂时没取到。", _msg(alias, f"{r['error']}"), None)
    d = r["to_date"]
    when = f"{int(d[4:6])}月{int(d[6:])}日"
    iname = r["name"] if r["name"].endswith("指数") else r["name"] + "指数"
    say = (f"{alias}看{iname}：{when}收在 {r['to_close']:.2f}，{_ud(r['last_day_pct'])} {_pct(r['last_day_pct'])}；"
           f"最近 {r['days']} 个交易日{_ud(r['change_pct'])} {_pct(r['change_pct'])}。")
    body = (f"{when} 收 {r['to_close']:.2f}，{'+' if r['last_day_pct'] >= 0 else '-'}{_pct(r['last_day_pct'])}；"
            f"近 {r['days']} 日 {'+' if r['change_pct'] >= 0 else '-'}{_pct(r['change_pct'])}，区间 {r['low']:.2f}–{r['high']:.2f}")
    return _reply(intent, say, _msg(f"{alias} · {r['name']}", body, meta=f"PandaAI · {code} · {LEGAL}"))


def sector_movers(index_code: str) -> dict:
    """行业指数成分股在最近一个交易日的涨跌，从高到低。成分来自 PandaAI get_index_weights，行情来自 get_stock_daily。"""
    import panda_data
    from panda_client import login
    login()
    last = _last_trade_date()
    w = panda_data.get_index_weights(index_symbol=index_code, start_date=last, end_date=last)
    if w is None or not len(w):   # 有的指数权重不是每天都有：取最近一期
        import datetime as dt
        start = (dt.datetime.strptime(last, "%Y%m%d") - dt.timedelta(days=40)).strftime("%Y%m%d")
        w = panda_data.get_index_weights(index_symbol=index_code, start_date=start, end_date=last)
        w = w[w["date"] == w["date"].max()] if w is not None and len(w) else w
    if w is None or not len(w):
        return {"error": f"{index_code} 没有成分股数据"}
    syms = sorted(set(w["stock_symbol"].astype(str)))
    df = panda_data.get_stock_daily(symbol=syms, start_date=last, end_date=last)
    df = df[(df["pre_close"] > 0) & (df["trade_status"] == 0)] if "trade_status" in df.columns else df[df["pre_close"] > 0]
    df = df.assign(pct=(df["close"] / df["pre_close"] - 1) * 100).sort_values("pct", ascending=False)
    rows = [{"name": str(r["name"]), "code": str(r["symbol"])[:6], "pct": round(float(r["pct"]), 2)} for _, r in df.iterrows()]
    return {"date": last, "n": len(syms), "rows": rows, "up": sum(1 for r in rows if r["pct"] > 0)}


def _sector_top(intent: Intent, refuse: bool = False) -> dict:
    alias, code, _ = intent.sector
    m = sector_movers(code)
    if "error" in m or not m["rows"]:
        say = f"我不推荐个股。{alias}成分股的数据暂时没取到。" if refuse else f"{alias}成分股的数据暂时没取到。"
        return _reply(intent, say, _msg(alias, m.get("error", "没有数据")), "shake" if refuse else None, 2 if refuse else 1)
    d = m["date"]
    when = f"{int(d[4:6])}月{int(d[6:])}日"
    top = m["rows"][:3]
    tops = "、".join(f"{r['name']}{_ud(r['pct'])} {_pct(r['pct'])}" for r in top)
    facts = f"{alias}指数 {m['n']} 只成分股，{when}有 {m['up']} 只上涨，涨得最多的是{tops}。"
    body = f"{when} {m['up']}/{m['n']} 只上涨。领涨：" + "，".join(f"{r['name']} {'+' if r['pct'] >= 0 else '-'}{_pct(r['pct'])}" for r in top)
    if refuse:
        return _reply(intent, "我不推荐个股，只讲数据。" + facts, _msg(f"不做推荐 · {alias}", body, hint="只是数据，不是买卖建议", meta=f"PandaAI · {code} 成分股 · {LEGAL}"),
                      "shake", 2)
    return _reply(intent, facts, _msg(f"{alias} · 成分股", body, meta=f"PandaAI · {code} 成分股 · {LEGAL}"))


def _watchlist(intent: Intent, watch_codes, refuse: bool = False) -> dict:
    from watch import top_movers
    day = _day(watch_codes)
    hi, lo = top_movers(day)
    facts = f"你的自选里，{_spoken(day)}最强的是{hi['name']}，{_ud(hi['pct'])} {_pct(hi['pct'])}；最弱的是{lo['name']}，{_ud(lo['pct'])} {_pct(lo['pct'])}。"
    if refuse:
        say = f"我不推荐股票。不过你的自选里，{hi['name']}最强，{_ud(hi['pct'])} {_pct(hi['pct'])}。"
        return _reply(intent, say, _msg("我不做买卖建议", facts, hint="可以问我：帮我看看某只股票", meta=f"PandaAI · {LEGAL}"), "shake", 2)
    return _reply(intent, facts, _msg(f"自选 · {_asof(day)}", facts, meta=f"PandaAI · {LEGAL}"), "nod", 1)


_last = {"date": "未知", "at": 0.0}


def _last_trade_date() -> str:
    """最近交易日：10 分钟缓存（每个问题都去问一次要多花 1–2 秒）。"""
    import time
    if time.time() - _last["at"] > 600:
        try:
            from panda_client import PandaClient, login
            login()
            _last.update(date=PandaClient().last_trade_date() or "未知", at=time.time())
        except BaseException:
            pass
    return _last["date"]


def _agent(intent: Intent, log=print) -> dict | None:
    """规则答不了的：大模型 + PandaAI MCP 工具（brain/agent.py）。不是对我说的 → None。"""
    from brain import agent
    d = agent.answer(intent.text, _last_trade_date(), log=log)
    if not d or not d.get("for_me") or not d.get("say"):
        return None
    say = d["say"]
    return _reply(intent, say, _msg(d.get("title") or "PandaAI 数据", say, meta=f"PandaAI 数据 · {LEGAL}"))


def answer(intent: Intent, watch_codes, log=print) -> dict | None:
    k = intent.kind
    if k in ("quote", "yesno") and intent.period_days > 1:   # 「最近一周 / 一个月」：要日线区间，交给 agent（period_return）
        return _agent(intent, log)
    if k in ("quote", "yesno"):
        return _quote(intent)
    if k == "compare":
        return _compare(intent) if len(intent.codes) >= 2 else _quote(intent) if intent.codes else None
    if k == "overview":
        return _overview(intent, watch_codes)
    if k == "sector":
        return _sector(intent)
    if k == "sector_top":
        return _sector_top(intent)
    if k == "watchlist":
        return _watchlist(intent, watch_codes)
    if k == "advice":   # 不推荐；说到了行业就讲行业成分股的数据，没说就讲自选的
        return _sector_top(intent, refuse=True) if intent.sector else _watchlist(intent, watch_codes, refuse=True)
    if k == "sim_start":
        return _reply(intent, "好，开始行情异动模拟。我替你盯着自选股，有异动就转头提醒你。",
                      _msg("行情异动模拟", "我替你盯着自选股，有异动就转头提醒你。", hint="说“停止模拟”结束", meta="模拟数据 · " + LEGAL),
                      "nod", 1, action="sim_start")
    if k == "sim_stop":
        return _reply(intent, "好，模拟结束。", None, "nod", 1, action="sim_stop")
    # explain / unknown：大模型 + PandaAI 数据工具；它也负责判断是不是在跟我说话（背景闲聊 → None）
    return _agent(intent, log)
