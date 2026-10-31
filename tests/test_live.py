"""真数据测试：真的调 PandaAI 和大模型，确认我们和接口同步。

    DESKBOT_LIVE=1 uv run --group dev pytest -m live -v

要联网，要 data/.env 里的 PandaAI 账号（和方舟密钥，没有就用 Ollama）。默认不跑。
"""

import asyncio
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("DESKBOT_LIVE") != "1", reason="设 DESKBOT_LIVE=1 才跑真数据测试"),
]

CODES = ["300750", "002594", "688981", "600519", "600036"]


@pytest.fixture(scope="module")
def market():
    mod = pytest.importorskip("brain.market")
    return mod.Market() if hasattr(mod, "Market") else mod


def test_panda_login_and_last_trade_date():
    import panda_client
    panda_client.login()
    d = panda_client.PandaClient().last_trade_date()
    assert d and len(str(d)) == 8   # YYYYMMDD


@pytest.mark.parametrize("code", CODES)
def test_day_is_real(market, code):
    d = market.day(code)
    assert d["close"] > 0 and d["pre_close"] > 0
    assert d["low"] <= d["close"] <= d["high"]
    assert len(d["intraday"]) >= 48


def test_replay_clock(market):
    d0, d12, close = market.day("300750", at=0), market.day("300750", at=12), market.day("300750")
    assert len(d12["intraday"]) == 13
    assert "回放" in d12["asof"] and "收盘" in close["asof"]
    assert d12["close"] == pytest.approx(d12["intraday"][-1])
    assert d0["close"] != close["close"] or d12["close"] != close["close"]


def test_history_feeds_metrics(market):
    m = pytest.importorskip("brain.metrics")
    h = market.history("300750", days=22)
    assert 15 <= len(h) <= 22
    assert -60 < m.pct_return(h["close"]) < 60
    assert m.max_drawdown(h["close"]) <= 0


def test_llm_explains_real_numbers(market):
    llm = pytest.importorskip("brain.llm")
    pipeline = pytest.importorskip("brain.pipeline")
    brain = pipeline.Brain(market, llm.from_env())
    r = asyncio.run(brain.ask("宁德时代今天涨了吗？"))
    assert r["llm"] in ("ark", "ollama", "template")
    assert r["gesture"] in ("nod", "shake")
    assert r["say"] and r["card"]["src"].startswith("PandaAI")
    assert r["ms"] < 6000


def test_llm_provider_is_reachable():
    llm = pytest.importorskip("brain.llm")
    client = llm.from_env()
    if getattr(client, "provider", "template") == "template":
        pytest.skip("DESKBOT_LLM=template：没有可测的大模型")
    e = client.explain("quote", {"name": "宁德时代", "day_pct": 2.1}, lang="zh")
    assert e.provider in ("ark", "ollama")
    assert llm.check_numbers(e.say, {"name": "宁德时代", "day_pct": 2.1})
