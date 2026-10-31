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
    ("生物医药现在怎么样",                  "sector",       []),
    ("医药股最近怎么样",                    "sector",       []),
    ("恒瑞医药怎么样",                      "quote",        ["600276"]),   # 股票名里带「医药」：还是个股
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


def test_sector_picks_longest_alias():
    from brain import sectors
    assert sectors.find("生物医药现在怎么样")[1] == "399441.SZ"   # 不是「医药」
    assert sectors.find("医药股最近怎么样")[1] == "000933.SH"
    assert sectors.find("半导体板块")[1] == "H30184.SH"
    assert sectors.find("今天天气怎么样") is None


def test_stock_suffix_never_swapped():
    from brain import series
    assert series.stock_suffix_error("600519.SH") is None
    assert series.stock_suffix_error("300750.SZ") is None
    assert "不要自己换后缀" in series.stock_suffix_error("000933.SH")   # 000 开头是深市股票；800医卫指数要走指数目录
    assert series.stock_suffix_error("600519.SZ")


def test_this_sector_refers_to_previous_sector():
    r = router.Router()
    assert r.route("帮我看看食品饮料板块。").kind == "sector"
    it = r.route("这个板块有没有什么值得推荐的个股？")   # 11-01 现场原话
    assert it.kind == "advice" and it.sector[1] == "000807.SH"
    it = r.route("这个板块里哪只涨得最好")
    assert it.kind == "sector_top" and it.sector[1] == "000807.SH"
    assert r.route("今天推荐什么股票").sector == ()   # 没提板块：还是自选的数据
