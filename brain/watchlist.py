"""T18：用语音增删自选。纯函数，中枢拿结果去调 ModeEngine.profile_set 保存。

    apply("add", "002594", ["300750", "688981"]) → (["300750", "688981", "002594"], "ok")

result：ok / exists（已经在）/ missing（本来就没有）/ full（满 8 只）/ unknown（认不出股票）/ empty（至少留一只）
"""

from __future__ import annotations

MAX = 8


def apply(op: str, code: str | None, current: list[str], max_n: int = MAX) -> tuple[list[str], str]:
    cur = list(current)
    if not code:
        return cur, "unknown"
    c = code
    if op == "add":
        if c in cur:
            return cur, "exists"
        if len(cur) >= max_n:
            return cur, "full"
        return cur + [c], "ok"
    if op == "remove":
        if c not in cur:
            return cur, "missing"
        if len(cur) <= 1:
            return cur, "empty"
        return [x for x in cur if x != c], "ok"
    raise ValueError(op)
