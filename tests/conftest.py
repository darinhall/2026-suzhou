"""测试共用：假行情、假大模型。测试不联网、不连板子（plan/README.md「测试怎么跑」）。"""

from types import SimpleNamespace

import pandas as pd
import pytest

# 10-30 风格的样本：宁德时代涨、比亚迪跌、中芯国际波动大。数字是造的，只保证方向和量级。
DAYS = {
    "300750": dict(name="宁德时代", close=255.0, pre_close=249.75, high=257.0, low=248.0, amount=9.8e9),
    "002594": dict(name="比亚迪", close=98.0, pre_close=100.0, high=101.0, low=97.5, amount=6.1e9),
    "688981": dict(name="中芯国际", close=120.0, pre_close=118.0, high=124.0, low=115.0, amount=1.2e10),
    "600519": dict(name="贵州茅台", close=1450.0, pre_close=1450.0, high=1460.0, low=1440.0, amount=4.0e9),
    "600036": dict(name="招商银行", close=42.0, pre_close=41.8, high=42.3, low=41.6, amount=2.5e9),
}
INDICES = {
    "399006": dict(name="创业板指", close=2600.0, pre_close=2567.0),
    "000001": dict(name="上证指数", close=3300.0, pre_close=3290.0),
}


def _hist(start: float, step: float, n: int = 22) -> list[float]:
    return [round(start * (1 + step) ** i * (1 + 0.01 * (-1) ** i), 2) for i in range(n)]


HIST = {
    "300750": _hist(230, 0.005),
    "002594": _hist(110, -0.006),
    "688981": _hist(100, 0.009),
    "600519": _hist(1440, 0.0),
    "600036": _hist(41, 0.001),
}


class FakeMarket:
    """和 brain/market.py 一样的接口（T03）。"""

    def day(self, code):
        if code not in DAYS:
            raise KeyError(code)
        d = dict(DAYS[code], code=code, asof="10-30 收盘")
        d["intraday"] = [d["pre_close"] + (d["close"] - d["pre_close"]) * i / 47 for i in range(48)]
        return d

    def index_day(self, code="399006"):
        return dict(INDICES[code], code=code, asof="10-30 收盘",
                    intraday=[INDICES[code]["pre_close"] + (INDICES[code]["close"] - INDICES[code]["pre_close"]) * i / 47 for i in range(48)])

    def history(self, code, days=22):
        if code not in HIST:
            raise KeyError(code)
        closes = HIST[code][-days:]
        return pd.DataFrame({"date": [f"2026-10-{i + 1:02d}" for i in range(len(closes))], "close": closes, "amount": [1e9] * len(closes)})

    def watchlist(self):
        return list(DAYS)


class FakeLLM:
    """假大模型：回一句固定格式的话。fail=True 时模拟超时，流水线应降级到模板。"""

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def explain(self, intent, facts, lang="zh"):
        self.calls.append((intent, facts))
        if self.fail:
            raise TimeoutError("fake llm timeout")
        return SimpleNamespace(say="好的，这是数据。", head="结论", pts=["要点"], followups=["和比亚迪比呢？"], provider="fake")

    def extract(self, text):
        return None


@pytest.fixture
def market():
    return FakeMarket()


@pytest.fixture
def llm():
    return FakeLLM()
