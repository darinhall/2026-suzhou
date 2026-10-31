// 信息密度版的屏幕（盯盘 / 单股 / 起床后 / 天气 / 市场天气）：吃的是协议里真实的 face card（场景.md，v2），
// 字段没有就不画，绝不用假值补；没有数据源的块打「示例」角标。face.js 在"紧凑 / 专业"模式下调用；dense.html（原型页）共用这里的小部件。
// 样式在 dense-views.css（由 tools/make_dense_views_css.py 从 dense.css 生成，类名统一加 dv- 前缀，不和 screen.css 撞名）。

import { SAMPLES } from './dense-samples.js';

export const esc = (s = '') => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
export const smp = '<i class="smp">示例</i>';
const LD = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十','十一','十二','十三','十四','十五','十六','十七','十八','十九','二十','廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'];
export const lunarOf = (d) => { const p = new Intl.DateTimeFormat('zh-CN-u-ca-chinese', { month: 'long', day: 'numeric' }).formatToParts(d); return p.find((x) => x.type === 'month').value + LD[+p.find((x) => x.type === 'day').value - 1]; };
export const f2 = (v) => Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
export const sg = (v) => (v > 0 ? '▲' : v < 0 ? '▼' : '–');
export const pct = (v, plus = true) => `<span class="pct ${cls(v)}">${sg(v)} ${v > 0 && plus ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}%</span>`;
export const pctS = (v) => `<span class="pct ${cls(v)}">${sg(v)}${Math.abs(v).toFixed(2)}%</span>`;   // 指数条里用，省一个符号位

