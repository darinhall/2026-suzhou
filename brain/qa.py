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
    if face and face.get("state") == "answer":   # 答案卡：问题、动作标签、字幕都放进卡片（板子不做任何拼接）
        c = face["card"]
        c.setdefault("q", intent.text.strip().rstrip("。？！?!.")[:18])
        c.setdefault("say", say)
        if gesture:
            c.setdefault("act", {"nod": "点头", "shake": "摇头"}.get(gesture, ""))
    return {"intent": intent.kind, "text": intent.text, "codes": intent.codes, "say": say, "face": face,
            "gesture": {"name": gesture, "times": times} if gesture else None, "action": action}


def _ans(head: str, tone: str, big: str = "", sub: str = "", series=None, stats=None, pts=None, src: str = "") -> dict:
    """答案卡（protocol.md）：head 结论 · big 大数字 · series 走势（相对起点 %）· stats 指标 · pts 要点 · src 来源。"""
    card = {"v": 2, "head": head, "tone": tone, "big": big, "sub": sub, "src": src or "PandaAI"}
    if series:
        card["series"] = series
    if stats:
        card["stats"] = stats[:4]
    if pts:
        card["pts"] = pts[:3]
    return {"state": "answer", "card": card}


def _tone(p: float) -> str:
    return "up" if p > 0 else "down" if p < 0 else "flat"


def _sp(p: float) -> str:
    return f"{'+' if p >= 0 else '-'}{abs(p):.2f}%"


