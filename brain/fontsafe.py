"""板子的中文字体只有 ASCII + 常用标点 + GB2312 一级汉字（esp32s3/tools/make_vlw.py），别的字画出来是空白。
发给板子的卡片文字先过一遍 safe()：能换成相近字符的换掉，换不了的去掉。
"""

from __future__ import annotations

PUNCT = set("，。！？：；、（）“”‘’—…·¥％▲▼→←↑↓①②③℃°×÷±≈＋－")
REPLACE = {"　": "  ", "｜": " / ", "|": " / ", "～": "~", "【": "[", "】": "]", "《": "“", "》": "”",
           "「": "“", "」": "”", "！": "！", "＝": "=", "：": "：", "／": "/", "＞": ">", "＜": "<"}


def ok(ch: str) -> bool:
    if 0x20 <= ord(ch) < 0x7F or ch in PUNCT:
        return True
    try:
        b = ch.encode("gb2312")
    except UnicodeEncodeError:
        return False
    return len(b) == 2 and 0xB0 <= b[0] <= 0xD7   # 一级汉字区


def safe(text: str) -> str:
    out = []
    for ch in text:
        if ok(ch):
            out.append(ch)
        elif ch in REPLACE:
            out.append(REPLACE[ch])
        elif ch in "\n\t":
            out.append(" ")
    return "".join(out)


def card(c):
    """卡片里所有字符串都过一遍（递归）。"""
    if isinstance(c, str):
        return safe(c)
    if isinstance(c, dict):
        return {k: card(v) for k, v in c.items()}
    if isinstance(c, list):
        return [card(v) for v in c]
    return c