// ---------- 图 ----------
export function spark(points, pre, area = false) {
  const lo = Math.min(...points, pre), hi = Math.max(...points, pre), span = hi - lo || 1, n = points.length;
  const X = (i) => (i / (n - 1)) * 100, Y = (v) => 28 - ((v - lo) / span) * 26 - 1;
  const line = points.map((v, i) => `${X(i).toFixed(2)},${Y(v).toFixed(2)}`).join(' ');
  const color = points[n - 1] >= pre ? 'var(--up)' : 'var(--down)';
  return `<svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
    <line x1="0" x2="100" y1="${Y(pre)}" y2="${Y(pre)}" stroke="var(--faint)" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>
    ${area ? `<polygon points="0,${Y(pre)} ${line} 100,${Y(pre)}" fill="${color}" opacity=".10"/>` : ''}
    <polyline points="${line}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
}
export const rangeBar = (lo, hi, v, open) => {
  const p = (x) => `${Math.min(100, Math.max(0, ((x - lo) / (hi - lo || 1)) * 100)).toFixed(1)}%`;
  return `<div class="rng"><b style="left:0;width:100%"></b>${open != null ? `<i style="left:${p(open)};background:var(--faint)"></i>` : ''}<i style="left:${p(v)}"></i></div>`;
};
export function line24(vals, now) {
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1, n = vals.length;
  const X = (i) => (i / (n - 1)) * 100, Y = (v) => 26 - ((v - lo) / span) * 22 - 2;
  const pts = vals.map((v, i) => `${X(i).toFixed(2)},${Y(v).toFixed(2)}`).join(' ');
  return `<svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
    <polygon points="0,28 ${pts} 100,28" fill="var(--ink)" opacity=".07"/>
    <polyline points="${pts}" fill="none" stroke="var(--ink)" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    ${now != null ? `<line x1="${X(now)}" x2="${X(now)}" y1="0" y2="28" stroke="var(--accent)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>` : ''}</svg>`;
}

// ---------- 状态栏 ----------
const hhmm = () => new Date().toTimeString().slice(0, 5);
const MARKET_MODE = { 休市: 'closed', 盘前: 'pre', 交易中: 'live', 午休: 'closed', 已收盘: 'close' };
const MODE_TEXT = { live: '实时', replay: '回放', close: '收盘', sample: '示例', estimate: '估算' };

// mode：圆点颜色（live / replay 用 accent）；label：左边的字；scene：{page, of, clock}（场景引擎在跑才有页码点和回放时钟）
export function barHtml(mode, label, asof, scene) {
  const of = scene && scene.of > 1 ? Math.min(scene.of, 8) : 0;
  const dots = of ? `<span class="dots">${Array.from({ length: of }, (_, i) => `<i class="${i + 1 === scene.page ? 'on' : ''}"></i>`).join('')}</span>` : '';
  return `<div class="bar" data-mode="${esc(mode)}" data-label="${esc(label)}" data-asof="${esc(asof)}"><span class="mode ${esc(mode)}">${esc(label)}</span><span class="t">${esc(scene?.clock || hhmm())}</span><span class="asof lo">${esc(asof)}</span>${dots}</div>`;
}

// 类名统一加 dv- 前缀（dense-views.css 同样处理），所以不会和 screen.css 里的 .live / .dots / .row 等撞名
export const ns = (html) => html.replace(/class="([^"]*)"/g, (_, c) => `class="${c.split(/\s+/).filter(Boolean).map((t) => `dv-${t}`).join(' ')}"`);

// 场景页码 / 回放时钟变了：只换状态栏，不重画整屏
export function updateBar(root, scene) {
  const bar = root.querySelector('.dv-bar');
  if (!bar) return;
  const d = bar.dataset;
  bar.outerHTML = ns(barHtml(d.mode, d.label, d.asof, scene));
}

const has = (v) => v != null && v !== '';
const num = (v) => Number(v);

// ---------- 盯盘 ----------
function watch(c, scene) {
  const mode = c.sample ? 'sample' : c.mode ?? 'close';
  const rows = (c.rows ?? []).slice(0, 5);
  const idxs = (c.indices?.length ? c.indices : c.index ? [c.index] : []).slice(0, 4);
  const idx = idxs.length
    ? `<div class="idx">${idxs.map((x) => `<div><span class="lbl">${esc(x.name)}</span><span class="vp">${has(x.value) ? `<span class="v">${num(x.value).toFixed(1)}</span>` : ''}${pctS(num(x.pct ?? 0))}</span></div>`).join('')}</div>` : '';
  const body = rows.map((s, i) => {
    const p = num(s.pct ?? 0), pre = has(s.prev_close) ? num(s.prev_close) : s.spark?.[0];
    const sp = s.spark?.length >= 2 && pre != null ? spark(s.spark, pre) : '';
    const rng = has(s.high) && has(s.low) && has(s.price) ? rangeBar(num(s.low), num(s.high), num(s.price), has(s.open) ? num(s.open) : null) : '';
    const sub3 = [s.alert ? '异动' : '', has(s.amp) ? `振幅 ${num(s.amp).toFixed(1)}%` : ''].filter(Boolean).join(' · ');
    return `
    <div class="wr r${i + 1} ${s.alert ? 'alert' : ''}">
      <div class="c1"><span class="nm">${s.alert ? '<i class="alertdot"></i>' : ''}${esc(s.name)}</span><span class="sub">${esc(s.code ?? '')}${has(s.vol_ratio) ? `<span class="bc"> · 量比 ${num(s.vol_ratio).toFixed(1)}</span>` : ''}</span></div>
      <div class="c2"><span class="big">${has(s.price) ? f2(s.price) : ''}</span>${has(s.amount) ? `<span class="sub bc">额 ${num(s.amount).toFixed(1)}亿</span>` : ''}</div>
      <div class="c3">${pct(p)}${sub3 ? `<span class="sub bc">${sub3}</span>` : ''}</div>
      <div class="c4"><div class="sp">${sp}</div>${rng ? `<div class="c">${rng}</div>` : ''}</div>
    </div>`;
  }).join('');
  const avg = has(c.avg_pct) ? num(c.avg_pct) : rows.length ? rows.reduce((a, s) => a + num(s.pct ?? 0), 0) / rows.length : null;
  const legal = mode === 'sample' ? '示例数据 · 不构成投资建议' : 'PandaAI · 不构成投资建议';
  return `${barHtml(mode, MODE_TEXT[mode] ?? '', c.asof ?? '', scene)}
    <div class="body">${idx}<div class="rows">${body || '<div class="sub" style="padding:8px 0">自选里还没有股票</div>'}</div>
    <div class="foot">${avg != null ? `<span>自选均值</span>${pct(avg)}` : ''}<span class="ml lo">${legal}</span></div></div>`;
}

// ---------- 单股 ----------
function mkt(c, scene) {
  const mode = c.sample ? 'sample' : c.mode ?? 'close';
  const p = num(c.pct ?? 0), hasPrice = has(c.price);
  const pre = has(c.prev_close) ? num(c.prev_close) : c.spark?.[0];
  const kv = (k, v, color = '', extra = '') => `<span class="k ${extra}">${k}</span><span class="v ${extra}">${color ? `<span class="${color}">${v}</span>` : v}</span>`;
  const stats = [
    has(c.open) && kv('开盘', f2(c.open), pre != null ? cls(num(c.open) - pre) : ''),
    has(c.high) && kv('最高', f2(c.high), pre != null ? cls(num(c.high) - pre) : ''),
    has(c.low) && kv('最低', f2(c.low), pre != null ? cls(num(c.low) - pre) : ''),
    has(c.prev_close) && kv('昨收', f2(c.prev_close)),
    has(c.volume) && kv('成交量', `${num(c.volume).toLocaleString('en-US', { maximumFractionDigits: 1 })}万手`, '', 'bc'),
    has(c.amount) && kv('成交额', `${num(c.amount).toFixed(1)}亿`),
    has(c.amp) && kv('振幅', `${num(c.amp).toFixed(2)}%`, '', 'bc'),
    has(c.limit_up) && kv('涨停价', f2(c.limit_up), 'up', 'c'),
    has(c.limit_down) && kv('跌停价', f2(c.limit_down), 'down', 'c'),
  ].filter(Boolean).join('');
  const chg = hasPrice && pre != null ? num(c.price) - pre : null;
  const hero = hasPrice
    ? `<span class="p">${f2(c.price)}</span><span class="pc">${sg(p)} ${chg != null ? `${chg >= 0 ? '+' : '−'}${Math.abs(chg).toFixed(2)}<br><span style="font-size:.8em">` : '<span>'}${p >= 0 ? '+' : '−'}${Math.abs(p).toFixed(2)}%</span></span>`
    : `<span class="p">${sg(p)} ${p >= 0 ? '+' : '−'}${Math.abs(p).toFixed(2)}%</span>`;
  const chart = c.spark?.length >= 2 && pre != null ? `<div class="chart">${spark(c.spark, pre, true)}</div><div class="axis"><span>09:30</span><span class="lo">11:30</span><span class="lo">13:00</span><span>15:00</span></div>` : '<div class="chart"></div>';
  let strip = '';
  if (c.range20 && hasPrice) {
    const { lo, hi } = c.range20, rp = Math.min(100, Math.max(0, ((num(c.price) - lo) / (hi - lo || 1)) * 100));
    strip = `<div class="strip c"><div><div class="row spread"><span class="lbl">20 日区间</span><span class="sub num">${f2(lo)} – ${f2(hi)}</span></div>
      <div class="rng"><b style="left:0;width:100%"></b><i style="left:${rp.toFixed(1)}%"></i></div></div></div>`;
  }
  return `${barHtml(mode, MODE_TEXT[mode] ?? '', c.asof ?? '', scene)}
    <div class="body"><div class="mk">
      <div class="l">
        <div class="row"><span class="nm">${c.alert ? '<i class="alertdot"></i>' : ''}${esc(c.name ?? '')}</span><span class="sub">${esc(c.code ?? '')}</span>${c.alert ? '<span class="chip solid">异动</span>' : ''}${has(c.vol_ratio) ? `<span class="sub ml bc">量比 ${num(c.vol_ratio).toFixed(1)}</span>` : ''}</div>
        <div class="hero ${cls(p)}">${hero}</div>
        ${chart}
      </div>
      <div class="stats">${stats}</div>
    </div>${strip}</div>`;
}

// ---------- 起床后 ----------
const weekday = (w) => (!w ? '' : String(w).startsWith('周') ? w : `周${w}`);

function today(c, scene) {
  const w = c.wx ?? null, sm = c.sample ?? {};
  const market = c.market ?? '';
  const mode = MARKET_MODE[market] ?? 'closed';
  const asof = c.next_open && market === '休市' ? `下次开盘 ${c.next_open}` : '';
  const lunar = c.lunar ?? lunarOf(new Date());
  const t = w?.temp ?? c.temp, word = w?.text ?? c.text;
  const kvRows = [];
  if (w) {
    if (has(w.feels) || has(w.humidity)) kvRows.push(['体感', [has(w.feels) && `${w.feels}°`, has(w.humidity) && `湿度 ${w.humidity}%`].filter(Boolean).join(' · ')]);
    if (has(w.lo) && has(w.hi)) kvRows.push(['今天', `${w.lo}–${w.hi}°${has(w.rain) ? ` · 雨 ${w.rain}%` : ''}`]);
    if (has(w.wind)) kvRows.push(['风', w.wind, 'bc sh']);
    if (has(w.aqi)) kvRows.push(['空气', `AQI ${w.aqi}${w.aqi_text ? ` · ${w.aqi_text}` : ''}`, 'bc sh']);
    if (has(w.uv)) kvRows.push(['紫外线', `${w.uv} 级`, 'c sh']);
    if (has(w.sunrise)) kvRows.push(['日出落', `${w.sunrise} / ${w.sunset ?? ''}`, 'c sh']);
    if (has(w.tmr_text)) kvRows.push(['明天', `${w.tmr_text} ${w.tmr_lo}–${w.tmr_hi}°`]);
  } else if (has(c.tmr_text)) kvRows.push(['明天', `${c.tmr_text} ${c.tmr_lo}–${c.tmr_hi}°`]);
  const hourly = w?.hourly?.length >= 2 ? `<div class="bc lo" style="height:22px;margin-top:auto">${line24(w.hourly, new Date().getHours())}</div>` : '';
  // 日程：v2 有 events[]；旧卡片只有 next_*，就当一条
  const evs = c.events?.length ? c.events.slice(0, 3) : c.next_title ? [{ time: c.next_time ?? '', title: c.next_title }] : [];
  const evHtml = evs.length
    ? evs.map((e, i) => `<div class="ev ${i === 0 ? 'next' : ''} ${i === 1 ? 'bc' : ''} ${i === 2 ? 'c' : ''}"><span class="tm">${esc(e.time ?? '')}</span><span class="tt">${esc(e.title ?? '')}</span></div>`).join('')
    : '<div class="sub">今天没有会议了</div>';
  const fx = (c.fx ?? []).slice(0, 3);
  const fxHtml = fx.length ? `<div class="hd lo c" style="margin-top:2px"><span>汇率</span><span>ECB 日终</span></div>
    <div class="lo c">${fx.map((x) => `<div class="fxr"><span class="sub">${x.per ? `${x.per}${String(x.pair).split('/')[0]}` : esc(x.pair)}</span><span class="v">${num(x.rate).toFixed(x.per ? 2 : 4)} ${pctS(num(x.pct ?? 0))}</span></div>`).join('')}</div>` : '';
  const last = c.last_idx
    ? `<div class="c lo" style="margin-top:auto"><span class="lbl">上一交易日${c.last_idx.sample ? smp : ''}</span><div class="row" style="gap:6px;margin-top:3px"><span class="sub">${esc(c.last_idx.name)}</span><span class="num nm">${has(c.last_idx.value) ? num(c.last_idx.value).toFixed(1) : ''}</span>${pctS(num(c.last_idx.pct ?? 0))}</div></div>` : '';
  const on = c.overnight ?? [];
  return `${barHtml(mode, market, asof, scene)}
    <div class="body"><div class="g t3">
      <div class="col date">
        <span class="lbl">${esc(c.month ?? '')} 月 · ${esc(weekday(c.weekday))}</span>
        <span class="d">${esc(c.day ?? '')}</span>
        <span class="sub c">农历 ${esc(lunar)}</span>
        ${market ? `<div class="row"><span class="chip">${esc(market)}</span></div>` : ''}
        ${c.next_open ? `<span class="sub bc sh">下次开盘 ${esc(c.next_open)}${c.open_in ? `<br>还有 ${esc(c.open_in)}` : ''}</span>` : ''}
        ${last}
      </div>
      <div class="col">
        <div class="row"><span class="lbl">${esc(c.city ?? '')}</span></div>
        <div class="row"><span class="hero"><span class="p num" style="font:500 var(--fh)/.9 var(--mono);letter-spacing:-.05em">${has(t) ? `${t}°` : ''}</span></span><span class="nm">${esc(word ?? '')}</span></div>
        <div class="kv">${kvRows.map(([k, v, x = '']) => `<span class="k ${x}">${k}</span><span class="v ${x}">${esc(v)}</span>`).join('')}</div>
        ${hourly}
      </div>
      <div class="col blk">
        <div class="hd"><span>日程${sm.events ? smp : ''}</span><span class="num">${evs.length}</span></div>
        ${evHtml}
        ${fxHtml}
      </div>
    </div>
    ${c.brief ? `<div class="brief bc"><b>盘前简报</b>${esc(c.brief)}</div>` : ''}
    ${on.length ? `<div class="foot c blk"><span>隔夜外盘${sm.overnight ? smp : ''}</span>${on.map((o) => `<span class="sub">${esc(o.name)}</span>${pct(num(o.pct ?? 0))}`).join('')}</div>` : ''}</div>`;
}

// ---------- 天气 ----------
function sky(c, scene) {
  const hasHourly = c.hourly?.length >= 2, hasRain = c.rain_hourly?.length >= 2;
  const kvRows = [
    has(c.feels) && ['体感', `${c.feels}°`],
    has(c.lo) && has(c.hi) && ['今天', `${c.lo}–${c.hi}°`],
    has(c.humidity) && ['湿度', `${c.humidity}%`],
    has(c.wind) && ['风', `${c.wind_dir ?? ''} ${c.wind} 级`.trim(), 'bc sh'],
    has(c.aqi) && ['AQI', `${c.aqi}${c.aqi_text ? ` · ${c.aqi_text}` : ''}${has(c.pm25) ? ` · PM2.5 ${c.pm25}` : ''}`, 'bc'],
    has(c.uv) && ['紫外线', `${c.uv} 级`, 'c sh'],
    has(c.sunrise) && ['日出落', `${c.sunrise} / ${c.sunset ?? ''}`, 'c sh'],
  ].filter(Boolean);
  const hour = new Date().getHours();
  const right = hasHourly || hasRain ? `
      <div class="col">
        ${hasHourly ? `<div class="hd"><span>气温 °C</span><span class="num">${Math.min(...c.hourly)}–${Math.max(...c.hourly)}</span></div>
        <div class="chart" style="min-height:44px">${line24(c.hourly, hour)}</div>
        <div class="axis"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>` : ''}
        ${hasRain ? `<div class="hd bc"><span>降水概率 %</span>${has(c.tmr_rain) ? `<span class="num">明天 ${c.tmr_rain}</span>` : ''}</div>
        <div class="chart bc" style="max-height:32px"><div class="tbar">${c.rain_hourly.map((v, i) => `<i class="${i === hour ? 'now' : ''}" style="height:${Math.max(4, v)}%"></i>`).join('')}</div></div>` : ''}
      </div>` : '';
  return `${barHtml('close', '天气', `${c.city ?? ''} · ${hasHourly ? '24 小时' : '现在'}`, scene)}
    <div class="body"><div class="g t2" style="grid-template-columns:${right ? '.9fr 1.1fr' : '1fr'}">
      <div class="col">
        <div class="row" style="align-items:flex-end"><span class="hero"><span class="p num" style="font:500 var(--fh)/.9 var(--mono);letter-spacing:-.05em">${has(c.temp) ? `${c.temp}°` : ''}</span></span><span class="nm">${esc(c.text ?? '')}</span></div>
        <div class="kv">${kvRows.map(([k, v, x = '']) => `<span class="k ${x}">${k}</span><span class="v ${x}">${esc(v)}</span>`).join('')}</div>
      </div>${right}
    </div>
    ${c.advice ? `<div class="brief"><b>建议</b>${esc(c.advice)}${c.tmr_text ? ` · 明天 ${esc(c.tmr_text)} ${c.tmr_lo}–${c.tmr_hi}°` : ''}</div>` : ''}</div>`;
}

// ---------- 市场天气（涨跌家数） ----------
function market(c, scene) {
  const up = num(c.up ?? 0), down = num(c.down ?? 0), flat = num(c.flat ?? 0), tot = up + down + flat || 1;
  const share = Math.round((up / (up + down || 1)) * 100);
  const approx = c.mode === 'estimate' || c.mode === 'sample';
  const tag = approx ? smp : '';
  const limits = has(c.limit_up_n) || has(c.limit_down_n)
    ? `<div class="row spread c" style="margin-top:4px"><span class="sub">涨停 <b class="up num">${c.limit_up_n ?? '–'}</b></span><span class="sub">跌停 <b class="down num">${c.limit_down_n ?? '–'}</b></span></div>` : '';
  return `${barHtml(c.mode === 'sample' ? 'sample' : 'close', c.mode === 'estimate' ? '估算' : c.mode === 'sample' ? '示例' : '收盘', c.time ?? '', scene)}
    <div class="body"><div class="g t2">
      <div class="col">
        <span class="lbl">市场天气</span>
        <div class="row" style="align-items:flex-end;gap:10px"><span class="hero"><span class="p">${share}</span></span><span class="nm">${esc(c.word ?? '')}</span></div>
        <span class="sub">上涨家数占比 %</span>
      </div>
      <div class="col">
        <div class="hd"><span>涨跌家数${tag}</span><span class="num"><span class="up">▲ ${up}</span> · <span class="down">▼ ${down}</span></span></div>
        <div class="bs" style="margin-top:4px"><i style="width:${(up / tot) * 100}%;background:var(--up)"></i>${flat ? `<i style="width:${(flat / tot) * 100}%;background:var(--faint)"></i>` : ''}<i style="flex:1;background:var(--down)"></i></div>
        ${flat ? `<span class="sub bc">平盘 ${flat}</span>` : ''}
        ${limits}
      </div>
    </div>
    <div class="foot"><span class="lo">${c.mode === 'sample' ? '示例数据 · ' : 'PandaAI 日线 · '}不构成投资建议</span></div></div>`;
}

const VIEWS = { watch, mkt, today, sky, weather: market };
export const DENSE_STATES = Object.keys(VIEWS);
export const DENSITY_D = { compact: 'B', pro: 'C' };   // 简洁（simple）不在这里：它用 face.js 原来的大字视图

// density：'compact' | 'pro'。返回整屏 HTML（外层 .dv 带 data-d，字号和层级由 dense-views.css 决定）
export function denseView(state, card, density, scene) {
  const v = VIEWS[state];
  if (!v) return null;
  const c = card && Object.keys(card).length ? card : SAMPLES[state];   // 空卡片（状态按钮）：用带「示例」标记的示例
  return `<div class="dv" data-d="${DENSITY_D[density] ?? 'C'}">${ns(v(c, scene))}</div>`;
}
