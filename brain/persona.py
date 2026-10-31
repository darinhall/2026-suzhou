"""读 brain/personas.json（T16）。不认识的 id 退回默认人格；缺的字段用默认人格的值补上。"""

from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name("personas.json")


def _table() -> tuple[str, dict[str, dict]]:
    raw = json.loads(PATH.read_text())
    return raw["default"], {p["id"]: p for p in raw["personas"]}


def ids() -> list[str]:
    return list(_table()[1])


def load(pid: str | None = None) -> dict:
    """返回一个完整的人格 dict（每次读文件：改了 JSON 不用重启中枢）。"""
    default, table = _table()
    base = table[default]
    p = table.get(pid, base)
    out = {**base, **p}
    for key in ("alerts", "brief", "guard", "voice"):   # 子块逐字段补默认值
        out[key] = {**base.get(key, {}), **p.get(key, {})}
    return out
