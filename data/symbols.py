"""PandaAI 代码（symbol）拼接。

规则来源：
- 期货：Data Overview 页（交易所后缀 + 品种表），例 RB.SHF、IF.CFE
- 港股 .HK、美股 .NB：Data Overview 页，例 0700.HK、AAPL.NB
- A 股 / 指数后缀 .SH / .SZ：panda_data 1.0.5 SDK 自带示例（000001.SZ、600000.SH、000300.SH）
- 6 位代码前缀 → 交易所：沪深交易所的通用编号规则（不是 PandaAI 文档里的，已标注）
"""

FUTURES = {
    "CFE": "IC IF IH IM T TF TL TS",
    "CZC": "AP CF CJ CY ER FG JR LR MA ME OI PF PK PL PM PR PX RI RM RO RS SA SF SH SM SR TA TC UR WH WS WT ZC",
    "DCE": "A B BB BZ C CS EB EG FB I J JD JM L LG LH L_F M P PG PP PP_F RR S V V_F Y",
    "SHF": "AD AG AL AO AU BR BU CU FU HC NI OP PB RB RU SN SP SS WR ZN",
    "INE": "BC EC LU NR SC",
    "GFE": "LC PD PS PT SI",
}
FUTURE_EXCHANGE = {code: ex for ex, codes in FUTURES.items() for code in codes.split()}

# 指数池（Data Overview 页的部分列表）
UNIVERSES = {
    "000300": "沪深300", "000905": "中证500", "000906": "中证800", "000852": "中证1000",
    "000016": "上证50", "000010": "上证180", "000009": "上证380", "399001": "深证成指",
    "399006": "创业板指", "000688": "科创50",
}


def a_share(code: str) -> str:
    """6 位 A 股代码 → 600000.SH / 300750.SZ。只支持沪深（文档：Only SSE and SZSE）。"""
    code = code.strip()
    if "." in code:
        return code.upper()
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"A 股代码应为 6 位数字：{code!r}")
    # 交易所通用编号规则：6/9 开头上交所，0/2/3 开头深交所；4/8 开头是北交所，PandaAI 不支持
    if code[0] in "69":
        return f"{code}.SH"
    if code[0] in "023":
        return f"{code}.SZ"
    raise ValueError(f"{code} 不是沪深股票（北交所等不支持）")


def index(code: str) -> str:
    """指数代码 → 000300.SH / 399006.SZ。"""
    code = code.strip()
    if "." in code:
        return code.upper()
    if code.startswith("399"):
        return f"{code}.SZ"
    if len(code) == 6 and code.isdigit():
        # SDK 示例用 000300.SH；中证指数（000300、000905 等）挂在 .SH 下
        return f"{code}.SH"
    # TODO: confirm suffix for H-prefixed CSI codes (e.g. H30539 中证白酒) — not shown in docs or SDK examples
    raise ValueError(f"不确定 {code!r} 的后缀，先跟 PandaAI 确认")


def future(code: str) -> str:
    """期货品种（或合约）→ RB.SHF / IF.CFE / RB2501.SHF。只用于显示；调接口用 future_api()。"""
    code = code.strip().upper()
    if "." in code:
        return code
    product = code.rstrip("0123456789").removesuffix("_DOMINANT")
    ex = FUTURE_EXCHANGE.get(product)
    if ex is None:
        raise ValueError(f"未知期货品种：{product!r}")
    return f"{code}.{ex}"


def future_api(code: str) -> str:
    """调期货接口用的代码：不带交易所后缀（实测 RB.SHF 会被拒，错误码 100002）。
    接口接受：品种+4位年月（RB2601，郑商所也是 4 位）、品种+_DOMINANT（主力连续）、或如 L2602F。
    只给品种（RB）时默认主力连续 RB_DOMINANT。"""
    code = code.strip().upper().split(".")[0]
    product = code.rstrip("0123456789F").removesuffix("_DOMINANT") or code
    if code.rstrip("0123456789").removesuffix("_DOMINANT") not in FUTURE_EXCHANGE and product not in FUTURE_EXCHANGE:
        raise ValueError(f"未知期货品种：{code!r}")
    return code if (code[-1].isdigit() or code.endswith("_DOMINANT") or code.endswith("F")) else f"{code}_DOMINANT"


def hk(code: str) -> str:
    """港股 → 0700.HK（文档示例是 4 位，不足补 0）。"""
    code = code.strip().upper().removesuffix(".HK")
    return f"{code.zfill(4)}.HK"


def us(code: str) -> str:
    """美股 → AAPL.NB。"""
    return f"{code.strip().upper().removesuffix('.NB')}.NB"


BUILDERS = {"a": a_share, "index": index, "future": future_api, "future_display": future, "hk": hk, "us": us}


def symbol(market: str, code: str) -> str:
    """symbol("a", "300750") → "300750.SZ"；market 取 a / index / future / hk / us。"""
    try:
        return BUILDERS[market](code)
    except KeyError:
        raise ValueError(f"market 应为 {sorted(BUILDERS)} 之一，收到 {market!r}") from None


if __name__ == "__main__":
    for m, c in [("a", "300750"), ("a", "600000"), ("index", "000300"), ("index", "399006"),
                 ("future", "RB"), ("future", "if"), ("future", "RB2601"), ("future_display", "RB"), ("hk", "700"), ("us", "aapl")]:
        print(f"{m:7} {c:8} → {symbol(m, c)}")
