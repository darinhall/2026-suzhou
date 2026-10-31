// 信息密度原型：5 张屏 × 3 档密度 × 2 种尺寸。数据在 dense-data.js；每个 .smp 角标 = 现在没有数据源的"示例"字段。
import { WATCH, INDICES, BREADTH, WEATHER, FX, OVERNIGHT, EVENTS, BRIEF } from './dense-data.js';

const $ = (s, r = document) => r.querySelector(s);
const esc = (s = '') => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const smp = '<i class="smp">示例</i>';
const LD = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十','十一','十二','十三','十四','十五','十六','十七','十八','十九','二十','廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'];
const lunarOf = (d) => { const p = new Intl.DateTimeFormat('zh-CN-u-ca-chinese', { month: 'long', day: 'numeric' }).formatToParts(d); return p.find((x) => x.type === 'month').value + LD[+p.find((x) => x.type === 'day').value - 1]; };
const f2 = (v) => Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const sg = (v) => (v > 0 ? '▲' : v < 0 ? '▼' : '–');
const pct = (v, plus = true) => `<span class="pct ${cls(v)}">${sg(v)} ${v > 0 && plus ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}%</span>`;
const pctS = (v) => `<span class="pct ${cls(v)}">${sg(v)}${Math.abs(v).toFixed(2)}%</span>`;   // 指数条里用，省一个符号位

// ---------- 图 ----------
function spark(points, pre, area = false) {
  const lo = Math.min(...points, pre), hi = Math.max(...points, pre), span = hi - lo || 1, n = points.length;
  const X = (i) => (i / (n - 1)) * 100, Y = (v) => 28 - ((v - lo) / span) * 26 - 1;
  const line = points.map((v, i) => `${X(i).toFixed(2)},${Y(v).toFixed(2)}`).join(' ');
  const color = points[n - 1] >= pre ? 'var(--up)' : 'var(--down)';
  return `<svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
    <line x1="0" x2="100" y1="${Y(pre)}" y2="${Y(pre)}" stroke="var(--faint)" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>
    ${area ? `<polygon points="0,${Y(pre)} ${line} 100,${Y(pre)}" fill="${color}" opacity=".10"/>` : ''}
    <polyline points="${line}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
}
const rangeBar = (lo, hi, v, open) => {
  const p = (x) => `${(((x - lo) / (hi - lo || 1)) * 100).toFixed(1)}%`;
  return `<div class="rng"><b style="left:0;width:100%"></b>${open != null ? `<i style="left:${p(open)};background:var(--faint)"></i>` : ''}<i style="left:${p(v)}"></i></div>`;
};
function line24(vals, now) {
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1, n = vals.length;
  const X = (i) => (i / (n - 1)) * 100, Y = (v) => 26 - ((v - lo) / span) * 22 - 2;
  const pts = vals.map((v, i) => `${X(i).toFixed(2)},${Y(v).toFixed(2)}`).join(' ');
  return `<svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
    <polygon points="0,28 ${pts} 100,28" fill="var(--ink)" opacity=".07"/>
    <polyline points="${pts}" fill="none" stroke="var(--ink)" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    <line x1="${X(now)}" x2="${X(now)}" y1="0" y2="28" stroke="var(--accent)" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
}

// ---------- 状态栏 ----------
function bar(mode, time, asof, page, of) {
  const names = { live: '实时', replay: '回放', close: '收盘', closed: '休市', pre: '盘前' };
  return `<div class="bar"><span class="mode ${mode}">${names[mode]}</span><span class="t">${time}</span><span class="asof lo">${asof}</span>
    <span class="dots">${Array.from({ length: of }, (_, i) => `<i class="${i === page ? 'on' : ''}"></i>`).join('')}</span></div>`;
}

