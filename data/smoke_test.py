"""PandaAI 连通性测试：登录 → 最新交易日 → 宁德时代日线 → 沪深300 日线 → 分钟线。

    uv run --python 3.12 --with panda-data==1.0.5 python data/smoke_test.py

每一步单独 try，打印成功 / 失败和返回的列名，方便看我们的账号开通了哪些模块。
不会打印账号和 token。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from panda_client import PandaClient, login   # noqa: E402


def step(name, fn):
    try:
        out = fn()
    except Exception as e:   # SDK 错误码见交接文档 §7：200002/200004 token、200005 密码、200101/200103 没权限
        print(f"✗ {name}: {type(e).__name__}: {e}")
        return None
    if hasattr(out, "columns"):
        print(f"✓ {name}: {len(out)} 行 · 列 = {list(out.columns)}")
        print(out.tail(3).to_string(max_cols=12), "\n")
    else:
        print(f"✓ {name}: {out!r}")
    return out


login()
print("✓ 登录成功\n")
c = PandaClient()
last = step("最新交易日", c.last_trade_date) or "20261030"
step("宁德时代 300750 日线（近 1 个月）", lambda: c.get_bars("a", ["300750"], "20261001", last))
step("沪深300 000300 日线（近 1 个月）", lambda: c.get_bars("index", ["000300"], "20261001", last))
step("螺纹钢主力 RB_DOMINANT 期货日线", lambda: c.get_bars("future", ["RB"], "20261020", last))
step("宁德时代 5 分钟线（最近一个交易日）", lambda: c.get_minute("a", ["300750"], last, last, frequency="5m"))
