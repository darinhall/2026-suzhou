// 屏幕 UI：表情 + 卡片。状态名与交接文档 §4 的 face.state 一致。
// 这里是 DOM 实现，真机用 LVGL 按同样的布局和像素尺寸画。

const esc = (s = '') => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const LEGAL = '示例数据 · 不构成投资建议';

function eyes(extra = '') {
  return `<div class="eyes ${extra}"><i class="eye"></i><i class="eye"></i></div><div class="mouth"></div>`;
}

function spark(points, up) {
  if (!points?.length) return '';
  const w = 444, h = 90, min = Math.min(...points), max = Math.max(...points), span = max - min || 1;
  const xy = points.map((v, i) => `${(i / Math.max(1, points.length - 1)) * w},${h - ((v - min) / span) * (h - 8) - 4}`).join(' ');
  const color = up ? 'var(--up)' : 'var(--down)';
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${xy}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round"/></svg>`;
}

const VIEWS = {
  idle: () => eyes(),
  blink: (c) => eyes() + `<div class="badge">${esc(c?.count ?? 1)}</div>`,
  happy: () => eyes('happy'),
  listening: () => eyes() + '<div class="wave"><i></i><i></i><i></i><i></i><i></i><i></i></div>',
  thinking: () => eyes('up') + '<div class="dots"><i></i><i></i><i></i></div>',
  ok: (c) => `<div class="check"><b>✓</b>${esc(c?.title ?? '已确认')}</div>`,
  msg: (c = {}) => `
    <div class="card ${c.level === 'urgent' ? 'urgent' : ''}">
      <div class="mini"><i></i><i></i></div>
      <div class="title">${esc(c.title)}</div>
      <div class="body">${esc(c.body)}</div>
      <div class="hint">${esc(c.hint ?? '')}</div>
    </div>`,
  mkt: (c = {}) => {
    const up = (c.pct ?? 0) >= 0;
    const cls = up ? 'up' : 'down';
    return `
    <div class="card mkt">
      <div class="head"><span class="name">${esc(c.name)}</span><span class="code">${esc(c.code)}</span></div>
      <div class="nums">
        <span class="pct ${cls}">${up ? '+' : ''}${Number(c.pct ?? 0).toFixed(2)}%</span>
        ${c.vol_ratio != null ? `<span class="vr">量比 ${Number(c.vol_ratio).toFixed(1)}</span>` : ''}
      </div>
      ${spark(c.spark, up)}
      <div class="hint">${esc(c.hint ?? '')}</div>
      <div class="legal">${LEGAL}</div>
    </div>`;
  },
  // 摸鱼模式：只有眼睛，没有数字。外人看是表情，主人看得懂行情。参数由 updateStealth 写进 CSS 变量
  stealth: () => `<div class="stealth"><div class="eyes"><i class="eye"></i><i class="eye"></i></div><i class="blush"></i><i class="blush"></i></div>`,
  // 老板键：伪装成办公助手
  decoy: (c = {}) => {
    const now = new Date();
    const hm = now.toTimeString().slice(0, 5);
    const day = now.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' });
    return `
    <div class="decoy">
      <div class="clock">${hm}</div>
      <div class="date">${day}</div>
      <div class="next"><span>下一个会议</span>${esc(c.meeting ?? '15:00 · 产品评审会')}</div>
      <div class="todo">今日待办 ${esc(c.todo ?? 3)} 项 · 专注中</div>
    </div>`;
  },
};

// 行情 → 表情：pct 是自选股平均涨跌幅（%），vol 是波动程度 0–1
function updateStealth(root, { pct = 0, vol = 0.3, alert = false } = {}) {
  const s = root.querySelector('.stealth');
  if (!s) return;
  const lid = pct <= -2 ? 0.45 : pct < -0.5 ? 0.25 : 0;                       // 跌：眼皮耷拉
  const blush = pct >= 2 ? 0.9 : pct > 0.5 ? (pct - 0.5) / 1.5 * 0.6 : 0;      // 涨：脸红
  s.classList.toggle('joy', pct >= 2);                                          // 大涨：眯眼笑
  s.style.setProperty('--lid', lid);
  s.style.setProperty('--blush', blush.toFixed(2));
  s.style.setProperty('--tint', pct >= 0 ? '#7f9dff' : '#3fc0d6');            // 偏紫 = 涨，偏青 = 跌，只有主人知道
  s.style.setProperty('--breath', `${(6 - 4.5 * Math.min(1, vol)).toFixed(1)}s`); // 波动越大呼吸越快
  if (alert) {
    s.classList.remove('ping');
    void s.offsetWidth;
    s.classList.add('ping');
  }
}

export class Face {
  constructor(el, onTouch) {
    this.el = el;
    this.state = 'idle';
    el.addEventListener('pointerdown', (e) => {
      const r = el.getBoundingClientRect();
      // 3D 变换后 rect 是投影后的包围盒，正对时足够准确
      onTouch(Math.round(((e.clientX - r.left) / r.width) * 480), Math.round(((e.clientY - r.top) / r.height) * 320));
      e.stopPropagation();
    });
    this.blinkLoop();
  }

  set(state, card) {
    const view = VIEWS[state];
    if (!view) return console.warn('unknown face state', state);
    // 摸鱼模式连续更新时不重画，只改变量，呼吸动画才不会一跳一跳
    if (!(state === 'stealth' && this.state === 'stealth')) this.el.innerHTML = view(card);
    if (state === 'stealth') updateStealth(this.el, card);
    clearInterval(this.clock);
    if (state === 'decoy') this.clock = setInterval(() => (this.el.innerHTML = view(card)), 15000);
    this.state = state;
    this.card = card;
  }

  // 空闲时自己眨眼，让它看起来是活的
  blinkLoop() {
    setTimeout(() => {
      const e = this.el.querySelector('.eyes:not(.happy)');
      if (e) { e.classList.add('shut'); setTimeout(() => e.classList.remove('shut'), 120); }
      this.blinkLoop();
    }, 2500 + Math.random() * 3000);
  }
}
