"""自由提问：规则认不出的话交给大模型 + PandaAI MCP 工具（brain/panda_mcp.py）。

    answer(text, last_trade_date) → {"for_me", "title", "say"} | None

- 大模型（DeepSeek，方舟）自己决定调哪个 PandaData 方法；常用方法的准确参数写在工具说明里，少走"查文档"这一步。
- 算数交给 Python：区间涨跌用 period_return，换算 / 加减乘除用 calc，不让大模型心算（decisions.md §2）。
- 说出来的每个带小数 / 百分号的数字都要能在工具结果里找到（允许 万 / 亿 / 百分比 换算和四舍五入），
  对不上就让它改一次，还对不上就不说数字。
- 背景闲聊（不是对机器人说的）→ for_me=false，中枢什么都不做。
"""

from __future__ import annotations

import json
import re
import time

from brain import llm

MAX_ROUNDS = 8
DEADLINE_S = 15    # 总时长上限：到点就让它用已有结果直接回答（板子最多等 30 秒）
ROWS = 20          # 工具结果最多给大模型看几行（取最后几行 = 最新的）
RESULT_CHARS = 3500

CHEATSHEET = """常用方法（参数名准确，* = 必填；日期都是 YYYYMMDD；A 股代码 600519.SH / 300750.SZ / 688981.SH，指数 000001.SH / 399001.SZ / 399006.SZ / 000300.SH，港股是 4 位 + .HK：腾讯 0700.HK、美团 3690.HK、小米 1810.HK）：
- get_stock_daily(symbol, start_date*, end_date*, fields)  A股日线：open high low close volume amount pre_close name
- get_index_daily(start_date*, end_date*, symbol, fields)  指数日线
- get_hk_daily(start_date*, end_date*, symbol, fields) / get_us_daily(...)  港股 / 美股日线
- get_stock_industry(stock_symbol*, level)  股票所属行业：industry_name parent_l1_name
- get_concept_constituents(concept, concept_stock, date)  概念成分：传 concept_stock=股票代码 查它属于哪些概念；传 concept=概念名 查成分股
- get_concept_list(concept)  概念列表（可按名字筛）
- get_lhb_list(start_date*, end_date*, symbol)  龙虎榜：symbol reason amount deviation
- get_fina_forecast(symbol, end_quarter)  业绩预告：forecast_type forecast_description forecast_np_floor/ceiling（end_quarter 如 2026q3）
- get_fina_performance(symbol, end_quarter)  财务快报：operating_revenue net_profit_parent basic_eps
- get_margin(symbol, start_date*, end_date*)  融资融券：margin_balance short_balance total_balance
- get_hsgt_hold(symbol, start_date*, end_date*)  北向（沪深股通）持股：shares_num holding_ratio
- get_top_holders(symbol, start_date*, end_date*, end_rank)  十大股东
- get_holder_count(symbol, start_date, end_date)  股东户数
- get_index_indicator(symbol, start_date, end_date)  指数估值：pe_ttm pb_lf
- get_industry_detail(level)  行业列表（level = L1 / L2 / L3；没有 date 参数）
- get_industry_constituents(industry_code, level)  行业成分股
- get_restricted_list(symbol, start_date*, end_date*)  限售解禁
行业 / 板块 / 主题的行情：先 find_index 按名字找指数代码，再 period_return。
代码规则：A 股 6/9 开头 .SH，0/2/3 开头 .SZ；指数代码以 find_index 返回的为准（可能是 .CSI、H3xxxx.SH）。**不要自己改代码后缀**，换了就是另一只证券。
不在上面的：先 search_methods 找方法名，再 method_doc 看参数。"""

