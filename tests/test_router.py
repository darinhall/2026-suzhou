"""T04：一句话 → 意图 + 股票代码。加新句子就在表里加一行。"""

import pytest

router = pytest.importorskip("brain.router")

CASES = [
    # 文字,                              kind,        codes
    ("宁德时代今天涨了吗？",               "yesno",     ["300750"]),
    ("茅台跌了没有",                      "yesno",     ["600519"]),
    ("看一下比亚迪",                      "quote",     ["002594"]),
    ("中芯国际怎么样",                    "quote",     ["688981"]),
    ("比较一下宁德时代和比亚迪最近一个月",   "compare",   ["300750", "002594"]),
    ("今天大盘怎么样？",                   "overview",  []),
    ("我的自选股今天谁最强？",              "watchlist", []),
    ("我应该全仓买入中芯国际吗？",          "advice",    ["688981"]),
    ("推荐一只能涨的股票",                 "advice",    []),
    ("下一只",                           "control",   []),
    ("宁德时带今天涨了吗",                 "yesno",     ["300750"]),   # 语音识别错字
    ("宁王涨了吗",                        "yesno",     ["300750"]),   # 别名
    ("把比亚迪加到自选",                   "watch_add",    ["002594"]),
    ("关注一下中芯国际",                   "watch_add",    ["688981"]),
    ("删掉招商银行",                      "watch_remove", ["600036"]),
    ("不看茅台了",                        "watch_remove", ["600519"]),
    ("我的自选有哪些",                     "watch_list",   []),
    # 11-01 现场说的话（语音识别原样）
    ("帮我看看中芯国际的股票。",             "quote",        ["688981"]),
    ("帮我看看中芯国际的行情",               "quote",        ["688981"]),
    ("今天推荐什么股票？",                  "advice",       []),
    ("行情移动模拟",                       "sim_start",    []),   # 「异动」被听成「移动」
    ("行情异动模拟。",                      "sim_start",    []),
    ("停止模拟",                          "sim_stop",     []),
    ("今天天气怎么样",                     "unknown",      []),
    ("大阪怎么样？",                       "overview",     []),   # 「大盘」被听成「大阪」
    ("宁德时代属于哪些概念",                "research",     ["300750"]),   # 要查 MCP
    ("茅台三季度业绩预告怎么说",             "research",     ["600519"]),
]


@pytest.mark.parametrize("text,kind,codes", CASES)
def test_route(text, kind, codes):
    it = router.Router().route(text)
    assert it.kind == kind
    assert it.codes == codes


def test_period():
    r = router.Router()
    assert r.route("比较一下宁德时代和比亚迪最近一个月").period_days == 22
    assert r.route("宁德时代最近一周怎么样").period_days == 5
    assert r.route("宁德时代今天涨了吗").period_days == 1


def test_followup_uses_previous_codes():
    r = router.Router()
    r.route("宁德时代今天涨了吗")
    it = r.route("和比亚迪比呢？")
    assert it.kind == "compare"
    assert it.codes == ["300750", "002594"]
    assert r.route("为什么？").kind == "explain"


def test_unknown_stock_is_not_guessed():
    it = router.Router().route("火星科技今天涨了吗")
    assert it.codes == []
