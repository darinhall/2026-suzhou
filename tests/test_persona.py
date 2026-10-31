"""提醒阈值配置（brain/personas.json）：默认 standard；5 个交易人格搁置（T16）但保持和游戏一致。"""

import re
from pathlib import Path

import pytest

persona = pytest.importorskip("brain.persona")

GAME = Path(__file__).resolve().parent.parent / "sim" / "game" / "persona.js"


def test_ids_match_game():
    game_ids = re.findall(r"id: '(\w+)'", GAME.read_text())
    assert sorted(i for i in persona.ids() if i != "standard") == sorted(game_ids)


@pytest.mark.parametrize("pid", ["standard", "surfer", "hunter", "guardian", "holder", "flash"])
def test_every_persona_is_complete(pid):
    p = persona.load(pid)
    assert p["id"] == pid
    for k in ("cross_pct", "glance_ratio", "surge_pct_5m", "vol_ratio", "max_level", "cooldown_s"):
        assert k in p["alerts"]
    assert 0 < p["alerts"]["glance_ratio"] < 1
    assert p["voice"]["tone"]


def test_unknown_falls_back_to_default():
    assert persona.load("nope")["id"] == "standard"
    assert persona.load(None)["id"] == "standard"


def test_sensitivity_order():
    """闪电最敏感，佛系最迟钝：演示 3 的对比靠这个。"""
    cross = {pid: persona.load(pid)["alerts"]["cross_pct"] for pid in persona.ids()}
    assert cross["flash"] < cross["standard"] < cross["holder"]
    assert cross["flash"] < cross["surfer"] <= cross["guardian"] < cross["holder"]
