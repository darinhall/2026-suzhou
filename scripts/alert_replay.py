"""用真实数据（PandaAI，最近一个交易日的 5 分钟线）把每个人格的提醒阶梯跑一遍，打印每次提醒。

    uv run python scripts/alert_replay.py              # 全部人格
    uv run python scripts/alert_replay.py flash        # 只看一个

时间按"回放 1 秒一根 K 线"算冷却（和展台默认 speed 一样）。用来调 brain/personas.json 的阈值。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "data")]

from brain import persona  # noqa: E402
from brain.alerts import AlertWatcher, Tick  # noqa: E402
from watch import TIMES, load_day, stock_state  # noqa: E402

SPEED = 1.0   # 秒 / 根


def ticks_at(day: dict, i: int) -> list[Tick]:
    out = []
    for k in range(len(day["stocks"])):
        s = stock_state(day, k, i)
        out.append(Tick(s["code"], s["name"], s["pct"], s["price"], s["_series"], s.get("vol_ratio"), s.get("limit_up"), s.get("limit_down")))
    return out


def run(day: dict, pid: str) -> list[tuple[str, object]]:
    clk = [0.0]
    w = AlertWatcher(persona.load(pid), clock=lambda: clk[0])
    log = []
    for i in range(len(TIMES)):
        clk[0] = i * SPEED
        for a in w.check(ticks_at(day, i)):
            log.append((TIMES[i], a))
    return log


def main() -> None:
    day = load_day()
    print("数据：", day.get("date"), "·", " ".join(f"{s['name']}" for s in day["stocks"]))
    for i in (len(TIMES) - 1,):
        print("收盘：", "  ".join(f"{t.name} {t.pct:+.2f}%" for t in ticks_at(day, i)))
    for pid in sys.argv[1:] or persona.ids():
        log = run(day, pid)
        big = sum(a.level >= 2 for _, a in log)
        print(f"\n== {pid} {persona.load(pid)['name']}：{len(log)} 次（≥2 级 {big} 次）")
        for clock, a in log:
            print(f"  {clock}  L{a.level} {a.kind:<6} {a.say}")


if __name__ == "__main__":
    main()
