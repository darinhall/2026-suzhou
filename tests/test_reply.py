"""T05 / T06：防编造检查、模板兜底、卡片格式（protocol.md）。"""

import json
from pathlib import Path

import pytest

llm = pytest.importorskip("brain.llm")
cards = pytest.importorskip("brain.cards")

CARDS = Path(__file__).parent / "fixtures" / "cards"


def test_numbers_must_come_from_facts():
    facts = {"day_pct": 2.1, "rel_pct": 0.83}
    assert llm.check_numbers("收涨 2.1%，跑赢创业板 0.8 个点", facts)
    assert not llm.check_numbers("收涨 5.0%", facts)
    assert llm.check_numbers("宁德时代收涨了", facts)   # 没有数字也算通过


def test_template_never_fails_and_is_honest():
    facts = {"name": "宁德时代", "day_pct": 2.1, "bench_name": "创业板指", "rel_pct": 0.83}
    e = llm.template_explain("yesno", facts, lang="zh")
    assert e.say and e.provider == "template"
    assert llm.check_numbers(e.say, facts)


@pytest.mark.parametrize("path", sorted(CARDS.glob("*.json")), ids=lambda p: p.stem)
def test_fixture_cards_follow_protocol(path):
    card = json.loads(path.read_text())
    errors = cards.validate(card)
    if path.stem.startswith("bad_"):
        assert errors
    else:
        assert errors == []