// ---------- 1 盯盘 ----------
function watch() {
  const idx = INDICES.map((x) => `<div><span class="lbl">${x.name}</span><span class="vp"><span class="v">${x.val.toFixed(1)}</span>${pctS(x.pct)}</span></div>`).join('');
  const rows = WATCH.map((s, i) => `
    <div class="wr r${i + 1} ${s.alert ? 'alert' : ''}">
      <div class="c1"><span class="nm">${s.alert ? '<i class="alertdot"></i>' : ''}${s.name}</span><span class="sub">${s.code}<span class="bc"> · 量比 ${s.vr.toFixed(1)}</span></span></div>
      <div class="c2"><span class="big">${f2(s.price)}</span><span class="sub bc">额 ${s.amt.toFixed(1)}亿</span></div>
      <div class="c3">${pct(s.pct)}<span class="sub bc">${s.alert ? '异动 · ' : ''}振幅 ${s.amp.toFixed(1)}%</span></div>
      <div class="c4"><div class="sp">${spark(s.spark, s.pre)}</div><div class="c">${rangeBar(s.low, s.high, s.price, s.open)}</div></div>
    </div>`).join('');
  const avg = WATCH.reduce((a, s) => a + s.pct, 0) / WATCH.length;
  return `${bar('replay', '10:35', '回放 10-30 · 5 分钟线', 1, 5)}
    <div class="body"><div class="idx">${idx}</div><div class="rows">${rows}</div>
    <div class="foot"><span>自选均值</span>${pct(avg)}<span class="ml lo">PandaAI · 不构成投资建议</span></div></div>`;
}

// ---------- 2 单股 ----------
function mkt() {
  const s = WATCH[0];
  const kv = (k, v, c = '', extra = '') => `<span class="k ${extra}">${k}</span><span class="v ${extra}">${c ? `<span class="${c}">${v}</span>` : v}</span>`;
  const [r0, r1] = s.r20, rp = ((s.price - r0) / (r1 - r0)) * 100;
  return `${bar('close', '15:00', '收盘 10-30 · 5 分钟线', 2, 5)}
    <div class="body"><div class="mk">
      <div class="l">
        <div class="row"><span class="nm">${s.name}</span><span class="sub">${s.code}.SZ</span><span class="sub ml bc">量比 ${s.vr.toFixed(1)}</span></div>
        <div class="hero ${cls(s.chg)}"><span class="p">${f2(s.price)}</span><span class="pc">${sg(s.chg)} ${s.chg > 0 ? '+' : '−'}${Math.abs(s.chg).toFixed(2)}<br><span style="font-size:.8em">${s.pct > 0 ? '+' : '−'}${Math.abs(s.pct).toFixed(2)}%</span></span></div>
        <div class="chart">${spark(s.spark, s.pre, true)}</div>
        <div class="axis"><span>09:30</span><span class="lo">11:30</span><span class="lo">13:00</span><span>15:00</span></div>
      </div>
      <div class="stats">
        ${kv('开盘', f2(s.open), cls(s.open - s.pre))}${kv('最高', f2(s.high), cls(s.high - s.pre))}${kv('最低', f2(s.low), cls(s.low - s.pre))}${kv('昨收', f2(s.pre))}
        ${kv('成交量', `${s.vol.toLocaleString('en-US')}万股`, '', 'bc')}${kv('成交额', `${s.amt.toFixed(1)}亿`)}${kv('振幅', `${s.amp.toFixed(2)}%`, '', 'bc')}
        ${kv('涨停价', f2(s.lu), 'up', 'c')}${kv('跌停价', f2(s.ld), 'down', 'c')}
      </div>
    </div>
    <div class="strip c">
      <div><div class="row spread"><span class="lbl">20 日区间</span><span class="sub num">${f2(r0)} – ${f2(r1)}</span></div>
        <div class="rng"><b style="left:0;width:100%"></b><i style="left:${rp.toFixed(1)}%"></i></div></div>
      <div class="blk"><div class="row spread"><span class="lbl">市场宽度${smp}</span><span class="sub num">${BREADTH.up} : ${BREADTH.down}</span></div>
        <div class="bs"><i style="width:${(BREADTH.up / (BREADTH.up + BREADTH.down)) * 100}%;background:var(--up)"></i><i style="flex:1;background:var(--down)"></i></div></div>
    </div></div>`;
}

