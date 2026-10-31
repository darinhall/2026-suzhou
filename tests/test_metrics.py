"""T02：brain/metrics.py 的接口和数值。"""

import math

import pytest

m = pytest.importorskip("brain.metrics")


def test_pct_return():
    assert m.pct_return([100, 110, 99, 121]) == pytest.approx(21.0)


def test_day_change():
    assert m.day_change(102, 100) == pytest.approx(2.0)


def test_moving_average():
    assert m.moving_average([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_max_drawdown():
    assert m.max_drawdown([100, 120, 90, 130]) == pytest.approx(-25.0)
    assert m.max_drawdown([1, 2, 3]) == pytest.approx(0.0)


def test_volatility():
    # 日收益 +10%、-10%：样本标准差 0.1414…
    assert m.volatility([100, 110, 99], annualize=False) == pytest.approx(14.1421, abs=1e-3)
    assert m.volatility([100, 110, 99]) == pytest.approx(14.1421 * math.sqrt(252), abs=1e-2)


def test_relative_and_correlation():
    a = [100, 110, 99, 121]
    assert m.relative([100, 110], [100, 105]) == pytest.approx(5.0)
    assert m.correlation(a, [x / 2 for x in a]) == pytest.approx(1.0)


def test_normalize():
    assert m.normalize([50, 55]) == pytest.approx([100, 110])


def test_accepts_series():
    pd = pytest.importorskip("pandas")
    assert m.pct_return(pd.Series([100, 110])) == pytest.approx(10.0)


@pytest.mark.parametrize("fn", ["pct_return", "volatility", "max_drawdown", "normalize"])
def test_too_short(fn):
    with pytest.raises(ValueError):
        getattr(m, fn)([100])
