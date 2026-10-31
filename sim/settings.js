// 设置面板 + 大模式切换条的界面。数据都在 profile.js 的 ProfileSync 里，这里只管画和收集输入。
import { MODES, LIMITS } from './profile.js';

const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const DENSITY = [['simple', '简洁', '大字，一屏一件事，自选 3 只'], ['compact', '紧凑', '多一行成交额 / 振幅，自选 4 只'], ['pro', '专业', '区间条 + 指数条，自选 5 只']];
const TABS = [['display', '显示'], ['watch', '盯盘'], ['weather', '天气'], ['other', '其他']];
const STATE_TEXT = {
  offline: ['', '离线 · 设置存在本机，连上中枢后再同步'],
  pending: ['pend', '保存中…'],
  applied: ['ok', '已同步到中枢 ✓'],
  noreply: ['warn', '中枢没有应答（版本旧？）· 设置只在本机生效'],
};

// ---------- 模式切换条（左栏顶部） ----------
export function mountModes({ root, sync, runnerState }) {
  root.innerHTML = `
    <div class="modes" id="modes">${MODES.map((m, i) => `<button data-mode="${m.id}" title="${esc(m.desc)}"><kbd>${i + 1}</kbd>${m.label}</button>`).join('')}</div>
    <div class="now" id="now" hidden>
      <div class="now-top"><b id="now-mode"></b><span id="now-item"></span><em id="now-n"></em></div>
      <div class="now-bar"><i id="now-fill"></i></div>
      <div class="now-ctl">
        <button data-ctl="prev" title="上一项（←）">‹ 上一项</button>
        <button data-ctl="pause" id="btn-pause" title="暂停 / 继续（P）">⏸ 暂停</button>
        <button data-ctl="next" title="下一项（→）">下一项 ›</button>
      </div>
    </div>
    <p class="note" id="mode-desc"></p>`;
  const $ = (s) => root.querySelector(s);
  let timerStart = 0, timerSec = 0, raf = 0;
  const tick = () => {   // 进度条：这一项停留多久
    const k = timerSec ? Math.min(1, (performance.now() - timerStart) / (timerSec * 1000)) : 0;
    $('#now-fill').style.width = `${k * 100}%`;
    raf = requestAnimationFrame(tick);
  };
  return {
    paint(state) {   // state: {name,page,of,label,item,paused,sec}
      const m = MODES.find((x) => x.id === state?.name);
      root.querySelectorAll('[data-mode]').forEach((b) => b.classList.toggle('on', b.dataset.mode === state?.name));
      const show = !!state?.name && state.name !== 'stop';
      $('#now').hidden = !show;
      $('#mode-desc').textContent = m ? m.desc : show ? (state.label ?? state.name) : '选一个模式，真机和屏幕一起换';
      if (!show) { cancelAnimationFrame(raf); return; }
      $('#now-mode').textContent = state.label ?? m?.label ?? state.name;
      $('#now-item').textContent = state.item ?? '';
      $('#now-n').textContent = state.of > 1 ? `${state.page}/${state.of}` : '';
      $('#btn-pause').textContent = state.paused ? '▶ 继续' : '⏸ 暂停';
      timerStart = performance.now();
      timerSec = state.paused || state.of <= 1 ? 0 : (state.sec ?? runnerState?.sec ?? 0);
      cancelAnimationFrame(raf);
      tick();
    },
  };
}

