// 一天的场景（起床后 / 盯盘 / 收盘 / 展台）的离线版：没连中枢时，模拟器自己按页播放，数字用示例数据，
// 这样没有网络、没有 PandaAI 账号也能完整演示。连上中枢时，场景由中枢调度（{"t":"scene"}），这里不参与。
// 页数、页序和中枢的场景引擎（hub）一致：n / of 就是 scene_state 里的 page / of。

export const SCENES = [
  { id: 'morning', label: '起床后', desc: '今天 → 早安简报 → 自选（上个交易日收盘）' },
  { id: 'watch', label: '盯盘', desc: '自选回放：数字实时跳动，异动时弹出行情卡' },
  { id: 'close', label: '收盘', desc: '自选收盘 → 收盘小结 → 睡觉' },
  { id: 'booth', label: '展台', desc: '全部串起来，循环播放，没人碰就玩球 / 睡觉' },
];

const wait = (ms, sig) => new Promise((r) => {
  const t = setTimeout(r, ms);
  sig.onabort = () => { clearTimeout(t); r(); };
});

// ---- 示例数据 ----
const BASE = [
  { name: '宁德时代', code: '300750', prev: 205.45, p: 215.3, vr: 1.4, amt: 135.2 },
  { name: '贵州茅台', code: '600519', prev: 1441.1, p: 1432.5, vr: 0.8, amt: 31.9 },
  { name: '比亚迪', code: '002594', prev: 265.2, p: 268.4, vr: 1.0, amt: 17.1 },
];
export const sparkOf = (prev, p, n = 20) => Array.from({ length: n }, (_, i) => +(prev + ((p - prev) * i) / (n - 1) + Math.sin(i * 1.3 + p) * prev * 0.004).toFixed(2));
const pctOf = (r) => +(((r.p - r.prev) / r.prev) * 100).toFixed(2);
// 离线示例卡片也带上"专业 / 紧凑"屏要的字段（开高低、振幅、量比、成交额），并标 sample:true，屏幕上显示「示例」
export const rowOf = (r) => {
  const sp = r.spark ?? sparkOf(r.prev, r.p), hi = Math.max(...sp, r.p), lo = Math.min(...sp, r.p);
  return { name: r.name, code: r.code, pct: pctOf(r), price: +r.p.toFixed(2), prev_close: r.prev, open: sp[1] ?? r.prev, high: +hi.toFixed(2), low: +lo.toFixed(2),
    amp: +(((hi - lo) / r.prev) * 100).toFixed(2), vol_ratio: r.vr ?? 1, amount: r.amt ?? 20, spark: sp };
};
const INDICES = [{ name: '上证', value: 3296.5, pct: 0.42 }, { name: '深证', value: 10512.3, pct: 0.61 }, { name: '创业板', value: 2105.8, pct: 1.12 }, { name: '沪深300', value: 3891.2, pct: 0.38 }];

export const watchCard = (rows, mode, asof) => ({ title: '自选', asof, mode, sample: true, index: { name: '上证指数', pct: 0.42 }, indices: INDICES, rows: rows.map(rowOf) });
export const mktCard = (r, extra = {}) => ({ ...rowOf(r), code: `${r.code}.${r.code[0] === '6' ? 'SH' : 'SZ'}`, sample: true, ...extra });

const BRIEF_MORNING = { title: '早安简报', items: ['昨晚美股科技走弱，半导体承压', '今天 15:00 产品评审会，别迟到', '自选里宁德时代上个交易日 +4.8%'], hint: '', legal: false };
const BRIEF_CLOSE = { title: '收盘小结', items: ['自选 3 只：2 涨 1 跌，平均 +1.8%', '最大异动：宁德时代 ▲ +4.8%，量比 2.3', '明天 09:30 开盘，我会提前叫你'], hint: '', legal: false };

// 每个场景 = 一串页；页里 run(ctx) 负责把这一页画出来并等够时间
function pagesOf(name) {
  const close = () => watchCard(BASE, 'close', '10-30 收盘');
  const pages = {
    morning: [
      { face: () => ({ state: 'today', card: {} }), ms: 4000 },
      { face: () => ({ state: 'brief', card: BRIEF_MORNING }), ms: 4500 },
      { face: () => ({ state: 'watch', card: close() }), ms: 5000 },
    ],
    watch: [
      { replay: true, ms: 14000 },
      { face: () => ({ state: 'mkt', card: mktCard({ ...BASE[0], p: 218.9 }, { alert: true, vol_ratio: 2.3, asof: '回放 13:21', mode: 'replay', hint: '按头 = 记入模拟单' }) }), ms: 4500 },
    ],
    close: [
      { face: () => ({ state: 'watch', card: close() }), ms: 5000 },
      { face: () => ({ state: 'brief', card: BRIEF_CLOSE }), ms: 5000 },
      { face: () => ({ state: 'sleep', card: {} }), ms: 4000 },
    ],
  };
  if (name === 'booth') return [...pages.morning, ...pages.watch, ...pages.close.slice(0, 2)];
  return pages[name];
}

export function createSceneRunner({ handle, onState, caption }) {
  let sig = null;

  async function replay(ms, s) {   // 盯盘回放：三只票随机游走，数字每 0.7 秒跳一次，涨幅最大的那行是 loud 行
    const rows = BASE.map((r) => ({ ...r, p: r.prev, spark: [r.prev] }));
    const t0 = performance.now();
    while (!s.aborted && performance.now() - t0 < ms) {
      rows.forEach((r, i) => {
        const drift = (BASE[i].p - r.prev) / 20;
        r.p = Math.max(0.01, r.p + drift + (Math.random() - 0.5) * r.prev * 0.004);
        r.spark = [...r.spark, +r.p.toFixed(2)].slice(-24);
      });
      await handle({ t: 'face', state: 'watch', card: watchCard(rows, 'replay', '回放 10-30') });
      await wait(700, s);
    }
  }

  async function play(name) {
    const s = sig = { aborted: false, onabort: null };
    s.abort = () => { s.aborted = true; s.onabort?.(); };
    const pages = pagesOf(name);
    const label = SCENES.find((x) => x.id === name).label;
    do {
      for (let i = 0; i < pages.length && !s.aborted; i++) {
        onState({ t: 'scene_state', name, page: i + 1, of: pages.length });
        caption(`场景 · ${label} · ${i + 1}/${pages.length}`);
        const pg = pages[i];
        if (pg.replay) await replay(pg.ms, s);
        else {
          const f = pg.face();
          await handle({ t: 'face', state: f.state, card: f.card });
          await wait(pg.ms, s);
        }
      }
    } while (name === 'booth' && !s.aborted);   // 展台循环
    if (sig === s) { sig = null; caption(''); }
    if (!s.aborted) { onState({ t: 'scene_state', name: 'stop', page: 0, of: 0 }); await handle({ t: 'face', state: 'idle' }); }
  }

  return {
    start(name) { this.stop(); play(name); },
    stop() {
      if (sig) { sig.abort(); sig = null; }
      caption('');
      onState({ t: 'scene_state', name: 'stop', page: 0, of: 0 });
    },
  };
}
