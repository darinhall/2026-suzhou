"""股票名称 ↔ 代码：给"自选"设置用（按名字或代码搜）。

名单来源：PandaAI 全市场日线（不传 symbol，一次 2–3 秒，每行带 name），整理成 {代码: 名称} 存进 data/cache/names.json（已 gitignore）。
没有缓存、也联不了 PandaAI 时，退回内置的一小份常见股票，搜不到就是搜不到，不会编名字。
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CACHE = HERE / "cache" / "names.json"

BUILTIN = {
    "300750": "宁德时代", "600519": "贵州茅台", "002594": "比亚迪", "600036": "招商银行", "688981": "中芯国际",
    "601318": "中国平安", "000858": "五粮液", "601012": "隆基绿能", "002415": "海康威视", "300059": "东方财富",
    "600900": "长江电力", "601899": "紫金矿业", "000333": "美的集团", "002475": "立讯精密", "600276": "恒瑞医药",
    "601166": "兴业银行", "000001": "平安银行", "600030": "中信证券", "002230": "科大讯飞", "300124": "汇川技术",
}
_mem: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _mem
    if _mem is None:
        try:
            _mem = json.loads(CACHE.read_text())
        except (OSError, ValueError):
            _mem = {}
        _mem = {**BUILTIN, **_mem}
    return _mem


def refresh() -> int:
    """从 PandaAI 全市场日线更新名单，返回股票数。要联网 + 账号；失败抛错，调用方记日志。"""
    import panda_data
    from panda_client import PandaClient, login

    login()
    last = PandaClient().last_trade_date()
    df = panda_data.get_stock_daily(start_date=last, end_date=last)
    if "name" not in df.columns or len(df) < 1000:
        raise RuntimeError("全市场日线没有 name 列或太少")
    names = {str(s)[:6]: str(n) for s, n in zip(df["symbol"], df["name"]) if str(s)[:6].isdigit()}
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(names, ensure_ascii=False))
    global _mem
    _mem = {**BUILTIN, **names}
    return len(names)


def lookup(code: str) -> str | None:
    return _load().get(code)


def search(q: str, limit: int = 8) -> list[dict]:
    """按代码前缀或名称包含搜索；名称开头匹配的排前面。"""
    q = q.strip()
    if not q:
        return []
    names = _load()
    hits = []
    for code, name in names.items():
        if re.fullmatch(r"\d+", q):
            if code.startswith(q):
                hits.append((0, code, name))
        elif name.startswith(q):
            hits.append((0, code, name))
        elif q in name:
            hits.append((1, code, name))
    hits.sort()
    return [{"code": c, "name": n} for _, c, n in hits[:limit]]


def learn(code: str, name: str) -> None:
    """行情里带来的名字记进内存名单（不写盘）。"""
    if code and name and name != code:
        _load()[code] = name


def known_count() -> int:
    return len(_load())


if __name__ == "__main__":
    print(len(_load()), search(sys.argv[1] if len(sys.argv) > 1 else "宁德"))
