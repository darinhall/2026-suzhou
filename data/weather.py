"""天气 + 空气质量：Open-Meteo（免费、不用 key；2026-10-31 在苏州实测 1.3–1.5 秒）。

    python3 data/weather.py            # 打印苏州现在的天气

只用标准库。返回的 dict 字段已经是机器人屏幕要的样子（中文天气词、风力级、一句建议）。
来源：
- 天气 https://api.open-meteo.com/v1/forecast  （current / daily；weather_code 是 WMO 天气代码）
- 空气 https://air-quality-api.open-meteo.com/v1/air-quality  （CAMS 模型数据，不是地面监测站；正式上线要换中国环境监测总站）

空气质量说明：接口给的 us_aqi 是 PM 的 **24 小时滑动平均**换算的美标指数（实测：过去 24 小时 PM2.5 均值 153 →
美标 229，和接口的 228 一致），所以夜里霾重、中午已经好转时，us_aqi 仍然很高。屏幕上两个都给：
24 小时均值（标题）和此刻（好转 / 加重）。文字分段用国标 GB 3095 的 PM2.5 浓度（µg/m³）：35 / 75 / 115 / 150 / 250。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

# 苏州工业园区（纳米大学科技园附近）。要换城市只改这里。
SUZHOU = {"city": "苏州", "lat": 31.27, "lon": 120.74}

# WMO weather_code → 中文（https://open-meteo.com/en/docs 里的表）
WMO = {
    0: "晴", 1: "大部晴", 2: "多云", 3: "阴", 45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "小阵雪", 86: "大阵雪",
    95: "雷暴", 96: "雷暴冰雹", 99: "强雷暴冰雹",
}
RAINY = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def wind_level(kmh: float) -> int:
    """风速 km/h → 风力等级（蒲福风级，国内天气预报用的「几级风」）。"""
    for level, upper in enumerate([1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]):
        if kmh < upper:
            return level
    return 12


def pm25_text(ug: float | None) -> str:
    """PM2.5 浓度 → 国标分段的中文词。"""
    if ug is None:
        return "—"
    for upper, word in [(35, "优"), (75, "良"), (115, "轻度污染"), (150, "中度污染"), (250, "重度污染")]:
        if ug <= upper:
            return word
    return "严重污染"


def air_trend(now_ug: float | None, avg_ug: float | None) -> str:
    """此刻相对 24 小时均值：好转中 / 加重中 / 持平。"""
    if now_ug is None or not avg_ug:
        return "—"
    return "好转中" if now_ug < avg_ug * 0.6 else "加重中" if now_ug > avg_ug * 1.4 else "持平"


def advice(now: dict, today: dict) -> str:
    """一句话建议：最要紧的一条。机器人早上能直接说。"""
    if today["rain_pct"] is not None and today["rain_pct"] >= 50 or now["code"] in RAINY:
        return "今天有雨，记得带伞"
    if today["high"] is not None and today["low"] is not None and today["high"] - today["low"] >= 10:
        return "早晚温差大，带件外套"
    if today["low"] is not None and today["low"] <= 8:
        return "天冷，多穿点"
    if today["high"] is not None and today["high"] >= 32:
        return "天热，多喝水"
    if now["pm25"] is not None and now["pm25"] > 115:
        return "空气不好，少开窗"
    if now["pm25_24h"] is not None and now["pm25_24h"] > 115 and now["air_trend"] == "好转中":
        return "夜里有霾，现在在好转"
    return "天气不错"


def _get(url: str, params: dict, timeout: float = 10) -> dict:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=timeout) as r:
        return json.load(r)


def get_weather(place: dict = SUZHOU) -> dict:
    """现在 + 今天 + 明天 + 空气。网络失败会抛 URLError / TimeoutError，调用方决定怎么降级。"""
    w = _get("https://api.open-meteo.com/v1/forecast", {
        "latitude": place["lat"], "longitude": place["lon"], "timezone": "Asia/Shanghai", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
    })
    try:   # 空气质量单独一个接口，挂了不影响天气
        a = _get("https://air-quality-api.open-meteo.com/v1/air-quality", {
            "latitude": place["lat"], "longitude": place["lon"], "timezone": "Asia/Shanghai",
            "current": "us_aqi,pm2_5", "hourly": "pm2_5", "past_hours": 24, "forecast_hours": 1,
        })
        hours = [v for v in a["hourly"]["pm2_5"][:24] if v is not None]   # 过去 24 个整点
        a = {**a["current"], "pm25_24h": sum(hours) / len(hours) if hours else None}
    except Exception:
        a = {}

    cur, d = w["current"], w["daily"]
    day = lambda i: {   # noqa: E731
        "date": d["time"][i], "high": d["temperature_2m_max"][i], "low": d["temperature_2m_min"][i],
        "rain_pct": d["precipitation_probability_max"][i], "code": d["weather_code"][i],
        "text": WMO.get(d["weather_code"][i], "—"),
    }
    now = {
        "city": place["city"], "time": cur["time"], "temp": cur["temperature_2m"], "feels": cur["apparent_temperature"],
        "humidity": cur["relative_humidity_2m"], "code": cur["weather_code"], "text": WMO.get(cur["weather_code"], "—"),
        "wind_level": wind_level(cur["wind_speed_10m"]), "raining": cur["precipitation"] > 0,
        "pm25": a.get("pm2_5"), "pm25_24h": round(a["pm25_24h"], 1) if a.get("pm25_24h") is not None else None,
        "us_aqi": a.get("us_aqi"),   # 24 小时均值换算的美标指数，仅供参考
    }
    now["air_text"] = pm25_text(now["pm25_24h"])          # 标题：24 小时均值的级别
    now["air_now_text"] = pm25_text(now["pm25"])          # 此刻的级别
    now["air_trend"] = air_trend(now["pm25"], now["pm25_24h"])
    today, tomorrow = day(0), day(1)
    now["advice"] = advice(now, today)
    return {"now": now, "today": today, "tomorrow": tomorrow, "source": "Open-Meteo"}


if __name__ == "__main__":
    r = get_weather()
    n, t, m = r["now"], r["today"], r["tomorrow"]
    print(f"{n['city']} {n['time']}  {n['text']} {n['temp']}°C（体感 {n['feels']}°）  湿度 {n['humidity']}%  {n['wind_level']} 级风")
    print(f"空气：{n['air_text']}（24 小时均值 PM2.5 {n['pm25_24h']}），此刻 {n['air_now_text']}（{n['pm25']} µg/m³）· {n['air_trend']}")
    print(f"今天 {t['text']} {t['low']}~{t['high']}°C 降水概率 {t['rain_pct']}%   明天 {m['text']} {m['low']}~{m['high']}°C 降水概率 {m['rain_pct']}%")
    print(f"建议：{n['advice']}")