TOOLS = [
    {"type": "function", "function": {
        "name": "panda", "description": "调用一个 PandaData 方法（PandaAI 官方数据，经 MCP 网关）。\n" + CHEATSHEET,
        "parameters": {"type": "object", "properties": {
            "method": {"type": "string", "description": "方法名，如 get_stock_daily"},
            "params": {"type": "object", "description": "参数，名字必须和文档一致"}}, "required": ["method", "params"]}}},
    {"type": "function", "function": {
        "name": "period_return", "description": "A 股 / 指数 / 港股在最近 N 个交易日的涨跌（Python 算好的：名字、起止收盘价、区间涨跌幅、最新一天涨跌、最高、最低）。问「最近怎么样 / 一周 / 一个月涨了多少」先用它。返回里的 name 要核对是不是你要的那个。",
        "parameters": {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "如 688981.SH；指数如 000001.SH；港股如 0700.HK"},
            "days": {"type": "integer", "description": "交易日数：一周 5，一个月 22，三个月 66"}}, "required": ["symbol", "days"]}}},
    {"type": "function", "function": {
        "name": "find_index", "description": "按名字找指数代码（PandaAI 指数目录 2000 多个：行业、主题、宽基），如 医药、半导体、光伏、红利。",
        "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}}},
    {"type": "function", "function": {
        "name": "calc", "description": "算数（加减乘除、括号、round）。单位换算（元→亿元 除以 1e8）也用它，不要心算。",
        "parameters": {"type": "object", "properties": {"expr": {"type": "string"}}, "required": ["expr"]}}},
    {"type": "function", "function": {
        "name": "search_methods", "description": "按关键词找 PandaData 方法（305 个：A股、港美股、基金、期货、期权、宏观、因子）。",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "method_doc", "description": "看某个 PandaData 方法的准确参数和返回字段。",
        "parameters": {"type": "object", "properties": {"method": {"type": "string"}}, "required": ["method"]}}},
]


def _system(last: str) -> str:
    return (llm.SYSTEM + "\n"
            f"今天是 {time.strftime('%Y-%m-%d')}，最近一个交易日是 {last}（周末 / 休市时「今天」指这一天，要说明是哪天的数据）。\n"
            "你能用 PandaAI 数据工具回答行情、行业概念、财务、龙虎榜、融资融券、港美股、宏观等问题。\n"
            "规则：\n"
            "1. 麦克风会听到旁边人的闲聊。不是对你说的话（不是问题、和你无关、听不清的半句）→ 直接输出 {\"for_me\": false}，不要调工具。\n"
            "2. 数字只能来自工具结果；涨跌幅、区间变化、换算一律用 period_return / calc 算，不要心算。\n"
            "3. 不给买卖建议、不预测、不推荐股票；被问到就说你不做建议，只讲数据。\n"
            "4. 最后只输出一个 JSON：{\"for_me\": true, \"title\": \"不超过 10 个字的卡片标题\", \"say\": \"口语回答，不超过 60 个字\"}。"
            "say 里数字保留 1–2 位小数，金额用 亿 / 万，日期说成 10月30日；股票说名字不说代码（名字不知道就用 get_stock_daily 查 name）。"
            "「最近」默认看 5 个交易日。查不到就如实说查不到。")


# ---------- 工具 ----------
def _compact(result) -> str:
    """MCP 返回的表很大：只留最后 ROWS 行、去掉空字段，再截断。"""
    if isinstance(result, dict) and "columns" in result:
        cols = result["columns"]
        rows = result.get("rows") or result.get("data") or []
        result = [dict(zip(cols, r)) if isinstance(r, list) else r for r in rows]
    label = "rows(最后几行=最新)"
    if isinstance(result, list) and result and isinstance(result[0], dict):
        dates = {str(r.get("date")) for r in result}
        if len(result) > ROWS and len(dates) == 1 and "amount" in result[0]:   # 同一天的横截面（龙虎榜等）：按金额从大到小，截断也不丢最大的
            result = sorted(result, key=lambda r: -(r.get("amount") or 0))[:ROWS][::-1]
            label = f"rows(按 amount 从大到小的前 {ROWS} 行，最后一行最大)"
        elif "date" in result[0]:
            result = sorted(result, key=lambda r: str(r.get("date")))   # 接口是新的在前：排成从早到晚，最后几行 = 最新
    if isinstance(result, list):
        n = len(result)
        rows = [{k: v for k, v in r.items() if v not in (None, "", [])} if isinstance(r, dict) else r for r in result[-ROWS:]]
        while True:   # 太长就从前面丢行（最后几行是最新 / 最大的，不能截掉）
            s = json.dumps({"total_rows": n, label: rows}, ensure_ascii=False, default=str)
            if len(s) <= RESULT_CHARS or len(rows) <= 3:
                break
            rows = rows[1:]
        if n == 0:
            return '{"total_rows": 0, "note": "空表：没有这条数据，直接如实回答，不要换参数反复重试"}'
        return s[:RESULT_CHARS]
    s = json.dumps(result, ensure_ascii=False, default=str)
    return s[:RESULT_CHARS] + ("…（截断）" if len(s) > RESULT_CHARS else "")


def _mcp():
    from brain.panda_mcp import Client
    return Client().open()


def _calc(expr: str) -> str:
    if not re.fullmatch(r"[\d\s.+\-*/(),e]*", expr.replace("round", "")):   # 只剩数字、运算符和 round
        return "只支持数字和 + - * / ( ) round"
    try:
        return str(eval(expr, {"__builtins__": {}}, {"round": round}))
    except Exception as e:
        return f"算不了：{e}"


def _run_tool(name: str, args: dict, mcp_holder: list) -> str:
    try:
        if name == "calc":
            return _calc(str(args.get("expr", "")))
        if name == "period_return":
            from brain import series
            return json.dumps(series.period_return(str(args["symbol"]), int(args.get("days", 5))), ensure_ascii=False)
        if name == "find_index":
            from brain import series
            hits = series.find_index(str(args.get("keyword", "")))
            return json.dumps(hits or {"note": "没找到，换个关键词（比如更短的行业名）"}, ensure_ascii=False)
        if name.startswith("get_"):   # 大模型有时把 PandaData 方法名直接当工具名调：按 panda 处理
            args, name = {"method": name, "params": args.get("params", args)}, "panda"
        if not mcp_holder:
            mcp_holder.append(_mcp())
        c = mcp_holder[0]
        if name == "panda":
            out = c.call("call_pandadata", {"method": args["method"], "params": args.get("params") or {}})
            d = json.loads(out["content"][0]["text"])
            if not d.get("ok"):
                return json.dumps({"error": d.get("detail") or d.get("error")}, ensure_ascii=False)
            return _compact(d.get("result"))
        if name == "search_methods":
            d = json.loads(c.call("search_methods", {"query": args["query"]})["content"][0]["text"])
            items = d.get("methods") or d.get("results") or []
            return json.dumps([{"name": m["name"], "summary": m.get("summary")} for m in items[:12]], ensure_ascii=False)
        if name == "method_doc":
            d = json.loads(c.call("get_method_doc", {"method": args["method"]})["content"][0]["text"])
            return json.dumps(d, ensure_ascii=False)[:RESULT_CHARS]
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)
    return "没有这个工具"


