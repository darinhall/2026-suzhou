"""生成 TFT_eSPI 的 .vlw 平滑字体（含常用汉字），放进 esp32s3/bringup/data/，再 `pio run -t uploadfs` 传到板子的 LittleFS。

    uvx --python 3.12 --with pillow python esp32s3/tools/make_vlw.py <字体文件> <字号> <输出名>
    uvx --python 3.12 --with pillow python esp32s3/tools/make_vlw.py "/System/Library/Fonts/STHeiti Medium.ttc" 22 cjk22

字符集：ASCII + 常用标点 + GB2312 一级汉字（3755 个，覆盖日常 99% 以上）。
字体文件**不要进 git**（有授权问题），生成的 .vlw 也不进（见 .gitignore）。要分享给队友就用开源的思源黑体 Noto Sans SC（OFL）。
VLW 格式：6 个大端 uint32 的头 → 每个字 7 个 uint32 的信息表 → 所有字的 8 位灰度位图依次排列。
"""
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

font_path, size, name = sys.argv[1], int(sys.argv[2]), sys.argv[3]
font = ImageFont.truetype(font_path, size)

chars = {chr(c) for c in range(0x20, 0x7F)}
chars |= set("，。！？：；、（）“”‘’—…·¥％▲▼→←↑↓①②③℃°×÷±≈＋－")
for hi in range(0xB0, 0xD8):          # GB2312 一级汉字区
    for lo in range(0xA1, 0xFF):
        try:
            chars.add(bytes([hi, lo]).decode("gb2312"))
        except UnicodeDecodeError:
            pass
ascent, descent = font.getmetrics()

glyphs = []
for ch in sorted(chars):
    x0, y0, x1, y1 = font.getbbox(ch, anchor="ls")
    w, h = max(0, x1 - x0), max(0, y1 - y0)
    if w == 0 or h == 0:
        if ch == " ":
            glyphs.append((ord(ch), 0, 0, round(font.getlength(ch)), 0, 0, b""))
        continue
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((-x0, -y0), ch, font=font, fill=255, anchor="ls")
    glyphs.append((ord(ch), h, w, round(font.getlength(ch)), -y0, x0, img.tobytes()))

out = bytearray(struct.pack(">6I", len(glyphs), 11, size, 0, ascent, descent))
for u, h, w, adv, dy, dx, _ in glyphs:
    out += struct.pack(">7I", u, h, w, adv, dy & 0xFFFFFFFF, dx & 0xFFFFFFFF, 0)
for g in glyphs:
    out += g[6]

path = f"esp32s3/bringup/data/{name}.vlw"
open(path, "wb").write(out)
print(f"{path}: {len(glyphs)} 个字，{len(out)/1024:.0f} KB")
