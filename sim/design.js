// 设计旋钮：实验室里调，模拟器和游戏页同步（同一个浏览器里用 localStorage + storage 事件）。

export const KNOBS = [
  { key: 'size', label: '屏幕', options: [['s', '2.8″ 320×240（T5 实机）'], ['l', '3.5″ 480×320']] },
  { key: 'theme', label: '主题', options: [['light', '浅色'], ['dark', '深色']] },
  { key: 'accent', label: '强调色', options: [['orange', '橙（默认）'], ['amber', '琥珀'], ['cobalt', '钴蓝']] },
  { key: 'numeral', label: '数字字体', options: [['dot', '点阵 Doto'], ['sans', '细体 Geist'], ['mono', '等宽 Mono']] },
  { key: 'card', label: '卡片', options: [['loud', '反白（默认）'], ['quiet', '安静']] },
  { key: 'radius', label: '圆角', options: [['default', '默认'], ['sharp', '硬朗'], ['round', '圆润']] },
  { key: 'fs', label: '字号', options: [['0.9', '紧凑'], ['1', '默认'], ['1.1', '远看']] },
];

export const DEFAULTS = { size: 's', theme: 'light', accent: 'orange', numeral: 'dot', card: 'loud', radius: 'default', fs: '1' };
const KEY = 'deskbot.design';

export function load() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return { ...DEFAULTS }; }
}

export function save(d) {
  try { localStorage.setItem(KEY, JSON.stringify(d)); } catch {}
}

export function apply(el, d = load()) {
  for (const k of ['size', 'theme', 'accent', 'numeral', 'card', 'radius']) el.dataset[k] = d[k];
  el.style.setProperty('--fs', d.fs);
}

// 别的标签页改了设计，这里跟着变
export function follow(...els) {
  els.forEach((el) => apply(el));
  window.addEventListener('storage', (e) => e.key === KEY && els.forEach((el) => apply(el)));
}