// ---------- 3 起床后 ----------
function today() {
  const w = WEATHER, ev = EVENTS;
  const lunar = lunarOf(new Date(2026, 9, 31));
  return `${bar('closed', '07:30', '休市 · 下一交易日 11-03 周一', 0, 5)}
    <div class="body"><div class="g t3">
      <div class="col date">
        <span class="lbl">10 月 · 周六</span>
        <span class="d">31</span>
        <span class="sub c">农历 ${lunar}</span>
        <div class="row"><span class="chip">休市</span></div>
        <span class="sub bc sh">下次开盘 11-03 09:30<br>还有 2 天 2 小时</span>
        <div class="c lo" style="margin-top:auto"><span class="lbl">上一交易日</span><div class="row" style="gap:6px;margin-top:3px"><span class="sub">上证</span><span class="num nm">3296.5</span>${pctS(0.42)}</div></div>
      </div>
      <div class="col">
        <div class="row"><span class="lbl">${w.city} · ${w.time}</span></div>
        <div class="row"><span class="hero"><span class="p num" style="font:500 var(--fh)/.9 var(--mono);letter-spacing:-.05em">${w.temp}°</span></span><span class="nm">${w.text}</span></div>
        <div class="kv">
          <span class="k">体感</span><span class="v">${w.feels}° · 湿度 ${w.humidity}%</span>
          <span class="k">今天</span><span class="v">${w.lo}–${w.hi}° · 雨 ${w.rain}%</span>
          <span class="k bc sh">风</span><span class="v bc sh">${w.windDir} ${w.wind} 级</span>
          <span class="k bc sh">空气</span><span class="v bc sh">AQI ${w.aqi} · 良</span>
          <span class="k c sh">紫外线</span><span class="v c sh">${w.uv} 级</span>
          <span class="k c sh">日出落</span><span class="v c sh">${w.sunrise} / ${w.sunset}</span>
          <span class="k">明天</span><span class="v">${w.tmr.text} ${w.tmr.lo}–${w.tmr.hi}°</span>
        </div>
        <div class="bc lo" style="height:22px;margin-top:auto">${line24(w.hourly, 7)}</div>
      </div>
      <div class="col blk">
        <div class="hd"><span>日程${smp}</span><span class="num">${ev.length}</span></div>
        ${ev.map((e, i) => `<div class="ev ${i === 0 ? 'next' : ''} ${i === 1 ? 'bc' : ''} ${i === 2 ? 'c' : ''}"><span class="tm">${e.time}</span><span class="tt">${e.title}</span></div>`).join('')}
        <div class="hd lo c" style="margin-top:2px"><span>汇率</span><span>ECB 日终</span></div>
        <div class="lo c">${FX.map((x) => `<div class="fxr"><span class="sub">${x.scale ? '100JPY' : x.pair}</span><span class="v">${(x.val * (x.scale || 1)).toFixed(x.scale ? 2 : 4)} ${pctS(x.chg)}</span></div>`).join('')}</div>
      </div>
    </div>
    <div class="brief bc"><b>盘前简报</b>${esc(BRIEF)}</div>
    <div class="foot c blk"><span>隔夜外盘${smp}</span>${OVERNIGHT.map((o) => `<span class="sub">${o.name}</span>${pct(o.pct)}`).join('')}</div></div>`;
}

