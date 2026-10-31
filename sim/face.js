// 屏幕 UI：表情 + 卡片，按 DeskBot 设计系统画（样式在 screen.css）。
// 状态名就是协议里的 face.state；真机用 LVGL 按同样的布局和像素尺寸画。
// 设计系统规则：每屏最多一张 loud 卡片、一个 accent 元素；lilac 只给 AI；涨跌必须带 ▲▼ 和 +/− 号。

import { denseView, updateBar, DENSE_STATES } from './dense-views.js';

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

// 自选里每一行的迷你走势（viewBox 72×28，颜色跟涨跌；在 loud 行里用深底上的涨跌色）
function miniSpark(points, up) {
  if (!points?.length) return '<span class="wspark"></span>';
  const w = 72, h = 28, min = Math.min(...points), max = Math.max(...points), span = max - min || 1;
  const xy = points.map((v, i) => `${(i / Math.max(1, points.length - 1)) * w},${h - ((v - min) / span) * (h - 6) - 3}`).join(' ');
  return `<span class="wspark ${up ? 'up' : 'down'}"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${xy}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg></span>`;
}

// 数据来源：收盘 = 上一个交易日收盘价；回放 = 历史分钟线快进；实时 = 盘中（需要实时行情权限）；示例 = 编造的数字
const MODE = { close: '收盘', replay: '回放', live: '实时', sample: '示例' };
const legalOf = (mode, legal) => (legal ? `<div class="caption">${esc(legal)}</div>` : mode && mode !== 'sample' ? '<div class="caption">行情数据仅供参考 · 不构成投资建议</div>' : LEGAL);

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

  // 行情：一个点阵大数字 + 走势 + 合规提示。可选：price / prev_close / asof / mode（close|replay|live|sample）/ alert。
  // 没有 mode（老用法）= 一个闪烁的 accent 点。有 mode：右上角一个无色 chip；只有 mode=live 才闪点；alert = 点换成 accent 的「异动」chip（这一屏唯一的 accent）。
  mkt: (c = {}) => {
    const pct = Number(c.pct ?? 0);
    const dot = !c.alert && (c.mode === undefined || c.mode === 'live');
    const chip = c.alert ? '<span class="chip accent">异动</span>' : c.mode ? `<span class="chip">${MODE[c.mode] ?? esc(c.mode)}</span>` : '';
    const priceLine = c.price != null
      ? `<div class="label mkt-price">¥${Number(c.price).toFixed(2)}${c.prev_close != null ? ` · 昨收 ${Number(c.prev_close).toFixed(2)}` : ''}${c.asof ? ` · ${esc(c.asof)}` : ''}</div>`
      : c.asof ? `<div class="label mkt-price">${esc(c.asof)}</div>` : '';
    return `
    <div class="pane mkt">
      <div class="row"><span class="headline">${esc(c.name)}</span><span class="label">${esc(c.code)}</span>
        <span class="mkt-right">${c.vol_ratio != null ? `<span class="label">量比 ${Number(c.vol_ratio).toFixed(1)}</span>` : ''}${chip}</span></div>
      <div class="hero ${dir(pct)}">${dot ? '<span class="live" style="margin-bottom:14px"></span>' : ''}<span class="sign">${glyph(pct)} ${sign(pct)}</span><span class="numeral-xl">${numeral(fixed(pct))}</span><span class="sign">%</span></div>
      <div class="grow">${spark(c.spark, pct >= 0)}</div>
      <div class="foot"><div class="foot-l">${priceLine}${c.hint ? `<span class="hint">${esc(c.hint)}</span>` : ''}${priceLine ? legalOf(c.mode, c.legal) : ''}</div>${priceLine ? '' : legalOf(c.mode, c.legal)}</div>
    </div>`;
  },

  // 自选：顶上一行（标题 · 数据日期 · 指数 · 模式 chip），下面最多三行个股；涨跌幅最大的一行是唯一的 loud 行（深色药丸，点阵大数字）。
  watch: (c = {}) => {
    const sample = { title: '自选', asof: '10-30', mode: 'sample', index: { name: '上证指数', pct: 0.42 }, rows: [
      { name: '宁德时代', code: '300750', pct: 4.8, price: 215.3, spark: [12, 11, 12, 11, 12, 13, 12, 14, 13, 17, 20, 24, 23, 28] },
      { name: '贵州茅台', code: '600519', pct: -0.6, price: 1432.5, spark: [20, 21, 20, 22, 21, 20, 19, 20, 19, 19, 18] },
      { name: '比亚迪', code: '002594', pct: 1.2, price: 268.4, spark: [14, 13, 14, 15, 14, 15, 16, 15, 16, 17] }] };
    const d = { ...sample, ...Object.fromEntries(Object.entries(c).filter(([, v]) => v != null)) };
    const rows = (d.rows ?? []).slice(0, 3);
    const big = rows.reduce((bi, r, i) => (Math.abs(r.pct) > Math.abs(rows[bi].pct) ? i : bi), 0);
    const ix = d.index;
    const row = (r, i) => {
      const p = Number(r.pct ?? 0), loud = i === big;
      const num = loud ? `<b class="n">${numeral(fixed(p, 1))}</b>` : `<b>${fixed(p, 1)}</b>`;
      return `<div class="wrow${loud ? ' loud' : ''}">
        <div class="wname"><span class="headline">${esc(r.name)}</span><span class="label">${esc(r.code)}</span></div>
        ${miniSpark(r.spark, p >= 0)}
        <span class="wprice">${r.price != null ? Number(r.price).toFixed(2) : ''}</span>
        <span class="wpct ${dir(p)}"><span class="g">${glyph(p)}</span><span class="sg">${sign(p)}</span>${num}<span class="u">%</span></span>
      </div>`;
    };
    return `
    <div class="pane watch">
      <div class="row wtop"><span class="label">${esc(d.title)}${d.asof ? ` · ${esc(d.asof)}` : ''}</span>
        ${ix ? `<span class="label wi">${esc(ix.name)} <span class="${dir(ix.pct)}">${glyph(ix.pct)} ${sign(ix.pct)}${fixed(ix.pct, 2)}%</span></span>` : ''}
        <span class="chip" style="margin-left:auto">${MODE[d.mode] ?? esc(d.mode ?? '')}</span></div>
      <div class="wrows">${rows.map(row).join('')}</div>
      ${legalOf(d.mode, d.legal)}
    </div>`;
  },

  // 待机小动画：idle 安静一阵子之后会自己过渡过来（见 Face 的导演），也可以由中枢直接指定。
  // 玩球：橙色小球在屏幕里弹来弹去，眼睛跟着它。小球是这一屏唯一的 accent，所以不画嘴。
  play: () => '<div class="eyes"><i class="eye"></i><i class="eye"></i></div><i class="ball"></i>',
  // 睡觉：闭眼、慢慢呼吸、飘出 z。
  sleep: () => `<div class="sleep"><div class="eyes sleepy"><i class="eye"></i><i class="eye"></i></div>
      <i class="z z1">z</i><i class="z z2">Z</i><i class="z z3">Z</i></div>`,

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

  // 天气（不是 weather：weather 是"市场天气"）。当前温度 = 点阵大数字；一句建议 = 唯一的 loud 卡片。
  // 温度不是涨跌，所以不用红绿（红绿只给价格）。卡片缺字段 / 为 null 时用示例值，点 chip 也能看到完整的一屏。
  sky: (c = {}) => {
    const sample = { city: '苏州', time: '09:10', temp: 16, text: '雾', feels: 15, humidity: 88, hi: 23, lo: 14,
      tmr_text: '小阵雨', tmr_hi: 26, tmr_lo: 16, advice: '明天有雨，记得带伞' };
    const d = { ...sample, ...Object.fromEntries(Object.entries(c).filter(([, v]) => v != null)) };
    const word = String(d.text).length <= 3 ? 'display' : 'title';   // 4 个字以上（"小毛毛雨"）降一档，免得挤掉温度
    return `
    <div class="pane sky">
      <div class="row label">${esc(d.city)} · ${esc(d.time)}<span class="live" style="margin-left:auto"></span></div>
      <div class="row sky-hero grow">
        <span class="numeral-xl">${esc(d.temp)}</span><span class="headline deg">°C</span>
        <div class="sky-word"><div class="${word}">${esc(d.text)}</div><div class="label">体感 ${esc(d.feels)}° · 湿度 ${esc(d.humidity)}%</div></div>
      </div>
      <div class="loud">
        <div class="label meta">今天 ${esc(d.lo)}–${esc(d.hi)}° · 明天 ${esc(d.tmr_text)} ${esc(d.tmr_lo)}–${esc(d.tmr_hi)}°</div>
        <div class="title">${esc(d.advice)}</div>
      </div>
    </div>`;
  },

  // 今天：日期是点阵大数字；右边一行天气；唯一的 loud 卡片 = 下一个日程。休市 / 盘前 / 交易中 是一个不带颜色的 chip。
  // 缺字段 / 为 null 用示例值（点 chip 也能看到完整一屏）；没有日程时卡片说"今天没有会议了"。
  today: (c = {}) => {
    const sample = { month: 10, day: 30, weekday: '周五', market: '盘前', city: '苏州', temp: 16, text: '雾',
      tmr_text: '小阵雨', tmr_lo: 16, tmr_hi: 26, next_time: '15:00', next_in: '6 小时后', next_title: '产品评审会', next_where: '3 号会议室' };
    const clean = Object.fromEntries(Object.entries(c).filter(([, v]) => v != null));
    // 数据来自真实接口时（有 city 但没有 next_title），说明今天没有后续日程，不要拿示例日程冒充
    const d = { ...sample, ...clean, ...(c.city && !c.next_title ? { next_title: null } : {}) };
    // 这一行放不下就丢掉地点：汉字约 1em、其他约 0.6em，小屏一行大约能放 22em
    const emLen = (t) => [...t].reduce((n, ch) => n + (ch.charCodeAt(0) > 255 ? 1 : 0.6), 0);
    const meta = [`下一个`, d.next_time, d.next_in, d.next_where].filter(Boolean);
    if (emLen(meta.join(' · ')) > 21) meta.pop();
    const card = d.next_title
      ? `<div class="label meta">${esc(meta.join(' · '))}</div><div class="title">${esc(d.next_title)}</div>`
      : `<div class="label meta">日程</div><div class="title">今天没有会议了</div>`;
    return `
    <div class="pane today">
      <div class="row label">${esc(d.month)}月 · ${esc(d.weekday)}<span class="chip" style="margin-left:auto">${esc(d.market)}</span></div>
      <div class="row today-hero grow">
        <span class="numeral-xl">${esc(d.day)}</span>
        <div class="today-side"><div class="headline">${esc(d.city)} ${esc(d.temp)}° ${esc(d.text)}</div><div class="label">明天 ${esc(d.tmr_text)} ${esc(d.tmr_lo)}–${esc(d.tmr_hi)}°</div></div>
      </div>
      <div class="loud">${card}</div>
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

// ---------- 显示模式：简洁（原来的大字视图）/ 紧凑 / 专业（信息密度版，见 dense-views.js）----------
// 只有开了 opts.dense 的屏幕（主屏和 3D 头里的镜像屏）会跟着切换；实验室、游戏页的屏幕不受影响。
export const DENSITIES = ['simple', 'compact', 'pro'];
const DENSITY_KEY = 'deskbot.sim.density';
const readDensity = () => { try { const v = localStorage.getItem(DENSITY_KEY); return DENSITIES.includes(v) ? v : 'pro'; } catch { return 'pro'; } };
let density = readDensity();
const densityListeners = new Set();
export const getDensity = () => density;
export function setDensity(mode) {
  if (!DENSITIES.includes(mode) || mode === density) return false;
  density = mode;
  try { localStorage.setItem(DENSITY_KEY, mode); } catch {}
  densityListeners.forEach((fn) => fn(mode));
  return true;
}
export const onDensity = (fn) => densityListeners.add(fn);


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
  // opts.idleAfter：idle 安静多少秒之后开始玩球（0 / 不传 = 不自动；只有模拟器这块屏开）；opts.playFor：玩多少秒再去睡
  constructor(el, onTouch = () => {}, opts = {}) {
    this.el = el;
    this.opts = opts;
    this.state = 'idle';
    this.scene = null;   // 场景引擎的 {page, of, clock}：专业 / 紧凑屏的状态栏用
    this.stateSince = this.lastActive = performance.now();
    el.addEventListener('pointerdown', (e) => {
      this.poke();
      if (this.state === 'play' || this.state === 'sleep') this._show('idle');   // 摸一下就醒
      const r = el.getBoundingClientRect();
      // 3D 变换后 rect 是投影后的包围盒，正对时足够准确；换算成屏幕自己的像素（320×240 或 480×320）
      onTouch(Math.round(((e.clientX - r.left) / r.width) * el.offsetWidth), Math.round(((e.clientY - r.top) / r.height) * el.offsetHeight));
      e.stopPropagation();
    });
    if (opts.dense) {   // 跟随显示模式；状态栏的时钟每 20 秒刷新一次
      this.el.dataset.density = density;
      onDensity((mode) => {
        if (!this.el.isConnected) return;
        this.el.dataset.density = mode;
        if (DENSE_STATES.includes(this.state)) this._show(this.state, this.card);   // 当前就是信息屏：换成对应模式重画
      });
      setInterval(() => { if (this.el.isConnected) updateBar(this.el, this.scene); }, 20000);
    }
    this.blinkLoop();
    this.lookLoop();
    if (opts.idleAfter > 0) this.directorTimer = setInterval(() => this.direct(), 500);
  }

  // 中枢的场景引擎走到第几页 / 回放到几点：只换信息屏的状态栏，不重画整屏
  setScene(info) {
    this.scene = info && info.name ? { page: info.page, of: info.of, clock: info.clock } : null;
    if (this.opts.dense) updateBar(this.el, this.scene);
  }

  // 有人动过它（消息、触摸、按头）：重新计时
  poke() { this.lastActive = performance.now(); }

  // 待机导演：idle 安静 idleAfter 秒 → 玩球 playFor 秒 → 睡觉，直到有人动它
  direct() {
    if (!this.el.isConnected) return clearInterval(this.directorTimer);
    const now = performance.now();
    if (this.state === 'idle' && now - this.lastActive > this.opts.idleAfter * 1000) this._show('play');
    else if (this.state === 'play' && now - this.stateSince > (this.opts.playFor ?? 12) * 1000) this._show('sleep');
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

  set(state, card) {   // 外面（中枢、演示脚本、按钮）来的指令：算"有人动过它"
    this.poke();
    this._show(state, card);
  }

  _show(state, card) {
    let view = VIEWS[state];
    if (this.opts.dense && density !== 'simple' && DENSE_STATES.includes(state)) view = (c) => denseView(state, c, density, this.scene);   // 紧凑 / 专业：信息密度版
    if (!view) return console.warn('unknown face state', state);
    const prev = this.state;
    this.stopAnim();
    // 摸鱼模式连续更新时不重画，只改变量，呼吸动画才不会一跳一跳
    if (!(state === 'stealth' && this.state === 'stealth')) {
      this.el.innerHTML = view(card);
      // 行情 / 自选连续刷新数字时不重放进场动画，不然每次更新都闪一下
      if (state === prev && (state === 'watch' || state === 'mkt')) for (const ch of this.el.children) ch.style.animation = 'none';
    }
    if (state === 'stealth') updateStealth(this.el, card);
    clearInterval(this.clock);
    if (state === 'decoy' && !card?.time) this.clock = setInterval(() => (this.el.innerHTML = view(card)), 15000);
    this.state = state;
    this.card = card;
    this.stateSince = performance.now();
    if (state === 'play') this.startPlay();
    if (prev === 'sleep' && state !== 'sleep') {   // 被吵醒：眼睛一下子睁大
      this.el.classList.add('waking');
      setTimeout(() => this.el.classList.remove('waking'), 400);
    }
  }

  stopAnim() {
    cancelAnimationFrame(this.raf);
    if (this.state === 'play') this.glance0();
  }

  // 小球：重力 + 墙壁反弹，落地压扁一下；眼睛跟着球走
  startPlay() {
    const el = this.el, ball = el.querySelector('.ball');
    const W = el.offsetWidth, H = el.offsetHeight, r = ball.offsetWidth / 2, G = H * 2.6;
    let x = W * (0.15 + Math.random() * 0.2), y = H * 0.3, vx = (Math.random() < 0.5 ? -1 : 1) * W * 0.3, vy = 0, squash = 0, last = performance.now();
    const step = (now) => {
      if (!el.isConnected || this.state !== 'play') return;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      vy += G * dt; x += vx * dt; y += vy * dt;
      if (x < r) { x = r; vx = Math.abs(vx); }
      if (x > W - r) { x = W - r; vx = -Math.abs(vx); }
      if (y > H - r) { y = H - r; vy = -Math.max(Math.abs(vy) * 0.9, H * 1.25); squash = 1; }   // 永远弹得起来
      if (y < r) { y = r; vy = Math.abs(vy) * 0.5; }
      squash = Math.max(0, squash - dt * 6);
      const sy = 1 - 0.35 * squash, sx = 1 + 0.35 * squash;
      ball.style.transform = `translate(${x - r}px, ${y - r + r * (1 - sy)}px) scale(${sx}, ${sy})`;
      el.style.setProperty('--gx', `${Math.max(-34, Math.min(34, (x - W / 2) * 0.14))}px`);
      el.style.setProperty('--gy', `${Math.max(-18, Math.min(18, (y - H / 2) * 0.12))}px`);
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  }

  // 空闲时自己眨眼，让它看起来是活的
  blinkLoop() {
    setTimeout(() => {
      if (!this.el.isConnected) return;   // 实验室重画后旧的屏幕会被移除，停掉它的计时器
      const e = this.el.querySelector('.eyes:not(.happy):not(.sleepy)');
      if (e && !this.el.querySelector('.joy')) { e.classList.add('shut'); setTimeout(() => e.classList.remove('shut'), 120); }
      this.blinkLoop();
    }, 2500 + Math.random() * 3000);
  }
}
