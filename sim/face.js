// 屏幕 UI：表情 + 卡片，按 DeskBot 设计系统画（样式在 screen.css）。
// 状态名就是协议里的 face.state；真机用 LVGL 按同样的布局和像素尺寸画。
// 设计系统规则：每屏最多一张 loud 卡片、一个 accent 元素；lilac 只给 AI；涨跌必须带 ▲▼ 和 +/− 号。

const esc = (s = '') => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const LEGAL = '<div class="caption">示例数据 · 不构成投资建议</div>';
const sign = (v) => (v >= 0 ? '+' : '−');
const glyph = (v) => (v >= 0 ? '▲' : '▼');
const dir = (v) => (v >= 0 ? 'up' : 'down');
const fixed = (v, d = 1) => Math.abs(Number(v ?? 0)).toFixed(d);
// 点阵字体里的小数点像一团 "+"，换成一个方点，4.8 才不会被看成 4+8
const numeral = (text) => String(text).replace('.', '<i class="pt"></i>');

function eyes(extra = '', mouth = true) {
  return `<div class="eyes ${extra}"><i class="eye"></i><i class="eye"></i></div>${mouth ? '<div class="mouth"></div>' : ''}`;
}

function spark(points, up) {
  if (!points?.length) return '';
  const w = 448, h = 72, min = Math.min(...points), max = Math.max(...points), span = max - min || 1;
  const xy = points.map((v, i) => `${(i / Math.max(1, points.length - 1)) * w},${h - ((v - min) / span) * (h - 8) - 4}`).join(' ');
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${xy}" fill="none" stroke="var(--${up ? 'up' : 'down'})" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
}

function ruler(total, done) {
  return `<div class="ruler">${Array.from({ length: total }, (_, i) => `<i class="${i < done ? 'past' : i === done ? 'now' : ''}"></i>`).join('')}</div>`;
}