// ---------- 4 天气 ----------
function sky() {
  const w = WEATHER;
  return `${bar('closed', '07:30', `${w.city} · 24 小时`, 1, 5)}
    <div class="body"><div class="g t2" style="grid-template-columns:.9fr 1.1fr">
      <div class="col">
        <div class="row" style="align-items:flex-end"><span class="hero"><span class="p num" style="font:500 var(--fh)/.9 var(--mono);letter-spacing:-.05em">${w.temp}°</span></span><span class="nm">${w.text}</span></div>
        <div class="kv">
          <span class="k">体感</span><span class="v">${w.feels}°</span>
          <span class="k">今天</span><span class="v">${w.lo}–${w.hi}°</span>
          <span class="k">湿度</span><span class="v">${w.humidity}%</span>
          <span class="k bc sh">风</span><span class="v bc sh">${w.windDir} ${w.wind} 级</span>
          <span class="k bc">AQI</span><span class="v bc">${w.aqi} · PM2.5 ${w.pm25}</span>
          <span class="k c sh">紫外线</span><span class="v c sh">${w.uv} 级</span>
          <span class="k c sh">日出落</span><span class="v c sh">${w.sunrise} / ${w.sunset}</span>
        </div>
      </div>
      <div class="col">
        <div class="hd"><span>气温 °C</span><span class="num">${Math.min(...w.hourly)}–${Math.max(...w.hourly)}</span></div>
        <div class="chart" style="min-height:44px">${line24(w.hourly, 7)}</div>
        <div class="axis"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>
        <div class="hd bc"><span>降水概率 %</span><span class="num">明天 ${w.tmr.rain}</span></div>
        <div class="chart bc" style="max-height:32px"><div class="tbar">${w.rainHourly.map((v, i) => `<i class="${i === 7 ? 'now' : ''}" style="height:${Math.max(4, v)}%"></i>`).join('')}</div></div>
      </div>
    </div>
    <div class="brief"><b>建议</b>${esc(w.advice)} · 明天 ${w.tmr.text} ${w.tmr.lo}–${w.tmr.hi}°</div></div>`;
}

// ---------- 5 收盘 ----------
function close() {
  const top = [...WATCH].sort((a, b) => b.pct - a.pct)[0], bt = BREADTH, tot = bt.up + bt.down;
  const amt = INDICES[0].amt + INDICES[1].amt;
  return `${bar('close', '15:00', '收盘 10-30', 4, 5)}
    <div class="body"><div class="g t2">
      <div class="col">
        <div class="hd"><span>指数</span><span class="bc lo">成交额(亿)</span></div>
        ${INDICES.map((x, i) => `<div class="ir ${i === 3 ? 'bc' : ''}" style="grid-template-columns:1fr 1.1fr 1fr auto"><span class="nm" style="font-size:var(--fs)">${x.name}</span><span class="vv">${f2(x.val)}</span>${pctS(x.pct)}<span class="vv sub bc lo">${x.amt.toLocaleString('en-US')}</span></div>`).join('')}
        <div class="row spread"><span class="lbl">两市成交额</span><span class="num nm">${amt.toLocaleString('en-US')}亿</span></div>
      </div>
      <div class="col">
        <div class="blk"><div class="row spread"><span class="lbl">涨跌家数${smp}</span><span class="num sub"><span class="up">▲ ${bt.up}</span> · <span class="down">▼ ${bt.down}</span></span></div>
          <div class="bs" style="margin-top:4px"><i style="width:${(bt.up / tot) * 100}%;background:var(--up)"></i><i style="flex:1;background:var(--down)"></i></div>
          <div class="row spread c" style="margin-top:4px"><span class="sub">涨停 <b class="up num">${bt.lu}</b></span><span class="sub">跌停 <b class="down num">${bt.ld}</b></span></div></div>
        <div class="hd"><span>自选</span><span class="lo">今日</span></div>
        ${WATCH.map((s, i) => `<div class="ir r${i + 1}" style="grid-template-columns:1.2fr 1fr 1fr"><span class="nm" style="font-size:var(--fs)">${s.name}</span><span class="vv">${f2(s.price)}</span>${pctS(s.pct)}</div>`).join('')}
        <div class="loud row spread bc" style="margin-top:auto"><span class="lbl">最强</span><span class="nm" style="font-size:var(--fs)">${top.name}</span>${pct(top.pct)}</div>
      </div>
    </div>
    <div class="foot"><span class="lo">PandaAI 日线 · 不构成投资建议</span></div></div>`;
}

