// 密度原型用的假数据（原型页顶上有"原型 · 合成数据"横幅）。
// 每个块带 smp 标记：true = 现在没有任何数据源能提供，屏幕上要打"示例"角标；false = 产品里是真数据（PandaAI / Open-Meteo / Frankfurter）。
// 宁德时代那一行的 OHLC / 昨收 / 成交量 / 成交额 / 涨跌停价是 PandaAI 日线的真实返回值（2025-10-31 那根日线），走势是原型里合成的。

function rng(seed) { let s = seed; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

// 48 根 5 分钟收盘价（09:35–15:00），从开盘走到收盘，经过最高 / 最低
function series(open, high, low, close, seed, n = 48) {
  const r = rng(seed), pts = [];
  const hiAt = Math.floor(n * (0.12 + r() * 0.2)), loAt = Math.floor(n * (0.55 + r() * 0.3));
  const anchors = [[0, open], [hiAt, high], [loAt, low], [n - 1, close]].sort((a, b) => a[0] - b[0]);
  for (let i = 0; i < n; i++) {
    let k = 0;
    while (k < anchors.length - 2 && i > anchors[k + 1][0]) k++;
    const [i0, v0] = anchors[k], [i1, v1] = anchors[k + 1];
    const t = i1 === i0 ? 1 : (i - i0) / (i1 - i0);
    const jitter = (r() - 0.5) * (high - low) * 0.06 * Math.sin(Math.PI * Math.min(1, Math.max(0, t)));
    pts.push(+(v0 + (v1 - v0) * t + jitter).toFixed(2));
  }
  pts[0] = open; pts[n - 1] = close;
  return pts.map((v) => Math.min(high, Math.max(low, v)));
}

const stock = (name, code, o, h, l, c, pre, vol, amt, seed, extra = {}) => ({
  name, code, open: o, high: h, low: l, price: c, pre, vol, amt, spark: series(o, h, l, c, seed),
  pct: +((c / pre - 1) * 100).toFixed(2), chg: +(c - pre).toFixed(2), amp: +(((h - l) / pre) * 100).toFixed(2), ...extra,
});

export const WATCH = [
  stock('宁德时代', '300750', 398.0, 406.8, 388.2, 388.77, 398.29, 3405, 135.2, 11, { vr: 1.4, lu: 477.95, ld: 318.63, r20: [371.2, 432.5] }),
  stock('中芯国际', '688981', 98.4, 105.9, 98.1, 104.7, 100.1, 8120, 83.5, 22, { vr: 2.3, lu: 120.12, ld: 80.08, r20: [88.4, 110.2], alert: true }),
  stock('贵州茅台', '600519', 1462.0, 1476.5, 1455.0, 1468.0, 1462.9, 218, 31.9, 33, { vr: 0.8, lu: 1609.19, ld: 1316.61, r20: [1431.0, 1510.0] }),
  stock('比亚迪', '002594', 112.4, 113.9, 110.6, 111.2, 112.5, 1530, 17.1, 44, { vr: 1.0, lu: 123.75, ld: 101.25, r20: [104.8, 119.9] }),
  stock('招商银行', '600036', 43.1, 43.9, 43.0, 43.68, 43.29, 1280, 5.6, 55, { vr: 1.1, lu: 47.62, ld: 38.96, r20: [41.2, 44.8] }),
];

export const INDICES = [
  { name: '上证', full: '上证指数', val: 3296.46, pct: 0.42, amt: 5821 },
  { name: '深证', full: '深证成指', val: 10512.3, pct: 0.61, amt: 7344 },
  { name: '创业板', full: '创业板指', val: 2105.8, pct: 1.12, amt: 3260 },
  { name: '沪深300', full: '沪深300', val: 3891.2, pct: 0.38, amt: 2915 },
];

// 市场宽度：涨跌家数 / 涨停跌停。现在没有数据源（PandaAI 的 websocket 地址还没拿到），所以示例
export const BREADTH = { up: 3182, down: 1904, flat: 210, lu: 61, ld: 7, smp: true };

export const WEATHER = {
  city: '苏州', time: '07:30', temp: 16, feels: 15, text: '雾', humidity: 88, wind: 3, windDir: '东北', aqi: 72, pm25: 29, uv: 3,
  hi: 23, lo: 14, rain: 20, sunrise: '06:21', sunset: '17:03', advice: '早晚有雾，开车慢一点',
  tmr: { text: '小阵雨', hi: 26, lo: 16, rain: 70 },
  hourly: [14, 14, 14, 13, 13, 14, 14, 15, 16, 18, 19, 21, 22, 23, 23, 22, 21, 19, 18, 17, 16, 16, 15, 15],
  rainHourly: [5, 5, 5, 5, 10, 10, 10, 15, 15, 10, 10, 10, 15, 20, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65],
};

export const FX = [
  { pair: 'USD/CNY', val: 7.1182, chg: -0.12 },
  { pair: 'EUR/CNY', val: 7.7064, chg: 0.08 },
  { pair: 'JPY/CNY', val: 0.0471, chg: -0.21, scale: 100 },   // 每 100 日元
];

export const OVERNIGHT = [{ name: '纳指', pct: 0.84 }, { name: '标普', pct: 0.52 }];   // 隔夜外盘：没有数据源，示例

export const EVENTS = [   // 日程：现在读 data/schedule.json（示例），以后接飞书日历
  { time: '09:30', title: '晨会 · 产品组', where: '3 号会议室' },
  { time: '15:00', title: '产品评审会', where: '线上' },
  { time: '19:30', title: '黑客松彩排', where: '路演厅' },
];

export const BRIEF = '盘前：自选整体偏强，中芯国际放量 +4.6%；白天有雾，出门带伞（明天有雨）。';