def _curve(closes, prev) -> list[float]:
    """分时 / 日线收盘价 → 相对昨收（或起点）的涨跌幅 %，最多 48 个点。"""
    closes = [c for c in closes if c]
    if not closes or not prev:
        return []
    step = max(1, len(closes) // 48)
    return [round((c / prev - 1) * 100, 2) for c in closes[::step]][:48]


def _bench(day, code: str):
    """对比指数：创业板股票比创业板指，沪市比上证，深市比深证成指。"""
    want = "创业板指" if code.startswith("3") else "上证指数" if code.startswith("6") else "深证成指"
    return next((ix for ix in day.get("indices", []) if ix.get("name") == want), None)


def _quote(intent: Intent) -> dict:
    from watch import stock_state
    day = _day(intent.codes[:1])
    s = stock_state(day, 0, None)
    raw = day["stocks"][0]
    bits = [f"{s['name']}{_spoken(day)}报 {s['price']:.2f} 元，{_ud(s['pct'])} {_pct(s['pct'])}"]
    if s.get("vol_ratio"):
        bits.append(f"量比 {s['vol_ratio']:.1f}")
    series = [{"name": s["name"], "pts": _curve(raw.get("closes", []), raw.get("prev_close"))}]
    ix = _bench(day, s["code"])
    if ix:
        series.append({"name": ix["name"], "pts": _curve(ix.get("closes", []), ix.get("prev_close"))})
    stats = [["收盘", f"{s['price']:.2f}"], ["振幅", f"{s.get('amp', 0):.1f}%"]]
    if s.get("vol_ratio"):
        stats.append(["量比", f"{s['vol_ratio']:.1f}"])
    if s.get("amount"):
        stats.append(["成交额", f"{s['amount']:.0f}亿"])
    if intent.kind == "yesno":
        head = "涨了" if s["pct"] > 0 else "跌了" if s["pct"] < 0 else "平盘"
        say = head + "。" + "，".join(bits) + "。"
        gesture = "nod" if s["pct"] > 0 else "shake"
        times = 2
    else:
        head = f"收{'涨' if s['pct'] >= 0 else '跌'} {_pct(s['pct'])}"
        say = "，".join(bits) + "。"
        gesture, times = "nod", 1
    face = _ans(head, _tone(s["pct"]), _sp(s["pct"]), f"{s['code']} · {s['name']}", series, stats, src=f"PandaAI · {_asof(day)}")
    return _reply(intent, say, face, gesture, times)


def _compare(intent: Intent) -> dict:
    from watch import stock_state
    day = _day(intent.codes[:3])
    sts = [stock_state(day, k, None) for k in range(len(day["stocks"]))]
    best = max(sts, key=lambda s: s["pct"])
    say = "，".join(f"{s['name']}{_ud(s['pct'])} {_pct(s['pct'])}" for s in sts) + f"。{best['name']}更强。"
    order = [best] + [s for s in sts if s is not best]
    raw = {st["code"]: st for st in day["stocks"]}
    series = [{"name": s["name"], "pts": _curve(raw[s["code"]].get("closes", []), raw[s["code"]].get("prev_close"))} for s in order[:2]]
    stats = [[s["name"], _sp(s["pct"])] for s in order[:4]]
    face = _ans(f"{best['name']}更强", _tone(best["pct"]), _sp(best["pct"]), " vs ".join(s["name"] for s in order[:2]), series, stats,
                src=f"PandaAI · {_asof(day)}")
    return _reply(intent, say, face)


def _overview(intent: Intent, watch_codes) -> dict:
    from watch import indices_state
    day = _day(watch_codes)
    ixs = indices_state(day)
    up = sum(1 for x in ixs if x["pct"] >= 0)
    mood = "普涨" if up == len(ixs) else "普跌" if up == 0 else "涨跌互现"
    say = f"{_spoken(day)}，大盘{mood}：" + "，".join(f"{x['name']}{_ud(x['pct'])} {_pct(x['pct'])}" for x in ixs[:3]) + "。"
    main = ixs[0]
    raws = day.get("indices", [])
    series = [{"name": r["name"], "pts": _curve(r.get("closes", []), r.get("prev_close"))} for r in raws[:3:2]]   # 上证 + 创业板
    stats = [[x["name"].replace("指数", ""), _sp(x["pct"])] for x in ixs[:4]]
    face = _ans(f"大盘{mood}", _tone(main["pct"]), _sp(main["pct"]), f"{main['name']} {main['value']:.2f}", series, stats,
                src=f"PandaAI · {_asof(day)}")
    return _reply(intent, say, face)


def _sector(intent: Intent) -> dict:
    """行业指数：最新一天涨跌 + 区间涨跌（默认最近 5 个交易日）。数字都是 brain/series.py 用 PandaAI 日线算的。"""
    from brain import series
    alias, code, _ = intent.sector
    days = intent.period_days if intent.period_days > 1 else 5
    r = series.period_return(code, days)
    if "error" in r:
        return _reply(intent, f"{alias}的数据暂时没取到。", _ans(alias, "flat", "", code, pts=["数据暂时没取到"]), None)
    d = r["to_date"]
    when = f"{int(d[4:6])}月{int(d[6:])}日"
    iname = r["name"] if r["name"].endswith("指数") else r["name"] + "指数"
    say = (f"{alias}看{iname}：{when}收在 {r['to_close']:.2f}，{_ud(r['last_day_pct'])} {_pct(r['last_day_pct'])}；"
           f"最近 {r['days']} 个交易日{_ud(r['change_pct'])} {_pct(r['change_pct'])}。")
    curve = _curve(r.get("closes", []), r.get("from_close"))
    stats = [["当天", _sp(r["last_day_pct"])], [f"近{r['days']}日", _sp(r["change_pct"])], ["收盘", f"{r['to_close']:.2f}"],
             ["区间", f"{r['low']:.0f}-{r['high']:.0f}"]]
    face = _ans(f"{alias}{'涨' if r['last_day_pct'] >= 0 else '跌'} {_pct(r['last_day_pct'])}", _tone(r["last_day_pct"]), _sp(r["change_pct"]),
                f"{iname} · 近{r['days']}日", [{"name": f"{iname} 近{r['days']}日", "pts": curve}], stats, src=f"PandaAI · {code} · {when}")
    return _reply(intent, say, face)


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
        return _reply(intent, say, _ans("不做买卖建议" if refuse else alias, "warn" if refuse else "flat", pts=["成分股数据暂时没取到"]),
                      "shake" if refuse else None, 2 if refuse else 1)
    d = m["date"]
    when = f"{int(d[4:6])}月{int(d[6:])}日"
    top = m["rows"][:3]
    tops = "、".join(f"{r['name']}{_ud(r['pct'])} {_pct(r['pct'])}" for r in top)
    facts = f"{alias}指数 {m['n']} 只成分股，{when}有 {m['up']} 只上涨，涨得最多的是{tops}。"
    stats = [[r["name"], _sp(r["pct"])] for r in top] + [["上涨", f"{m['up']}/{m['n']}"]]
    if refuse:
        face = _ans("不做买卖建议", "warn", "只讲数据", f"{alias}指数成分股 · {when}", stats=stats,
                    pts=[f"{m['up']}/{m['n']} 只上涨", f"领涨 {top[0]['name']}", "数据不是建议"], src=f"PandaAI · {code} 成分股")
        return _reply(intent, "我不推荐个股，只讲数据。" + facts, face, "shake", 2)
    face = _ans(f"{alias}领涨", _tone(top[0]["pct"]), _sp(top[0]["pct"]), f"{top[0]['name']} · {when}", stats=stats,
                pts=[f"{m['up']}/{m['n']} 只上涨"] + [f"{r['name']} {_sp(r['pct'])}" for r in top[:2]], src=f"PandaAI · {code} 成分股")
    return _reply(intent, facts, face)


def _watchlist(intent: Intent, watch_codes, refuse: bool = False) -> dict:
    from watch import stock_state, top_movers
    day = _day(watch_codes)
    hi, lo = top_movers(day)
    facts = f"你的自选里，{_spoken(day)}最强的是{hi['name']}，{_ud(hi['pct'])} {_pct(hi['pct'])}；最弱的是{lo['name']}，{_ud(lo['pct'])} {_pct(lo['pct'])}。"
    sts = sorted((stock_state(day, k, None) for k in range(len(day["stocks"]))), key=lambda s: -s["pct"])
    stats = [[s["name"], _sp(s["pct"])] for s in sts[:4]]
    if refuse:
        say = f"我不推荐股票。不过你的自选里，{hi['name']}最强，{_ud(hi['pct'])} {_pct(hi['pct'])}。"
        face = _ans("不做买卖建议", "warn", "只讲数据", f"你的自选 · {_asof(day)}", stats=stats,
                    pts=[f"最强 {hi['name']} {_sp(hi['pct'])}", f"最弱 {lo['name']} {_sp(lo['pct'])}", "数据不是建议"], src=f"PandaAI · {_asof(day)}")
        return _reply(intent, say, face, "shake", 2)
    face = _ans(f"最强：{hi['name']}", _tone(hi["pct"]), _sp(hi["pct"]), f"你的自选 · {_asof(day)}", stats=stats,
                pts=[f"最弱 {lo['name']} {_sp(lo['pct'])}"], src=f"PandaAI · {_asof(day)}")
    return _reply(intent, facts, face, "nod", 1)


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
    return _reply(intent, say, _ans(d.get("title") or "PandaAI 数据", "flat", pts=d.get("pts") or [], src="PandaAI 数据 · MCP"))


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