const SCREENS = { watch: ['盯盘', watch], mkt: ['单股', mkt], today: ['起床后', today], sky: ['天气', sky], close: ['收盘', close] };
const DENS = { A: '标准', B: '紧凑', C: '专业' };
const PHYS = { l: 480 / 165 * 96 / 480, s: 320 / 143 * 96 / 320 };   // 3.5″ 165 ppi / 2.8″ 143 ppi → 1 屏幕像素 = ? CSS 像素

const st = Object.assign({ screen: 'watch', d: 'C', size: 'l', mode: 'compare', theme: 'light', pg: 'auto' }, Object.fromEntries(new URLSearchParams(location.search)));

function frame(screen, d, size, scale, label) {
  const [W, H] = size === 'l' ? [480, 320] : [320, 240];
  const fig = document.createElement('figure');
  fig.className = 'fig';
  fig.innerHTML = `<figcaption>${label}</figcaption><div class="frame" style="width:${W * scale}px;height:${H * scale}px"><div class="ds" data-d="${d}" data-size="${size}" data-theme="${st.theme}" style="transform:scale(${scale})">${SCREENS[screen][1]()}</div></div>`;
  return fig;
}

function render() {
  const wall = $('#wall');
  wall.innerHTML = '';
  const s = st.screen, name = SCREENS[s][0];
  const cap = {
    compare: `${name} · 三档密度，480×320，1:1 像素`,
    sizes: `${name} · 密度 ${st.d}（${DENS[st.d]}）· 两种屏幕`,
    real: `${name} · 密度 ${st.d} · 按真实物理大小（3.5″ ≈ 165 ppi，2.8″ ≈ 143 ppi；屏幕离眼睛一臂远 ≈ 50 cm 来看）`,
    far: `${name} · 密度 ${st.d} · "远看一眼"：真实大小的 0.5×（≈ 1 m 外）`,
  }[st.mode];
  $('#cap').textContent = cap;
  if (st.mode === 'compare') for (const d of 'ABC') wall.append(frame(s, d, 'l', 1, `<b>${d}</b> ${DENS[d]}`));
  else if (st.mode === 'sizes') { wall.append(frame(s, st.d, 'l', 1, '<b>3.5″</b> 480×320')); wall.append(frame(s, st.d, 's', 1, '<b>2.8″</b> 320×240')); }
  else {
    const k = st.mode === 'far' ? 0.5 : 1;
    wall.append(frame(s, st.d, 'l', PHYS.l * k, `<b>3.5″</b> ×${(PHYS.l * k).toFixed(2)}`));
    wall.append(frame(s, st.d, 's', PHYS.s * k, `<b>2.8″</b> ×${(PHYS.s * k).toFixed(2)}`));
  }
  document.documentElement.dataset.pg = st.pg === 'auto' ? '' : st.pg;
  for (const [id, key] of [['#seg-screen', 'screen'], ['#seg-mode', 'mode'], ['#seg-d', 'd'], ['#seg-theme', 'theme']])
    $(id).querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === st[key])));
  $('#grp-d').style.display = st.mode === 'compare' ? 'none' : '';
}

function seg(id, key, items) {
  const el = $(id);
  el.innerHTML = items.map(([v, l]) => `<button data-v="${v}" aria-pressed="false">${l}</button>`).join('');
  el.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    st[key] = b.dataset.v;
    if (key === 'theme') st.pg = b.dataset.v;
    const q = new URLSearchParams(st); history.replaceState(null, '', `?${q}`);
    render();
  };
}
seg('#seg-screen', 'screen', Object.entries(SCREENS).map(([k, v]) => [k, v[0]]));
seg('#seg-mode', 'mode', [['compare', '三档对比'], ['sizes', '两种尺寸'], ['real', '真实大小'], ['far', '远看 0.5×']]);
seg('#seg-d', 'd', Object.entries(DENS).map(([k, v]) => [k, `${k} ${v}`]));
seg('#seg-theme', 'theme', [['light', '浅色'], ['dark', '深色']]);
document.fonts?.ready.then(render);
render();
