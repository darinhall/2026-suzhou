// 大模式（盯盘 / 天气 / 今天 / 时钟 / 待机 / 展台）的离线版：没连中枢时，模拟器按设置自己轮播，用示例数据。
// 连着中枢时由中枢调度（{"t":"mode"}），这里不参与。item 的页数、标签和中枢的 scene_state 字段一致。

import { SAMPLES } from './dense-samples.js';
import { MODES, SYMBOLS } from './profile.js';
import { mktCard, watchCard } from './scenes.js';

const hash = (s) => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const rnd = (seed, i) => { const x = Math.sin(seed * 12.9898 + i * 78.233) * 43758.5453; return x - Math.floor(x); };

// 一只股票的示例行情：认识的用表里的昨收，不认识的按代码哈希出一个价格
export function stockOf(code, name) {
  const h = hash(code), known = SYMBOLS.find((s) => s.code === code);
  const prev = known?.prev ?? +(10 + rnd(h, 1) * 190).toFixed(2);
  const pct = +((rnd(h, 2) - 0.5) * 9).toFixed(2);
  return { name: name || known?.name || code, code, prev, p: +(prev * (1 + pct / 100)).toFixed(2), vr: +(0.6 + rnd(h, 3) * 1.8).toFixed(1), amt: +(5 + rnd(h, 4) * 120).toFixed(1) };
}

function itemsOf(name, P) {
  const w = P.watch;
  const listItems = () => {
    const stocks = w.codes.map((c) => stockOf(c, P.watch.names?.[c]));
    if (!stocks.length) return [{ label: '自选为空', state: 'watch', card: SAMPLES.watch, sec: w.interval }];
    const pages = [];
    for (let i = 0; i < stocks.length; i += 5) pages.push(stocks.slice(i, i + 5));
    return pages.map((rows, i) => ({ label: pages.length > 1 ? `第 ${i + 1} 页` : '全部自选', state: 'watch', card: watchCard(rows, 'close', '示例数据'), sec: w.interval }));
  };
  const watchItems = () => {
    const stocks = w.codes.map((c) => stockOf(c, P.watch.names?.[c]));
    if (!stocks.length) return [{ label: '自选为空', state: 'watch', card: SAMPLES.watch, sec: w.interval }];
    if (w.view === 'list') return listItems();   // 设置里选了「列表」：盯盘也按列表轮播
    return stocks.map((s) => ({ label: s.name, state: 'mkt', card: { ...mktCard(s), asof: '示例数据', mode: 'sample' }, sec: w.interval }));
  };
  const todayItem = () => [{ label: P.today.city, state: 'today', card: { ...SAMPLES.today, city: P.today.city }, sec: 15 }];
  switch (name) {
    case 'watch': return watchItems();
    case 'list': return listItems();
    case 'today': return todayItem();
    case 'idle': return [{ label: '待机', state: 'idle', card: undefined, sec: 0 }];
    case 'booth': return [...watchItems().slice(0, 3), ...listItems(), ...todayItem()].map((it) => ({ ...it, sec: P.booth.dwell }));
    default: return [];
  }
}

export function createModeRunner({ handle, onState, getProfile }) {
  let name = null, items = [], i = 0, timer = null, paused = false;

  function show() {
    const it = items[i];
    if (!it) return;
    handle({ t: 'face', state: it.state, ...(it.card ? { card: it.card } : {}) });
    onState({ t: 'scene_state', name, page: i + 1, of: items.length, label: MODES.find((m) => m.id === name)?.label ?? name, item: it.label, paused });
    clearTimeout(timer);
    if (!paused && items.length > 1 && it.sec > 0) timer = setTimeout(() => step(1), it.sec * 1000);
  }
  function step(d) { if (!items.length) return; i = (i + d + items.length) % items.length; show(); }

  return {
    get name() { return name; },
    get paused() { return paused; },
    start(n) {
      clearTimeout(timer);
      name = n; paused = false; i = 0;
      items = itemsOf(n, getProfile());
      show();
    },
    refresh() { if (name) { const label = items[i]?.label; items = itemsOf(name, getProfile()); i = Math.max(0, items.findIndex((x) => x.label === label)); show(); } },   // 设置变了：重新排队，尽量停在原来那一项
    next() { step(1); },
    prev() { step(-1); },
    togglePause() { paused = !paused; show(); return paused; },
    stop() { clearTimeout(timer); name = null; items = []; paused = false; },
  };
}
