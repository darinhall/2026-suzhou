"""T18：增删自选的规则（纯函数）。"""

import pytest

wl = pytest.importorskip("brain.watchlist")

BASE = ["300750", "688981", "600519", "002594", "600036"]


def test_add():
    codes, res = wl.apply("add", "601318", BASE)
    assert res == "ok" and codes == BASE + ["601318"]


def test_add_existing():
    codes, res = wl.apply("add", "002594", BASE)
    assert res == "exists" and codes == BASE


def test_add_full():
    full = BASE + ["601318", "000001", "600030"]
    codes, res = wl.apply("add", "000858", full)
    assert res == "full" and codes == full


def test_remove():
    codes, res = wl.apply("remove", "600036", BASE)
    assert res == "ok" and "600036" not in codes and len(codes) == 4


def test_remove_missing():
    assert wl.apply("remove", "601318", BASE)[1] == "missing"


def test_keep_at_least_one():
    codes, res = wl.apply("remove", "300750", ["300750"])
    assert res == "empty" and codes == ["300750"]


def test_unknown_code():
    assert wl.apply("add", None, BASE)[1] == "unknown"
