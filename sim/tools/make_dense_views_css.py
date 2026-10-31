"""sim/dense.css（原型页的样式）→ sim/dense-views.css（face.js 在"紧凑 / 专业"模式下用的样式）。

    python3 sim/tools/make_dense_views_css.py

两处改动：
1. 选择器都限定在 .screen 里面的 .dv 容器下，类名统一加 dv- 前缀（dense-views.js 的 ns() 同样处理），不和 screen.css 的 .live / .dots / .row 等撞名；
2. 颜色不再自己定义，用 screen.css 的 token 做别名（米黄 / 深色主题自动跟着变），尺寸 l = 480×320、s = 320×240 仍然按 .screen 的 data-size。
"""
import pathlib, re

here = pathlib.Path(__file__).resolve().parent.parent
src = (here / "dense.css").read_text()
src = src[src.index("/* 字号"):]
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)

SIZE = {"l": ".screen:not([data-size=\"s\"]) .dv", "s": ".screen[data-size=\"s\"] .dv"}

def cls_prefix(s):
    return re.sub(r"\.([A-Za-z][\w-]*)", r".dv-\1", s)

def convert(sel):
    sel = sel.strip()
    m = re.match(r'\.ds\[data-size="(l|s)"\](.*)$', sel)
    if m:
        return SIZE[m.group(1)] + cls_prefix(m.group(2))
    m = re.match(r"\.ds(\[.*)$", sel)
    if m:
        return ".dv" + cls_prefix(m.group(1))
    return ".dv " + cls_prefix(sel)

out = []
for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src):
    sels = [convert(s) for s in m.group(1).split(",") if s.strip()]
    out.append(",\n".join(sels) + " {" + " ".join(m.group(2).split()) + " }")

head = """/* 由 sim/tools/make_dense_views_css.py 从 dense.css 生成，不要手改。 */
/* 容器：铺满 .screen，颜色用 screen.css 的 token 做别名，所以跟随米黄 / 深色主题 */
.dv {
  position: absolute; inset: 0; display: flex; flex-direction: column; overflow: hidden;
  --sunk: var(--surface-sunk); --mute: var(--ink-muted); --faint: var(--ink-faint);
  --on-card-mute: var(--on-card-muted); --up-c: var(--up-on-card); --down-c: var(--down-on-card);
  font-size: var(--fd); line-height: 1.2; font-variant-numeric: tabular-nums; color: var(--ink); font-family: var(--sans);
}
.dv, .dv * { box-sizing: border-box; }
"""
(here / "dense-views.css").write_text(head + "\n".join(out) + "\n")
print(f"dense-views.css: {len(out)} 条规则")