# ---------- 数字核对 ----------
def _nums(s: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s.replace(",", ""))]


def unverified(say: str, evidence: str) -> list[str]:
    """say 里带小数或 % 的数字，在工具结果里（允许 ×1e4 / ×1e8 / ×100 和四舍五入）找不到的。"""
    ev = _nums(evidence)
    bad = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(%|亿|万)?", say):
        txt, unit = m.group(1), m.group(2)
        if "." not in txt and not unit:
            continue   # 整数（日期、名次、个数）不核对
        v = float(txt)
        tol = 0.5 * 10 ** -(len(txt.split(".")[1]) if "." in txt else 0) + 1e-9
        scales = [1, 1e4, 1e8, 0.01, 100]
        if not any(abs(abs(e) / s - v) <= tol for e in ev for s in scales):
            bad.append(m.group(0))
    return bad


def answer(text: str, last_trade_date: str, log=print) -> dict | None:
    msgs = [{"role": "system", "content": _system(last_trade_date)}, {"role": "user", "content": text}]
    evidence, mcp_holder, t0, fixed = [], [], time.monotonic(), False
    for rnd in range(MAX_ROUNDS + 1):
        late = time.monotonic() - t0 > DEADLINE_S or rnd == MAX_ROUNDS
        if late:   # 到点 / 轮数用完：不给工具了，用已经查到的直接回答
            msgs.append({"role": "user", "content": "时间到了。只用上面已经查到的工具结果，现在直接输出最终 JSON；查到的不够就如实说。"})
        r = llm.complete(msgs, tools=None if late else TOOLS)
        if r is None:
            return None
        m = r.choices[0].message
        if m.tool_calls and not late:
            msgs.append({"role": "assistant", "content": m.content or "", "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
            for tc in m.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                t1 = time.monotonic()
                out = _run_tool(tc.function.name, args, mcp_holder)
                log(f"[agent] {tc.function.name} {json.dumps(args, ensure_ascii=False)[:120]} → {len(out)} 字 {time.monotonic() - t1:.1f}s")
                evidence.append(out)
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": out})
            continue
        raw = (m.content or "").strip()
        mm = re.search(r"\{.*\}", raw, re.S)
        try:
            d = json.loads(mm.group(0)) if mm else {}
        except json.JSONDecodeError:
            d = {}
        if not d.get("for_me"):
            return {"for_me": False}
        say = str(d.get("say", "")).strip()
        bad = unverified(say, "\n".join(evidence)) if evidence or re.search(r"\d", say) else []
        if bad and not fixed:   # 有数字对不上：让它用工具结果改一次
            fixed = True
            msgs += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"这些数字在工具结果里找不到：{'、'.join(bad)}。只用工具结果里的数字（需要换算就调 calc），重新输出 JSON。"}]
            continue
        if bad:
            log(f"[agent] 数字还是对不上 {bad}，不说数字")
            say = "这个我查到了，但数字没核对上，先不乱说。你可以换个问法再问我。"
        log(f"[agent] 用时 {time.monotonic() - t0:.1f}s")
        return {"for_me": True, "title": str(d.get("title", "PandaAI 数据"))[:12], "say": say[:90]}
    return {"for_me": True, "title": "没查到", "say": "这个问题我查了几次没查到合适的数据，换个问法试试？"}
