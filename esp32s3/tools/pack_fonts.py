"""把 bringup/data/*.vlw 打包成一个 fonts.bin（目录 + 各字体，64 KB 对齐），用 esptool 直接烧进 "fonts" 分区。
固件把这个分区 mmap 成内存里的数组，loadFont(数组) 不用读文件系统，切换字体快得多。

    python3 esp32s3/tools/pack_fonts.py                  # → esp32s3/bringup/fonts.bin
    uvx esptool --port /dev/cu.usbmodem101 write-flash 0x410000 esp32s3/bringup/fonts.bin
"""
import pathlib, struct

root = pathlib.Path(__file__).resolve().parent.parent / "bringup"
files = sorted((root / "data").glob("*.vlw"))
ALIGN = 0x10000
dir_size = ALIGN                       # 目录占第一个 64 KB
entries, blob, off = [], b"", dir_size
for f in files:
    data = f.read_bytes()
    entries.append((f.stem.encode()[:16].ljust(16, b"\0"), off, len(data)))
    pad = (-len(data)) % ALIGN
    blob += data + b"\0" * pad
    off += len(data) + pad
head = b"DBF1" + struct.pack("<I", len(entries)) + b"".join(n + struct.pack("<II", o, s) for n, o, s in entries)
(root / "fonts.bin").write_bytes(head.ljust(dir_size, b"\0") + blob)
print(f"fonts.bin: {len(entries)} 个字体，{off/1024/1024:.1f} MB；" + "、".join(f.stem for f in files))