const VIEWS = {
  idle: () => eyes(),
  blink: (c) => eyes() + `<div class="badge">${esc(c?.count ?? 1)}</div>`,
  happy: () => eyes('happy'),
  listening: () => eyes('ai', false) + '<div class="wave"><i></i><i></i><i></i><i></i><i></i><i></i></div>',
  thinking: () => eyes('ai up', false) + '<div class="dots"><i></i><i></i><i></i></div>',
  ok: (c) => `<div class="check"><b>✓</b><div class="title">${esc(c?.title ?? '已确认')}</div></div>`,

  // 消息：loud 卡片就是消息本身，下面一行说按头做什么
  msg: (c = {}) => `
    <div class="pane">
      <div class="loud grow">
        <div class="row label">${esc(c.title)}${c.level === 'urgent' ? '<span class="chip accent">紧急</span>' : ''}</div>
        <div class="title grow">${esc(c.body)}</div>
        ${c.meta ? `<div class="label meta">${esc(c.meta)}</div>` : ''}
      </div>
      <div class="hint">${esc(c.hint ?? '')}</div>
    </div>`,

  // 行情：一个点阵大数字 + 走势 + 合规提示
  mkt: (c = {}) => {
    const pct = Number(c.pct ?? 0);
    return `
    <div class="pane mkt">
      <div class="row"><span class="headline">${esc(c.name)}</span><span class="label">${esc(c.code)}</span>
        ${c.vol_ratio != null ? `<span class="label" style="margin-left:auto">量比 ${Number(c.vol_ratio).toFixed(1)}</span>` : ''}</div>
      <div class="hero ${dir(pct)}"><span class="live" style="margin-bottom:14px"></span><span class="sign">${glyph(pct)} ${sign(pct)}</span><span class="numeral-xl">${numeral(fixed(pct))}</span><span class="sign">%</span></div>
      <div class="grow">${spark(c.spark, pct >= 0)}</div>
      <div class="foot"><span class="hint">${esc(c.hint ?? '')}</span>${LEGAL}</div>
    </div>`;
  },

  // 摸鱼模式：只有眼睛，参数由 updateStealth 写进 CSS 变量
  stealth: () => `<div class="stealth"><div class="eyes"><i class="eye"></i><i class="eye"></i></div><i class="blush"></i><i class="blush"></i></div>`,

  // 老板键：伪装成办公助手（时钟 + 下一个会议）
  decoy: (c = {}) => {
    const now = new Date();
    const [h, m] = (c.time ?? now.toTimeString().slice(0, 5)).split(':');
    const day = c.date ?? now.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' });
    return `
    <div class="pane">
      <div><div class="numeral-lg">${h}<span>:${m}</span></div><div class="label" style="margin-top:6px">${esc(day)}</div></div>
      <div class="loud grow" style="justify-content:flex-end">
        <div class="label">下一个会议</div>
        <div class="title">${esc(c.meeting ?? '15:00 · 产品评审会')}</div>
      </div>
      <div class="hint">今日待办 ${esc(c.todo ?? 3)} 项 · 专注中</div>
    </div>`;
  },

  // 会议倒计时：点阵分钟数 + 刻度尺
  meeting: (c = {}) => `
    <div class="pane">
      <div class="row label">${esc(c.source ?? '飞书日历')}<span class="live" style="margin-left:auto"></span></div>
      <div class="row" style="align-items:flex-end"><span class="numeral-xl">${String(c.minutes ?? 5).padStart(2, '0')}</span><span class="headline" style="padding-bottom:8px">分钟后</span></div>
      <div class="title grow">${esc(c.title ?? '')}</div>
      ${ruler(c.span ?? 30, (c.span ?? 30) - (c.minutes ?? 5))}
      <div class="hint">${esc(c.hint ?? '按头 = 收到')}</div>
    </div>`,

  // A2A 办公室：一个智能体在发言（lilac = AI）
  agent: (c = {}) => `
    <div class="pane">
      <div class="row"><span class="chip ai">${esc(c.name)}</span><span class="label">${esc(c.source ?? 'A2A 办公室 · 盘前简报')}</span></div>
      <div class="title grow" style="display:flex;align-items:center">${esc(c.say)}</div>
      <div class="foot"><div class="steps">${Array.from({ length: c.of ?? 3 }, (_, i) => `<i class="${i < (c.n ?? 1) ? 'on' : ''}"></i>`).join('')}</div>${c.legal === false ? '' : LEGAL}</div>
    </div>`,

  // 市场天气：上涨家数占比做大数字，涨跌家数做比例条
  weather: (c = {}) => {
    const total = (c.up ?? 0) + (c.down ?? 0) || 1;
    const share = Math.round(((c.up ?? 0) / total) * 100);
    return `
    <div class="pane">
      <div class="row label">市场天气 · ${esc(c.time ?? '09:15')}</div>
      <div class="row" style="align-items:flex-end;gap:16px"><span class="numeral-xl">${share}</span><div style="padding-bottom:6px"><div class="display">${esc(c.word ?? '')}</div><div class="label">上涨家数占比 %</div></div></div>
      <div class="grow"></div>
      <div class="split"><i style="width:${share}%;background:var(--up)"></i><i style="flex:1;background:var(--down)"></i></div>
      <div class="foot"><span class="label"><span class="up">▲ ${c.up}</span> · <span class="down">▼ ${c.down}</span></span>${LEGAL}</div>
    </div>`;
  },

  // 简报：三条要点
  brief: (c = {}) => `
    <div class="pane brief">
      <div class="label">${esc(c.title ?? '盘前简报')}</div>
      <ol class="grow">${(c.items ?? []).map((t) => `<li>${esc(t)}</li>`).join('')}</ol>
      <div class="foot"><span class="hint">${esc(c.hint ?? '')}</span>${c.legal === false ? '' : LEGAL}</div>
    </div>`,

  // 护栏：冲动前问一句
  ask: (c = {}) => `
    <div class="pane">
      <div class="loud grow">
        <div class="label">${esc(c.why ?? '')}</div>
        <div class="display grow">${esc(c.title ?? '确定吗？')}</div>
        ${c.meta ? `<div class="label meta">${esc(c.meta)}</div>` : ''}
      </div>
      <div class="hint">${esc(c.hint ?? '按头 = 确认 · 不动 = 算了')}</div>
    </div>`,
};