// ---------- 设置面板（右栏） ----------
export function mountSettings({ root, sync, density, device, onResend }) {
  const ui = { tab: 'display', results: [], addQ: '', cityQ: '', drag: -1 };
  root.innerHTML = '<div class="st-status" id="st-status"></div><div class="seg st-tabs" id="st-tabs"></div><div class="st-pane" id="st-pane"></div>';
  const $ = (s) => root.querySelector(s);

  const fieldErr = (f) => (sync.state === 'error' && sync.error?.field === f ? `<p class="st-err">${esc(sync.error.error)}</p>` : '');
  const slider = (id, label, v, [lo, hi], step, unit) => `
    <label class="st-row"><span>${label}</span><input type="range" id="${id}" min="${lo}" max="${hi}" step="${step}" value="${v}"><output>${v}${unit}</output></label>`;

  const panes = {
    display() {
      const cur = density.get();
      return `<div class="st-group"><h4>屏幕显示模式 <small>真机与模拟器同步</small></h4>
        ${DENSITY.map(([id, name, d]) => `<button class="opt ${cur === id ? 'on' : ''}" data-density="${id}"><b>${name}</b><span>${d}</span></button>`).join('')}
        <p class="note">真机：长按屏幕右上角 0.7 秒也能切换。紧凑档真机暂按专业画。</p></div>`;
    },
    watch() {
      const w = sync.profile.watch;
      const chips = w.codes.map((c, i) => `
        <span class="pchip" draggable="true" data-i="${i}" title="拖动排序"><b>${esc(sync.nameOf(c))}</b><i>${c}</i>
          <button data-move="${i}:-1" ${i === 0 ? 'disabled' : ''} aria-label="前移">‹</button><button data-move="${i}:1" ${i === w.codes.length - 1 ? 'disabled' : ''} aria-label="后移">›</button>
          <button data-del="${i}" aria-label="移除 ${esc(sync.nameOf(c))}">×</button></span>`).join('');
      const dd = ui.results.length ? `<ul class="dd">${ui.results.map((r) => `<li data-code="${r.code}" data-name="${esc(r.name)}"><b>${esc(r.name)}</b><i>${r.code}</i></li>`).join('')}</ul>` : '';
      return `<div class="st-group"><h4>自选 <small>${w.codes.length}/${LIMITS.watchMax}</small></h4>
        <div class="chips2" id="wl">${chips || '<span class="note">还没有自选，搜一只加进来</span>'}</div>
        <div class="st-add"><input id="st-add" placeholder="搜代码或名称，如 宁德 / 300750" value="${esc(ui.addQ)}" autocomplete="off" spellcheck="false">${dd}</div>
        ${fieldErr('watch')}</div>
        <div class="st-group"><h4>怎么轮播</h4>
          <div class="seg" id="wv"><button data-view="single" class="${w.view === 'single' ? 'on' : ''}">单股轮播</button><button data-view="list" class="${w.view === 'list' ? 'on' : ''}">列表</button></div>
          ${slider('st-wi', '每页停留', w.interval, LIMITS.watchInterval, 1, ' 秒')}</div>`;
    },
    weather() {
      const wx = sync.profile.weather;
      const chips = wx.cities.map((c, i) => `
        <span class="pchip" data-i="${i}" title="${c.lat != null ? `${c.lat}, ${c.lon}` : '中枢解析中…'}"><b>${esc(c.name)}</b><i>${c.lat != null ? `${(+c.lat).toFixed(2)}, ${(+c.lon).toFixed(2)}` : '解析中…'}</i>
          <button data-cdel="${i}" aria-label="移除 ${esc(c.name)}">×</button></span>`).join('');
      return `<div class="st-group"><h4>城市 <small>${wx.cities.length}/${LIMITS.cityMax}</small></h4>
        <div class="chips2">${chips || '<span class="note">还没有城市</span>'}</div>
        <div class="st-add inline"><input id="st-city" placeholder="输入城市名，如 上海" value="${esc(ui.cityQ)}" autocomplete="off" spellcheck="false"><button id="btn-city" class="primary">添加</button></div>
        ${fieldErr('weather')}</div>
        <div class="st-group"><h4>怎么轮播</h4>${slider('st-ci', '每城停留', wx.interval, LIMITS.weatherInterval, 1, ' 秒')}</div>`;
    },
    other() {
      const P = sync.profile, names = [...new Set([...P.weather.cities.map((c) => c.name), P.today.city])];
      return `<div class="st-group"><h4>今天</h4>
          <label class="st-row"><span>天气城市</span><select id="st-tc">${names.map((n) => `<option ${n === P.today.city ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></label></div>
        <div class="st-group"><h4>展台</h4>
          <label class="st-row sw"><span>展台模式可用</span><input type="checkbox" id="st-be" ${P.booth.enabled ? 'checked' : ''}></label>
          ${slider('st-bd', '每页停留', P.booth.dwell, LIMITS.boothDwell, 1, ' 秒')}${fieldErr('booth')}</div>
        <div class="st-group"><h4>回放 <small>休市时用上个交易日的 5 分钟线</small></h4>${slider('st-rs', '速度', P.replay.speed, LIMITS.replay, 0.5, '×')}${fieldErr('replay')}</div>
        <div class="st-group"><button id="st-reset">恢复默认设置</button></div>`;
    },
  };

  function paintStatus() {
    const el = $('#st-status');
    if (sync.state === 'error') { el.className = 'st-status err'; el.textContent = sync.error?.field ? '✗ 没有保存，原因见下方' : `✗ ${sync.error?.error ?? '出错了'}`; return; }
    const [cls, text] = STATE_TEXT[sync.state] ?? ['', ''];
    el.className = `st-status ${cls}`;
    el.textContent = text;
  }
  $('#st-tabs').innerHTML = TABS.map(([id, name]) => `<button data-tab="${id}">${name}</button>`).join('');

  function render() {
    const active = document.activeElement?.id, caret = document.activeElement?.selectionStart;
    $('#st-tabs').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.tab === ui.tab));
    $('#st-pane').innerHTML = panes[ui.tab]();
    paintStatus();
    if (active && /^(st-add|st-city)$/.test(active)) { const el = $(`#${active}`); el?.focus(); try { el.setSelectionRange(caret, caret); } catch {} }
  }

  // ---- 事件 ----
  $('#st-tabs').onclick = (e) => { const b = e.target.closest('[data-tab]'); if (b) { ui.tab = b.dataset.tab; ui.results = []; render(); } };
  const pane = $('#st-pane');
  pane.addEventListener('click', (e) => {
    const t = e.target.closest('button, li');
    if (!t) return;
    const w = sync.profile.watch;
    if (t.dataset.density) return density.set(t.dataset.density);
    if (t.dataset.move) { const [i, d] = t.dataset.move.split(':').map(Number), a = [...w.codes]; [a[i], a[i + d]] = [a[i + d], a[i]]; return sync.set({ watch: { codes: a } }); }
    if (t.dataset.del !== undefined) return sync.set({ watch: { codes: w.codes.filter((_, i) => i !== +t.dataset.del) } });
    if (t.dataset.view) return sync.set({ watch: { view: t.dataset.view } });
    if (t.dataset.code) {   // 搜索结果里选一只
      ui.addQ = ''; ui.results = [];
      const code = t.dataset.code;
      return sync.set({ watch: { codes: [...w.codes, code], names: { ...w.names, [code]: t.dataset.name } } }) || render();
    }
    if (t.dataset.cdel !== undefined) return sync.set({ weather: { cities: sync.profile.weather.cities.filter((_, i) => i !== +t.dataset.cdel) } });
    if (t.id === 'btn-city') { const ok = sync.addCity(ui.cityQ); if (ok) ui.cityQ = ''; return render(); }
    if (t.id === 'st-reset') { sync.set({ watch: { codes: ['300750', '688981', '600519', '002594', '600036'], names: {}, view: 'single', interval: 8 }, weather: { cities: [{ name: '苏州', lat: 31.3, lon: 120.62 }], interval: 10 }, today: { city: '苏州' }, booth: { enabled: true, dwell: 15 }, replay: { speed: 1 } }); }
  });
  pane.addEventListener('input', (e) => {
    const el = e.target;
    if (el.type === 'range') { el.nextElementSibling.textContent = `${el.value}${el.nextElementSibling.textContent.replace(/[\d.]+/, '')}`; return; }   // 拖的时候只更新数字，松手再提交
    if (el.id === 'st-add') {
      ui.addQ = el.value;
      clearTimeout(ui.t);
      ui.t = setTimeout(async () => { ui.results = (await sync.search(ui.addQ)).filter((r) => !sync.profile.watch.codes.includes(r.code)); render(); }, 180);
    }
    if (el.id === 'st-city') ui.cityQ = el.value;
  });
  pane.addEventListener('change', (e) => {
    const el = e.target, v = +el.value;
    if (el.id === 'st-wi') sync.set({ watch: { interval: v } });
    else if (el.id === 'st-ci') sync.set({ weather: { interval: v } });
    else if (el.id === 'st-bd') sync.set({ booth: { dwell: v } });
    else if (el.id === 'st-rs') sync.set({ replay: { speed: v } });
    else if (el.id === 'st-be') sync.set({ booth: { enabled: el.checked } });
    else if (el.id === 'st-tc') sync.set({ today: { city: el.value } });
  });
  pane.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.id === 'st-city') { e.preventDefault(); if (sync.addCity(ui.cityQ)) ui.cityQ = ''; render(); }
    if (e.key === 'Enter' && e.target.id === 'st-add' && ui.results[0]) { e.preventDefault(); pane.querySelector('.dd li')?.click(); }
    if (e.key === 'Escape' && e.target.id === 'st-add') { ui.results = []; ui.addQ = ''; render(); }
  });
  // 拖动排序
  pane.addEventListener('dragstart', (e) => { const c = e.target.closest('.pchip[draggable]'); if (c) { ui.drag = +c.dataset.i; e.dataTransfer.effectAllowed = 'move'; } });
  pane.addEventListener('dragover', (e) => { if (ui.drag >= 0 && e.target.closest('.pchip[draggable]')) e.preventDefault(); });
  pane.addEventListener('drop', (e) => {
    const c = e.target.closest('.pchip[draggable]');
    if (!c || ui.drag < 0) return;
    e.preventDefault();
    const a = [...sync.profile.watch.codes], [m] = a.splice(ui.drag, 1);
    a.splice(+c.dataset.i, 0, m);
    ui.drag = -1;
    sync.set({ watch: { codes: a } });
  });

  render();
  sync.onChange(render);
  return { render, showTab(id) { ui.tab = id; render(); } };
}

