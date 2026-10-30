"""T5 串口探测：看板子上有没有在跑固件、波特率是多少。

    uv run --with pyserial python t5/serial_probe.py            # 依次试 115200 / 460800 / 921600
    uv run --with pyserial python t5/serial_probe.py monitor     # 一直显示日志（默认 460800），Ctrl-C 退出
    uv run --with pyserial python t5/serial_probe.py monitor --seconds 15   # 只录 15 秒（用 ! 运行时用这个）

probe 模式：每个波特率先等你按回车，然后马上按一下板子上的 RESET，脚本记录 10 秒。
每个波特率存两个文件到 t5/logs/：.bin（原始字节）和 .txt（能读的文字）。最后给每个波特率一个判断。

打开串口时把 DTR / RTS 都设成"不激活"，避免某些自动下载电路把芯片按住在复位或下载模式。
"""

import argparse
import pathlib
import sys
import time

import serial

DEFAULT_PORT = "/dev/cu.usbserial-210"
BAUDS = [115200, 460800, 921600]
LOGS = pathlib.Path(__file__).parent / "logs"


def open_port(port, baud):
    s = serial.Serial()
    s.port = port
    s.baudrate = baud
    s.timeout = 0.1
    s.dtr = False
    s.rts = False
    s.open()
    return s


def verdict(data: bytes) -> str:
    if not data:
        return "静默：一个字节都没有"
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    ratio = printable / len(data)
    if ratio > 0.9:
        return f"可读文字（{ratio:.0%} 可打印）→ 波特率对了"
    if ratio > 0.6:
        return f"大部分可读（{ratio:.0%}）→ 可能对，也可能混着二进制"
    return f"乱码（只有 {ratio:.0%} 可打印）→ 有信号，但波特率不对"


def probe(port, seconds):
    LOGS.mkdir(exist_ok=True)
    stamp = time.strftime("%H%M%S")
    results = []
    interactive = sys.stdin.isatty()
    if not interactive:
        # 在 Claude Code 里用 ! 运行时没有键盘输入：不等回车，三个波特率连着录，
        # 整个过程中每隔 3 秒左右按一次 RESET 就行
        print(f"非交互模式：连续记录 {len(BAUDS)} × {seconds} 秒，期间每隔约 3 秒按一次 RESET")
    for baud in BAUDS:
        if interactive:
            input(f"\n[{baud}] 按回车开始记录，然后马上按一下板子上的 RESET …")
        else:
            print(f"\n[{baud}] 开始记录")
        data = bytearray()
        with open_port(port, baud) as s:
            s.reset_input_buffer()
            end = time.time() + seconds
            while time.time() < end:
                chunk = s.read(4096)
                if chunk:
                    data += chunk
                    sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
                left = int(end - time.time()) + 1
                sys.stderr.write(f"\r  记录中… 还剩 {left:2d} 秒，已收到 {len(data)} 字节 ")
        sys.stderr.write("\n")
        base = LOGS / f"probe_{stamp}_{baud}"
        base.with_suffix(".bin").write_bytes(bytes(data))
        base.with_suffix(".txt").write_text(data.decode("utf-8", errors="replace"))
        results.append((baud, len(data), verdict(bytes(data)), base))

    print("\n==== 结果 ====")
    for baud, n, v, base in results:
        print(f"{baud:>7}  {n:>6} 字节  {v}")
    print(f"\n日志在 {LOGS}/probe_{stamp}_*")


def monitor(port, baud, seconds=0):
    """seconds=0 一直跑到 Ctrl-C；在 Claude Code 里用 ! 运行时要给一个秒数。同时存到 t5/logs/monitor_*.txt"""
    LOGS.mkdir(exist_ok=True)
    out = LOGS / f"monitor_{time.strftime('%H%M%S')}_{baud}.txt"
    print(f"监听 {port} @ {baud}" + (f"，{seconds} 秒" if seconds else "，Ctrl-C 退出") + f" → {out}")
    end = time.time() + seconds if seconds else None
    with open_port(port, baud) as s, open(out, "wb") as f:
        try:
            while end is None or time.time() < end:
                chunk = s.read(4096)
                if chunk:
                    f.write(chunk)
                    sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="probe", choices=["probe", "monitor"])
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--seconds", type=int, default=None, help="probe 每个波特率的秒数（默认 10）；monitor 的总秒数（默认一直跑）")
    ap.add_argument("--baud", type=int, default=460800, help="monitor 模式用")
    a = ap.parse_args()
    if a.mode == "probe":
        probe(a.port, a.seconds or 10)
    else:
        monitor(a.port, a.baud, a.seconds or 0)