export const STATES = Object.keys(VIEWS);

// 行情 → 表情：pct 是自选股平均涨跌幅（%），vol 是波动程度 0–1
function updateStealth(root, { pct = 0, vol = 0.3, alert = false } = {}) {
  const s = root.querySelector('.stealth');
  if (!s) return;
  const lid = pct <= -2 ? 0.45 : pct < -0.5 ? 0.25 : 0;
  const blush = pct >= 2 ? 1 : pct > 0.5 ? (pct - 0.5) / 1.5 * 0.6 : 0;
  s.classList.toggle('joy', pct >= 2);
  s.style.setProperty('--lid', lid);
  s.style.setProperty('--blush', blush.toFixed(2));
  s.style.setProperty('--breath', `${(6 - 4.5 * Math.min(1, vol)).toFixed(1)}s`);
  if (alert) {
    s.classList.remove('ping');
    void s.offsetWidth;
    s.classList.add('ping');
  }
}

export class Face {
  constructor(el, onTouch = () => {}) {
    this.el = el;
    this.state = 'idle';
    el.addEventListener('pointerdown', (e) => {
      const r = el.getBoundingClientRect();
      // 3D 变换后 rect 是投影后的包围盒，正对时足够准确；换算成屏幕自己的像素（320×240 或 480×320）
      onTouch(Math.round(((e.clientX - r.left) / r.width) * el.offsetWidth), Math.round(((e.clientY - r.top) / r.height) * el.offsetHeight));
      e.stopPropagation();
    });
    this.blinkLoop();
    this.lookLoop();
  }

  // 眼睛看向 (dx, dy) 像素，ms 后回中。身体转动前调用，眼睛先到、头后到
  glance(dx, dy, ms = 500) {
    if (!dx && !dy) return;
    this.el.style.setProperty('--gx', `${dx}px`);
    this.el.style.setProperty('--gy', `${dy}px`);
    clearTimeout(this.gazeReset);
    this.gazeReset = setTimeout(() => this.glance0(), ms + 250);
  }

  glance0() {
    this.gazeReset = null;
    this.el.style.setProperty('--gx', '0px');
    this.el.style.setProperty('--gy', '0px');
  }

  // 空闲时偶尔瞟一眼别处，再看回来：不动的脸看起来像死机
  lookLoop() {
    setTimeout(() => {
      if (!this.el.isConnected) return;
      if (['idle', 'blink', 'happy', 'listening'].includes(this.state) && !this.gazeReset) {
        const away = Math.random() < 0.55;
        this.el.style.setProperty('--gx', away ? `${Math.round((Math.random() - 0.5) * 20)}px` : '0px');
        this.el.style.setProperty('--gy', away ? `${Math.round((Math.random() - 0.5) * 10)}px` : '0px');
      }
      this.lookLoop();
    }, 2200 + Math.random() * 3500);
  }

  set(state, card) {
    const view = VIEWS[state];
    if (!view) return console.warn('unknown face state', state);
    // 摸鱼模式连续更新时不重画，只改变量，呼吸动画才不会一跳一跳
    if (!(state === 'stealth' && this.state === 'stealth')) this.el.innerHTML = view(card);
    if (state === 'stealth') updateStealth(this.el, card);
    clearInterval(this.clock);
    if (state === 'decoy' && !card?.time) this.clock = setInterval(() => (this.el.innerHTML = view(card)), 15000);
    this.state = state;
    this.card = card;
  }

  // 空闲时自己眨眼，让它看起来是活的
  blinkLoop() {
    setTimeout(() => {
      if (!this.el.isConnected) return;   // 实验室重画后旧的屏幕会被移除，停掉它的计时器
      const e = this.el.querySelector('.eyes:not(.happy)');
      if (e && !this.el.querySelector('.joy')) { e.classList.add('shut'); setTimeout(() => e.classList.remove('shut'), 120); }
      this.blinkLoop();
    }, 2500 + Math.random() * 3000);
  }
}
