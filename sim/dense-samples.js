// 没有真数据时（按"状态"按钮、离线、卡片是空的）信息屏用的示例卡片：形状和协议里的 v2 card 一样，但一律带 mode:"sample" / sample 标记，
// 屏幕上会打「示例」。数据取自 dense-data.js（原型页的合成数据）。
import { WATCH, INDICES, BREADTH, WEATHER, FX, OVERNIGHT, EVENTS, BRIEF } from './dense-data.js';

const half = (a) => a.filter((_, i) => i % 2 === 1);   // 48 根 → 24 根

export const SAMPLES = {
  watch: {
    title: '自选', asof: '示例数据', mode: 'sample',
    indices: INDICES.map((x) => ({ name: x.name, value: x.val, pct: x.pct, amount: x.amt })),
    rows: WATCH.map((s) => ({ name: s.name, code: s.code, pct: s.pct, price: s.price, prev_close: s.pre, open: s.open, high: s.high, low: s.low,
      amount: s.amt, amp: s.amp, vol_ratio: s.vr, spark: [s.pre, ...half(s.spark).slice(0, 23)], ...(s.alert ? { alert: true } : {}) })),
  },
  mkt: (() => {
    const s = WATCH[0];
    return { name: s.name, code: s.code, pct: s.pct, price: s.price, prev_close: s.pre, open: s.open, high: s.high, low: s.low, volume: +(s.vol / 100).toFixed(1),
      amount: s.amt, amp: s.amp, limit_up: s.lu, limit_down: s.ld, vol_ratio: s.vr, range20: { lo: s.r20[0], hi: s.r20[1] }, spark: s.spark, mode: 'sample', asof: '示例数据' };
  })(),
  today: {
    month: 10, day: 31, weekday: '周六', market: '休市', city: WEATHER.city, lunar: '九月廿二', next_open: '11-03 09:30', open_in: '2 天 2 小时',
    last_idx: { name: '上证', value: INDICES[0].val, pct: INDICES[0].pct, sample: true },
    wx: { temp: WEATHER.temp, text: WEATHER.text, feels: WEATHER.feels, humidity: WEATHER.humidity, hi: WEATHER.hi, lo: WEATHER.lo, rain: WEATHER.rain,
      wind: `${WEATHER.windDir} ${WEATHER.wind} 级`, aqi: WEATHER.aqi, aqi_text: '良', uv: WEATHER.uv, sunrise: WEATHER.sunrise, sunset: WEATHER.sunset,
      tmr_text: WEATHER.tmr.text, tmr_lo: WEATHER.tmr.lo, tmr_hi: WEATHER.tmr.hi, hourly: WEATHER.hourly },
    events: EVENTS.map((e) => ({ time: e.time, title: e.title })),
    fx: FX.map((x) => ({ pair: x.pair, rate: x.val * (x.scale || 1), pct: x.chg, ...(x.scale ? { per: x.scale } : {}) })),
    brief: BRIEF, overnight: OVERNIGHT, sample: { events: true, overnight: true },
  },
  sky: {
    city: WEATHER.city, time: WEATHER.time, temp: WEATHER.temp, text: WEATHER.text, feels: WEATHER.feels, humidity: WEATHER.humidity, wind: WEATHER.wind, wind_dir: WEATHER.windDir,
    hi: WEATHER.hi, lo: WEATHER.lo, tmr_text: WEATHER.tmr.text, tmr_hi: WEATHER.tmr.hi, tmr_lo: WEATHER.tmr.lo, tmr_rain: WEATHER.tmr.rain, advice: WEATHER.advice,
    uv: WEATHER.uv, sunrise: WEATHER.sunrise, sunset: WEATHER.sunset, hourly: WEATHER.hourly, rain_hourly: WEATHER.rainHourly, aqi: WEATHER.aqi, aqi_text: '良', pm25: WEATHER.pm25,
  },
  weather: { time: '15:00', word: '偏冷', up: BREADTH.up, down: BREADTH.down, flat: BREADTH.flat, limit_up_n: BREADTH.lu, limit_down_n: BREADTH.ld, mode: 'sample' },
};
