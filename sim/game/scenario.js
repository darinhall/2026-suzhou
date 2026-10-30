// 行情剧本：把一段日线变成游戏里的"关卡"（决策点）。
// 假数据和 Panda Data 真数据走同一个入口 fromBars(meta)，meta = {name, code, period, bars: [{date, close}]}。

function rng(seed) {
  return () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

// 示例行情：横盘 → 拉升 → 加速 → 跳水 → 继续跌 → 反弹 → 走平。只用于开发，界面上标"示例数据"。
export function fakeBars(seed = 7) {
  const segs = [[6, 0], [7, 0.022], [4, 0.014], [5, -0.035], [3, -0.02], [6, 0.02], [6, 0.002]];
  const r = rng(seed);
  const bars = [];
  let p = 100;
  for (const [n, drift] of segs) {
    for (let i = 0; i < n; i++) {
      p *= 1 + drift + (r() - 0.5) * 0.02;
      bars.push({ date: `第${bars.length + 1}天`, close: +p.toFixed(2) });
    }
  }
  return { name: '示例股票', code: 'DEMO', period: '示例数据', bars };
}

const ret = (bars, i, k = 5) => bars[i].close / bars[Math.max(0, i - k)].close - 1;

export function classify(r) {
  if (r > 0.05) return 'rally';
  if (r < -0.05) return 'crash';
  return 'flat';
}

// 决策点大致均匀分布，再在附近 ±2 天里挑涨跌最剧烈的那天，让每一关都有"情绪"
export function fromBars(meta, { rounds = 6, warmup = 5 } = {}) {
  const { bars } = meta;
  const n = bars.length;
  const stops = [];
  for (let k = 1; k <= rounds; k++) {
    const center = Math.round(warmup + ((n - 1 - warmup) * k) / (rounds + 1));
    let best = center;
    for (let i = center - 2; i <= center + 2; i++) {
      if (i > (stops.at(-1)?.i ?? warmup) + 1 && i < n - 1 && Math.abs(ret(bars, i)) > Math.abs(ret(bars, best))) best = i;
    }
    const r = ret(bars, best);
    stops.push({ i: best, ret: r, kind: classify(r) });
  }
  return { ...meta, stops };
}
