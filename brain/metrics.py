"""指标计算：卡片上的每个数字都从这里来（T02）。纯函数，只用 numpy，不联网。

输入是收盘价序列（list / tuple / pandas.Series，从早到晚）。百分比都是"百分数"（2.1 表示 2.1%）。
序列太短（< 2 个点）一律抛 ValueError，由调用方转成"数据不足"。
"""

from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252


def _arr(closes, min_len: int = 2) -> np.ndarray:
    a = np.asarray(list(closes), dtype=float)
    if a.size < min_len:
        raise ValueError(f"数据不足：需要至少 {min_len} 个点，只有 {a.size} 个")
    return a


def _returns(a: np.ndarray) -> np.ndarray:
    return a[1:] / a[:-1] - 1


def pct_return(closes) -> float:
    """区间涨跌 %：(最后 / 第一 - 1) × 100。"""
    a = _arr(closes)
    return float((a[-1] / a[0] - 1) * 100)


def day_change(close: float, pre_close: float) -> float:
    """当日涨跌 %。"""
    if not pre_close:
        raise ValueError("昨收为 0")
    return float((close / pre_close - 1) * 100)


def moving_average(closes, n: int) -> list[float | None]:
    """n 日均线，前 n-1 个为 None。"""
    a = np.asarray(list(closes), dtype=float)
    out: list[float | None] = [None] * min(n - 1, a.size)
    if a.size >= n:
        c = np.cumsum(np.insert(a, 0, 0.0))
        out += [float(x) for x in (c[n:] - c[:-n]) / n]
    return out


def volatility(closes, annualize: bool = True) -> float:
    """日收益率标准差（样本，ddof=1），单位 %；annualize 时 × sqrt(252)。只有一个收益率时为 0。"""
    r = _returns(_arr(closes))
    sd = float(np.std(r, ddof=1)) if r.size > 1 else 0.0
    return sd * 100 * (math.sqrt(TRADING_DAYS) if annualize else 1)


def max_drawdown(closes) -> float:
    """最大回撤 %（≤ 0），例如 -12.5。"""
    a = _arr(closes)
    peak = np.maximum.accumulate(a)
    return float(np.min(a / peak - 1) * 100)


def relative(a, b) -> float:
    """a 相对 b 的强弱：区间涨跌之差，单位百分点。"""
    return pct_return(a) - pct_return(b)


def correlation(a, b) -> float:
    """日收益率的皮尔逊相关。长度不同时按末尾对齐。"""
    x, y = _arr(a, 3), _arr(b, 3)
    n = min(x.size, y.size)
    rx, ry = _returns(x[-n:]), _returns(y[-n:])
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def normalize(closes, base: float = 100) -> list[float]:
    """归一到 base（画对比图用）。"""
    a = _arr(closes)
    return [float(x) for x in a / a[0] * base]


def summary(closes, pre_close: float | None = None, bench=None) -> dict:
    """给大模型和卡片用的一包指标（都保留 2 位小数）。bench = 对比基准的收盘价序列。"""
    a = _arr(closes)
    out = {"period_pct": pct_return(a), "max_drawdown_pct": max_drawdown(a), "last": float(a[-1])}
    if a.size >= 3:
        out["volatility_pct"] = volatility(a)
    if pre_close:
        out["day_pct"] = day_change(float(a[-1]), pre_close)
    if bench is not None:
        out["rel_pct"] = relative(a, bench)
        if a.size >= 3:
            out["corr"] = correlation(a, bench)
    return {k: round(v, 2) for k, v in out.items()}