// ---------- 设备盒子（左栏） ----------
export function mountDevice({ root, getInfo, onResend }) {
  root.innerHTML = `
    <div class="dev-row"><span>真机</span><b id="dv-peers">—</b></div>
    <div class="dev-row"><span>真机显示</span><b id="dv-disp">—</b></div>
    <div class="dev-row"><span>当前屏幕</span><b id="dv-face">—</b></div>
    <div class="line"><button id="btn-resend">重发当前到真机</button></div>
    <details class="cheat"><summary>真机手势</summary>
      <dl>
        <dt>单击</dt><dd>下一项（盯盘 / 天气里翻到下一个）</dd>
        <dt>长按右上角 0.7 秒</dt><dd>切换 简洁 ↔ 专业</dd>
        <dt>长按左上角 1.2 秒</dt><dd>老板键：时钟</dd>
        <dt>时钟里长按 1 秒</dt><dd>退出时钟</dd>
      </dl>
    </details>`;
  root.querySelector('#btn-resend').onclick = onResend;
  return {
    paint() {
      const i = getInfo();
      root.querySelector('#dv-peers').textContent = i.connected ? `脸 ${i.peers.face} · 身体 ${i.peers.body}` : '未连接中枢';
      root.querySelector('#dv-disp').textContent = i.board ?? '—';
      root.querySelector('#dv-face').textContent = i.face;
      root.querySelector('#btn-resend').disabled = !i.connected || !i.peers.face;
    },
  };
}
