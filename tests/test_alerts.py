"""T15：提醒阶梯。时间用假的时钟，测试不等真秒数。"""

import pytest

alerts = pytest.importorskip("brain.alerts")
persona = pytest.importorskip("brain.persona")
from brain.alerts import AlertWatcher, Tick  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def tick(pct, code="300750", name="宁德时代", closes=None, **kw):
    price = round(100 * (1 + pct / 100), 2)
    return Tick(code, name, pct, price, closes or [price, price], **kw)   # 默认最后 5 分钟没动：不算急涨急跌


def watcher(pid="guardian"):
    clk = Clock()
    return AlertWatcher(persona.load(pid), clock=clk), clk


def test_quiet_below_glance():
    w, _ = watcher()
    assert w.check([tick(1.0)]) == []


def test_ladder_glance_then_look():
    w, _ = watcher()   # 稳健：3% 转头，2.1% 瞥一眼
    (a,) = w.check([tick(2.2)])
    assert (a.level, a.kind, a.gesture) == (1, "glance", "glance")
    (b,) = w.check([tick(3.1)])
    assert (b.level, b.kind, b.gesture) == (2, "cross", "look")
    assert "3.1%" in b.say and "宁德时代" in b.say


def test_each_event_once():
    w, clk = watcher()
    assert w.check([tick(3.1)])
    clk.t += 1000
    assert w.check([tick(3.3)]) == []


def test_reset_on_replay_loop():
    w, _ = watcher()
    assert w.check([tick(3.1)])
    w.reset()
    assert w.check([tick(3.1)])


def test_cooldown_defers_not_drops():
    w, clk = watcher()   # 稳健 cooldown 60 秒
    assert w.check([tick(3.1)])[0].code == "300750"
    assert w.check([tick(-3.2, code="002594", name="比亚迪")]) == []   # 冷却中
    clk.t += 61
    (a,) = w.check([tick(-3.2, code="002594", name="比亚迪")])
    assert (a.code, a.level) == ("002594", 2)
    assert "跌到" in a.say


def test_one_big_alert_per_check():
    w, _ = watcher("flash")
    out = w.check([tick(1.5), tick(2.0, code="002594", name="比亚迪")])
    assert sum(a.level >= 2 for a in out) == 1


def test_persona_changes_threshold():
    calm, _ = watcher("guardian")
    fast, _ = watcher("flash")
    assert [a.level for a in calm.check([tick(1.2)])] == []
    assert [a.level for a in fast.check([tick(1.2)])] == [2]


def test_max_level_caps_ladder():
    w, _ = watcher("holder")   # 佛系：最多 1 级
    out = w.check([tick(6.0, closes=[100, 100, 100, 106])])
    assert out and max(a.level for a in out) == 1


def test_surge_is_level_3():
    w, _ = watcher("surfer")
    out = w.check([tick(1.2, closes=[100, 100.0, 100.0, 101.2])])
    assert out[0].kind == "surge" and out[0].level == 3


def test_opening_gap_is_not_a_surge():
    w, _ = watcher("surfer")
    assert all(a.kind != "surge" for a in w.check([tick(1.2, closes=[100.0, 101.2])]))


def test_down_only_ignores_rallies():
    w, _ = watcher("hunter")
    assert w.check([tick(4.0)]) == []
    assert w.check([tick(-4.0)])[0].level == 2


def test_limit_up():
    w, _ = watcher("surfer")
    out = w.check([tick(10.0, limit_up=110.0)])
    assert out[0].kind == "limit" and "涨停" in out[0].say


def test_switch_persona_live():
    w, _ = watcher("guardian")
    assert w.check([tick(1.2)]) == []
    w.set_persona(persona.load("flash"))
    assert w.check([tick(1.2)])[0].level == 2


def test_message_matches_protocol():
    w, _ = watcher()
    msg = w.check([tick(3.1)])[0].message(clock="10:35", persona="guardian")
    assert msg["t"] == "alert" and set(msg) >= {"code", "name", "level", "kind", "pct", "clock", "say", "persona"}
