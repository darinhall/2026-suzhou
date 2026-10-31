"""T16：人格 JSON 和交易人格游戏保持一致。"""

import re
from pathlib import Path

import pytest

persona = pytest.importorskip("brain.persona")

GAME = Path(__file__).resolve().parent.parent / "sim" / "game" / "persona.js"


def test_ids_match_game():
    game_ids = re.findall(r"id: '(\w+)'", GAME.read_text())
    assert sorted(persona.ids()) == sorted(game_ids)


@pytest.mark.parametrize("pid", ["surfer", "hunter", "guardian", "holder", "flash"])
def test_every_persona_is_complete(pid):
    p = persona.load(pid)
    assert p["id"] == pid
    for k in ("cross_pct", "glance_ratio", "surge_pct_5m", "vol_ratio", "max_level", "cooldown_s"):
        assert k in p["alerts"]
    assert 0 < p["alerts"]["glance_ratio"] < 1
    assert p["voice"]["tone"]


def test_unknown_falls_back_to_default():
    assert persona.load("nope")["id"] == "guardian"
    assert persona.load(None)["id"] == "guardian"


def test_sensitivity_order():
    """闪电最敏感，佛系最迟钝：演示 3 的对比靠这个。"""
    cross = {pid: persona.load(pid)["alerts"]["cross_pct"] for pid in persona.ids()}
    assert cross["flash"] < cross["surfer"] <= cross["guardian"] < cross["holder"]
