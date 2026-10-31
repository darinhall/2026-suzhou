"""T06：整条流水线（假行情 + 假大模型）。"""

import asyncio

import pytest

pipeline = pytest.importorskip("brain.pipeline")
cards = pytest.importorskip("brain.cards")
from conftest import FakeLLM  # noqa: E402


def ask(brain, text, **kw):
    return asyncio.run(brain.ask(text, **kw))


def test_yesno_up_nods(market, llm):
    r = ask(pipeline.Brain(market, llm), "宁德时代今天涨了吗？")
    assert r["intent"] == "yesno"
    assert r["gesture"] == "nod"
    assert r["card"]["tone"] == "up"
    assert cards.validate(r["card"]) == []


def test_yesno_down_shakes(market, llm):
    r = ask(pipeline.Brain(market, llm), "比亚迪今天涨了吗？")
    assert r["gesture"] == "shake"
    assert r["card"]["tone"] == "down"


def test_advice_is_refused(market, llm):
    r = ask(pipeline.Brain(market, llm), "我应该全仓买入中芯国际吗？")
    assert r["intent"] == "advice"
    assert r["gesture"] == "shake"
    assert r["card"]["tone"] == "warn"


def test_compare_has_two_series(market, llm):
    r = ask(pipeline.Brain(market, llm), "比较一下宁德时代和比亚迪最近一个月")
    assert r["intent"] == "compare"
    assert len(r["card"]["series"]) == 2


def test_unknown_stock_shakes(market, llm):
    r = ask(pipeline.Brain(market, llm), "火星科技今天涨了吗")
    assert r["gesture"] == "shake"


def test_llm_failure_falls_back_to_template(market):
    r = ask(pipeline.Brain(market, FakeLLM(fail=True)), "宁德时代今天涨了吗？")
    assert r["llm"] == "template"
    assert r["say"]


def test_card_always_has_source(market, llm):
    for q in ["宁德时代今天涨了吗？", "今天大盘怎么样？", "我的自选股今天谁最强？"]:
        assert ask(pipeline.Brain(market, llm), q)["card"]["src"]
