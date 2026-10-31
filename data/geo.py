"""城市名 → 经纬度：Open-Meteo 地名搜索（免费、不要 key），结果存进 data/cache/geo.json，同一个城市只查一次。

    python3 data/geo.py 北京
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache" / "geo.json"
BUILTIN = {   # 常用城市先内置，现场没网也能用
    "苏州": (31.27, 120.74), "北京": (39.90, 116.40), "上海": (31.23, 121.47), "深圳": (22.54, 114.06),
    "广州": (23.13, 113.26), "杭州": (30.27, 120.15), "南京": (32.06, 118.80), "成都": (30.57, 104.07),
}


def _cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def geocode(name: str, timeout: float = 8) -> dict:
    """返回 {"name","lat","lon"}。查不到抛 LookupError；没网抛 URLError / TimeoutError。"""
    name = name.strip()
    if not name or len(name) > 20:
        raise LookupError("城市名为空或太长")
    if name in BUILTIN:
        lat, lon = BUILTIN[name]
        return {"name": name, "lat": lat, "lon": lon}
    hit = _cache().get(name)
    if hit:
        return hit
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": name, "count": 1, "language": "zh"})
    with urllib.request.urlopen(url, timeout=timeout) as r:
        res = (json.load(r).get("results") or [])
    if not res:
        raise LookupError(f"找不到城市：{name}")
    out = {"name": name, "lat": round(res[0]["latitude"], 3), "lon": round(res[0]["longitude"], 3)}
    cache = _cache()
    cache[name] = out
    try:
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    except OSError:
        pass
    return out


if __name__ == "__main__":
    print(geocode(sys.argv[1] if len(sys.argv) > 1 else "北京"))
