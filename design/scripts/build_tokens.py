#!/usr/bin/env python3
"""tokens.json -> tokens.css (web/sim) + deskbot_tokens.h (Arduino/LVGL).
Run from repo root:  python3 design/scripts/build_tokens.py"""
import json, pathlib, re
D = pathlib.Path(__file__).resolve().parent.parent
t = json.loads((D / "tokens.json").read_text())
themes = [th["id"] for th in t["color"]["themes"]]

def val(tok, th):
    v = tok["value"]
    return v if isinstance(v, str) else v.get(th, v[themes[0]])

# ---- CSS
css = ["/* DeskBot — generated from tokens.json */"]
for i, th in enumerate(themes):
    sel = f':root, [data-theme="{th}"]' if i == 0 else f'[data-theme="{th}"]'
    lines = [f"  --{k['name']}: {val(k, th)};" for k in t["color"]["tokens"] + t.get("shadow", {}).get("tokens", [])]
    css.append(sel + " {\n" + "\n".join(lines) + "\n}")
root = [f"  --{k['name']}: {k['value']};" for fam in ("spacing", "radius") for k in t[fam]["tokens"]]
root += [f"  --font-{k}: {v};" for k, v in t["type"]["families"].items()]
css.append(":root {\n" + "\n".join(root) + "\n}")
for g in t["type"]["groups"]:
    for s in g["styles"]:
        fam = s.get("family", g["family"])
        lh = s["lineHeight"]
        props = [f"font-family: var(--font-{fam})", f"font-size: {s['fontSize']}", f"line-height: {lh}", f"font-weight: {s['fontWeight']}"]
        if "letterSpacing" in s: props.append(f"letter-spacing: {s['letterSpacing']}")
        css.append(f".{s['name']} {{ " + "; ".join(props) + "; }")
(D / "tokens.css").write_text("\n".join(css) + "\n")

# ---- C header for LVGL (lv_color_hex takes 0xRRGGBB)
cid = lambda n: re.sub(r"[^A-Za-z0-9]", "_", n).upper()
h = ["// DeskBot — generated from design/tokens.json. Do not edit by hand.", "#pragma once", ""]
for th in themes:
    h.append(f"// ---- colors: {th}")
    for k in t["color"]["tokens"]:
        hexv = val(k, th).lstrip("#")[:6]
        h.append(f"#define DB_{th.upper()}_{cid(k['name'])} 0x{hexv}")
    h.append("")
h.append("// ---- spacing / radius (px)")
for fam in ("spacing", "radius"):
    for k in t[fam]["tokens"]:
        n = int(float(k["value"].rstrip("px")))
        h.append(f"#define DB_{cid(k['name'])} {min(n, 0x7FFF) if k['name'] != 'radius-pill' else 'LV_RADIUS_CIRCLE'}")
h.append("")
h.append("// ---- type sizes (px) — convert fonts at exactly these sizes with lv_font_conv")
for g in t["type"]["groups"]:
    for s in g["styles"]:
        h.append(f"#define DB_FONT_{cid(s['name'])}_SIZE {int(float(s['fontSize'].rstrip('px')))}  // {s.get('family', g['family'])} {s['fontWeight']}")
(D / "deskbot_tokens.h").write_text("\n".join(h) + "\n")
print("wrote design/tokens.css, design/deskbot_tokens.h")
