import { Body } from './body.js';
import { Face, DENSITIES, getDensity, setDensity, onDensity } from './face.js';
import { Link, defaultUrl, defaultToken } from './link.js';
import { demos } from './demo.js';
import { follow } from './design.js';
import { USECASES } from './usecases.js';
import { SCENES, createSceneRunner } from './scenes.js';

const $ = (s) => document.querySelector(s);

const body = new Body($('#robot'));
const link = new Link({ onMessage: (m) => onHub(m), onStatus });
const params = new URLSearchParams(location.search);
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const store = {   // localStorage 可能被禁用，读写都包一层
  get: (k, d) => { try { return localStorage.getItem(`deskbot.sim.${k}`) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(`deskbot.sim.${k}`, v); } catch {} },
};

// 主屏：中间那块 480×320，真机上的屏幕就是这个。3D 机身头里那块（body.screen）是它的镜像，只负责跟着换。
const flatEl = $('#flat');
const heroScreen = document.createElement('div');
heroScreen.className = 'screen flat-screen';
flatEl.querySelector('.flat-inner').appendChild(heroScreen);

// 双击屏幕 = 老板键。在机器人本地处理，不等笔记本，保证瞬间切换
let lastTap = 0;
// ?idle=秒数：安静多久开始玩球（默认 25，之后再玩 12 秒就睡）；?idle=0 关掉
const idleParam = params.get('idle');
const face = new Face(heroScreen, (x, y) => {
  const now = performance.now();
  if (now - lastTap < 350) toggleBoss();
  lastTap = now;
  up({ t: 'touch', x, y });
}, { idleAfter: idleParam === null ? 25 : Number(idleParam), dense: true });
const mirror = new Face(body.screen, () => {}, { dense: true });   // 不自己导演（没有 idleAfter），完全跟主屏
const showHero = face._show.bind(face);
face._show = (state, card) => { showHero(state, card); mirror._show(state, card); };   // 主屏所有换屏（指令、触摸唤醒、待机导演）都会走这里
follow(heroScreen, body.screen);   // 设计实验室里调的主题 / 字体等，这里实时跟着变
window.deskbot = { face };   // 调试用：控制台里 deskbot.face.set('mkt', {...})
// ?density=simple|compact|pro：直接用某个显示模式打开（也会记住）
if (DENSITIES.includes(params.get('density'))) setDensity(params.get('density'));
// ?face=decoy 之类：直接打开某个表情，方便看屏幕设计
face.set(params.get('face') || 'idle');

// ---------- 日志尾巴：本机收发的消息 + 中枢日志，新的在最下面 ----------
const logEl = $('#log');
const hhmmss = (d = new Date()) => d.toTimeString().slice(0, 8);
function addRow(cls, tag, html, time = hhmmss()) {
  const li = document.createElement('li');
  li.className = cls;
  li.innerHTML = `<span class="tm">${time}</span><span class="tg">${tag}</span><span class="tx">${html}</span>`;
  const stick = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 30;
  logEl.appendChild(li);
  while (logEl.children.length > 300) logEl.firstChild.remove();
  if (stick) logEl.scrollTop = logEl.scrollHeight;
}
function log(kind, text) { addRow(kind, { up: '↑', down: '↓', sys: '·' }[kind] ?? '·', esc(text.length > 240 ? `${text.slice(0, 240)} …（${text.length} 字符）` : text)); }   // 卡片 JSON 很长，日志里只留开头
const LVL_TAG = { info: 'info', warn: 'warn', error: 'err' };
function hubLog(e, time) {
  if (!e || typeof e.ts !== 'number') return;
  const lvl = LVL_TAG[e.lvl] ? e.lvl : 'info';
  addRow(`log ${lvl}`, LVL_TAG[lvl], `<b>${esc(e.code ?? '')}</b>${esc(e.msg ?? '')}`, hhmmss(new Date(e.ts)));
}
$('#tail-seg').onclick = (e) => {
  const b = e.target.closest('[data-tail]');
  if (!b) return;
  $('#tail').dataset.show = b.dataset.tail;
  $('#tail-seg').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
  logEl.scrollTop = logEl.scrollHeight;
};
$('#tail').dataset.show = 'all';
$('#tail-seg button[data-tail="all"]').classList.add('on');

function up(msg) {
  log('up', JSON.stringify(msg));
  link.send(msg);
}

// ---------- 下行消息分发（真机固件里是同一张表） ----------
let pressWaiters = [];

async function handle(msg) {
  if (msg.t !== 'face' || (msg.state !== 'mkt' && msg.state !== 'watch')) log('down', JSON.stringify(msg));   // 行情 / 自选每秒刷新，不进日志
  switch (msg.t) {
    case 'pose':
      // 眼睛先看过去，头再跟上（真机上 T5 屏也这么做，动作才显得有意图）
      for (const f of [face, mirror]) f.glance(Math.sign((msg.yaw ?? body.yaw) - body.yaw) * 14, Math.sign((msg.pitch ?? body.pitch) - body.pitch) * -8, msg.ms ?? 500);
      return body.moveTo(msg.yaw, msg.pitch, msg.ms ?? 500);
    case 'gesture': return body.gesture(msg.name, msg.times ?? 1);
    case 'face':
      if (boss) { boss = { state: msg.state, card: msg.card }; return; }
      return face.set(msg.state, msg.card);
    case 'audio': return new Audio(msg.url).play().catch((e) => log('sys', `音频播放失败：${e.message}`));
    case 'torque': body.torque = Math.max(0, Math.min(100, msg.pct)); return;
    default: log('sys', `未知消息类型 ${msg.t}`);
  }
}

// 实时数据按钮：从点下去到答案回来之间一直显示「抓取中」（联网抓一次要几秒），失败 / 超时也会恢复
const LIVE_STATE = { today: 'today', sky: 'sky', market: 'mkt' };
let pending = null;
function endPending() {
  if (!pending) return;
  clearTimeout(pending.timer);
  pending.btn.classList.remove('running');
  bot.caption('');
  pending = null;
}

// 中枢发来的东西：人数、提示、别的客户端上行的事件，其余都是给机器人的指令
let peers = { face: 0, body: 0, view: 0 };
function onHub(m) {
  if (m.t === 'peers') {
    peers = m;
    for (const id of ['face', 'body', 'view']) {
      const el = $(`#pr-${id}`);
      el.classList.toggle('on', (m[id] | 0) > 0);
      el.querySelector('b').textContent = m[id] | 0;
    }
    $('#peers-note').textContent = `真机：脸 ${m.face} · 身体 ${m.body}`;
    return;
  }
  if (m.t === 'log') return hubLog(m);
  if (m.t === 'logs') { if (Array.isArray(m.items)) m.items.slice(-12).forEach((e) => hubLog(e)); return; }   // 刚连上：补最近几条
  if (m.t === 'display') {   // 别的客户端（或刚连上时中枢）告诉我们当前显示模式：直接应用，不回发，免得回环
    if (setDensity(m.mode)) log('down', JSON.stringify(m));
    return;
  }
  if (m.t === 'scene_state') return showScene(m);   // 中枢的场景引擎：现在在第几页
  if (m.t === 'notice') {
    if (m.level === 'error') link.report('error', 'REQ_FAILED', String(m.text).slice(0, 200));
    endPending();
    log('sys', m.text);
    bot.caption(m.text);
    setTimeout(() => bot.caption(''), 5000);
    return;
  }
  if (m.t === 'head_press') {   // 真机被按了头：等按头的演示脚本继续往下走
    flatEl.classList.add('pressed'); setTimeout(() => flatEl.classList.remove('pressed'), 260);
    pressWaiters.forEach((r) => r(true));
    pressWaiters = [];
    return;
  }
  if (m.t === 'touch' || m.t === 'boss') return log('down', JSON.stringify(m));
  if (pending && m.t === 'face' && m.state === LIVE_STATE[pending.what]) endPending();
  return handle(m);
}

// 网页上做的动作：打开「同步到真机」时，同一条指令也转给真机（经中枢）。中枢不会把它再发回给我们，不会回环
let control = false;
const act = (msg) => { if (control) up({ t: 'relay', msg }); return handle(msg); };

async function pressHead() {
  face.poke();
  if (!(await body.press())) return log('sys', `扭矩 ${body.torque}% 太大，按不动（需 ≤ 60%）`);
  flatEl.classList.add('pressed'); setTimeout(() => flatEl.classList.remove('pressed'), 260);   // 主屏上没有头，让整块屏幕往下压一下
  up({ t: 'head_press' });
  pressWaiters.forEach((r) => r(true));
  pressWaiters = [];
}

// 老板键：切到伪装的办公助手界面，再按一次恢复原来的画面
let boss = null;
function toggleBoss() {
  if (boss) {
    const { state, card } = boss;
    boss = null;
    face.set(state, card);
    body.moveTo(body.yaw, 0, 300);
  } else {
    boss = { state: face.state, card: face.card };
    face.set('decoy');
    body.moveTo(0, 0, 250);   // 立刻回正，装作什么都没发生
  }
  $('#btn-boss').classList.toggle('accent', !!boss);
  up({ t: 'boss', on: !!boss });
}

const bot = {
  handle: act,   // 演示脚本发的每条指令都走 act，这样能同步到真机
  caption: (text) => ($('#caption').textContent = text),
  waitPress: (ms) => new Promise((resolve) => {
    pressWaiters.push(resolve);
    setTimeout(() => resolve(false), ms);
  }),
};

// ---------- 状态上报，和真机一样每秒一次 ----------
function paintTele() {
  $('#telemetry').innerHTML =
    `yaw <b>${body.yaw.toFixed(1)}°</b> · pitch <b>${body.pitch.toFixed(1)}°</b> · 扭矩 <b>${body.torque}%</b> · 表情 <b>${esc(face.state)}</b>`;
}
setInterval(() => {
  paintTele();
  if (link.connected) link.send({ t: 'state', yaw: +body.yaw.toFixed(1), pitch: +body.pitch.toFixed(1), volt: 7.4, temp: 38 });
}, 1000);
// 当前屏幕状态在按钮上高亮（状态可能是导演、中枢、场景换的，不只是点按钮）
setInterval(() => document.querySelectorAll('[data-face]').forEach((b) => b.classList.toggle('on', b.dataset.face === face.state)), 300);
paintTele();
// 当前屏幕的状态和卡片数据（中枢推来的真数据一目了然）
let lastCard = '';
setInterval(() => {
  const key = face.state + JSON.stringify(face.card ?? null);
  if (key === lastCard) return;
  lastCard = key;
  $('#card-state').textContent = face.state;
  $('#card-json').textContent = face.card ? JSON.stringify(face.card, null, 1) : '（这个状态没有卡片数据）';
}, 400);

// ---------- 一天的场景 ----------
// 连着中枢：场景由中枢调度（它联网拿真数据，也会推给真机）；没连：模拟器用 scenes.js 的示例数据自己播
const sceneRunner = createSceneRunner({ handle: act, onState: (m) => showScene(m), caption: (t) => bot.caption(t) });
function showScene(m) {
  const on = m.name && m.name !== 'stop';
  for (const f of [face, mirror]) f.setScene(on ? m : null);   // 专业 / 紧凑屏状态栏的页码点和回放时钟
  const sc = SCENES.find((x) => x.id === m.name);
  const label = sc?.label ?? m.name;
  const box = $('#scene-state'), chip = $('#scene-chip');
  box.hidden = chip.hidden = !on;
  document.querySelectorAll('[data-scene]').forEach((b) => b.classList.toggle('running', on && b.dataset.scene === m.name));
  $('#scene-desc').textContent = on ? (sc?.desc ?? '') : '';
  $('#scene-desc').hidden = !on;
  if (!on) return;
  box.querySelector('b').textContent = `${label} · ${m.page}/${m.of}`;
  box.querySelector('.pg').innerHTML = Array.from({ length: m.of }, (_, i) => `<i class="${i + 1 === m.page ? 'on' : ''}"></i>`).join('');
  chip.textContent = `${label} ${m.page}/${m.of}`;
}
document.querySelectorAll('[data-scene]').forEach((b) => (b.onclick = () => {
  const name = b.dataset.scene;
  if (link.connected) { sceneRunner.stop(); up({ t: 'scene', name }); }
  else if (name === 'stop') sceneRunner.stop();
  else sceneRunner.start(name);
}));

// ---------- 显示模式：简洁 / 紧凑 / 专业 ----------
// 点按钮 / 按 V：本机立刻切换；连着中枢就发 {"t":"display","mode":…}，中枢存下来并转给真机和别的网页
const DENSITY_NAME = { simple: '简洁', compact: '紧凑', pro: '专业' };
const syncDensityUi = () => document.querySelectorAll('#density-seg [data-density]').forEach((b) => b.classList.toggle('on', b.dataset.density === getDensity()));
onDensity(syncDensityUi);
syncDensityUi();
function chooseDensity(mode) {
  if (setDensity(mode)) {
    bot.caption(`显示模式：${DENSITY_NAME[mode]}`);
    setTimeout(() => bot.caption(''), 2500);
  }
  if (link.connected) up({ t: 'display', mode });   // 已经是这个模式也发一次：让真机对齐
}
document.querySelectorAll('#density-seg [data-density]').forEach((b) => (b.onclick = () => chooseDensity(b.dataset.density)));

// ---------- 连接 ----------
function onStatus(kind, text) {
  $('#conn').className = `conn ${kind}`;
  $('#conn span').textContent = kind === 'on' ? '已连接' : kind === 'wait' ? '连接中' : '离线（单机模式）';
  $('#scene-src').textContent = kind === 'on' ? '中枢调度 · 真数据' : '示例数据';
  $('#hub-note').textContent = kind === 'on' ? '已连接' : kind === 'wait' ? '连接中…' : '离线';
  if (kind === 'off') for (const id of ['face', 'body', 'view']) { $(`#pr-${id}`).classList.remove('on'); $(`#pr-${id} b`).textContent = 0; }
  if (kind === 'off' && /拒绝|令牌/.test(text)) setTokenPop(true);   // 令牌不对：把令牌框弹出来
  log('sys', text);
}

$('#ws-url').value = defaultUrl();
link.token = defaultToken();
$('#ws-token').value = link.token;
$('#btn-connect').onclick = () => link.connect($('#ws-url').value.trim(), $('#ws-token').value.trim());
function setTokenPop(open) { $('#token-pop').hidden = !open; $('#btn-token').setAttribute('aria-expanded', String(open)); if (open) $('#ws-token').focus({ preventScroll: true }); }
$('#btn-token').onclick = () => setTokenPop($('#token-pop').hidden);
$('#ws-token').onkeydown = (e) => { if (e.key === 'Enter') $('#btn-connect').click(); };
$('#ws-url').onkeydown = (e) => { if (e.key === 'Enter') $('#btn-connect').click(); };
// https 页面（比如部署出去的 H5）连不了 ws:// 的笔记本，默认只在本地打开时自动连
if (location.protocol !== 'https:' || params.has('ws')) link.connect($('#ws-url').value);

// ---------- 控件 ----------
// 场景卡片：标题 + 谁在用，来自 usecases.js
$('#scenes').innerHTML =
  USECASES.map((uc) => `<button class="scene" data-demo="${uc.id}" title="${esc(uc.who)}"><b>${uc.name}</b><span>${uc.who}</span><i>▶</i></button>`).join('') +
  `<button class="all" data-demo="all">▶ ${USECASES.length} 个连播</button>`;
let running = false;
document.querySelectorAll('[data-demo]').forEach((b) => (b.onclick = async () => {
  if (running) return;
  running = true;
  b.classList.add('running');
  try { await demos[b.dataset.demo](bot); } finally { running = false; b.classList.remove('running'); }
}));
document.querySelectorAll('[data-gesture]').forEach((b) => (b.onclick = () => act({ t: 'gesture', name: b.dataset.gesture, times: 2 })));
document.querySelectorAll('[data-face]').forEach((b) => (b.onclick = () => act({ t: 'face', state: b.dataset.face })));
// 实时数据：让中枢联网抓一份，推给所有人（包括我们自己，所以不用本地再画一遍）
document.querySelectorAll('[data-live]').forEach((b) => (b.onclick = () => {
  if (!link.connected) {
    bot.caption('没连上中枢：在电脑上运行 ./hub/run.sh，实时数据要它联网去抓');
    return setTimeout(() => bot.caption(''), 5000);
  }
  endPending();
  b.classList.add('running');
  bot.caption('正在联网抓取…');
  pending = { what: b.dataset.live, btn: b, timer: setTimeout(endPending, 25000) };
  up({ t: 'req', what: b.dataset.live });
}));
$('#ctl').onchange = (e) => {
  control = e.target.checked;
  log('sys', control ? '已打开「同步到真机」：网页上的动作会同时发给真机' : '已关闭「同步到真机」');
};
$('#btn-press').onclick = pressHead;
$('#btn-boss').onclick = toggleBoss;
$('#btn-inject').onclick = () => {
  try {
    const parsed = JSON.parse($('#inject').value);
    (Array.isArray(parsed) ? parsed : [parsed]).reduce((p, m) => p.then(() => act(m)), Promise.resolve());
  } catch (e) { log('sys', `JSON 解析失败：${e.message}`); }
};

// ---------- 主屏缩放：自适应（填满中间区域）或固定倍数（放不下就缩） ----------
let scaleMode = store.get('scale', 'auto');
if (!['auto', '1', '1.5', '2'].includes(scaleMode)) scaleMode = 'auto';
function fitHero() {
  const sw = heroScreen.offsetWidth, sh = heroScreen.offsetHeight;
  if (!sw || !sh || body_big()) return;
  const main = $('#hero-main'), phone = matchMedia('(max-width: 820px)').matches;
  const aw = main.clientWidth - (phone ? 28 : 24) - 24;          // 左右内边距 + 黑色边框 12×2
  const ah = phone ? Infinity : main.clientHeight - 24 - 24;     // 手机上高度不限，只看宽度
  let k = Math.min(aw / sw, ah / sh);
  if (scaleMode !== 'auto') k = Math.min(k, Number(scaleMode));
  k = Math.max(0.5, Math.floor(Math.min(k, phone ? 3 : 2.5) * 20) / 20);
  heroScreen.style.transform = `scale(${k})`;
  flatEl.style.width = `${sw * k + 24}px`;
  flatEl.style.height = `${sh * k + 24}px`;
  $('#scale-seg').title = `当前 ${k.toFixed(2)}×`;
}
function setScale(m) {
  scaleMode = m;
  store.set('scale', m);
  $('#scale-seg').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.scale === m));
  fitHero();
}
$('#scale-seg').onclick = (e) => { const b = e.target.closest('[data-scale]'); if (b) setScale(b.dataset.scale); };
const cycleScale = () => { const o = ['auto', '1', '1.5', '2']; setScale(o[(o.indexOf(scaleMode) + 1) % o.length]); };
new ResizeObserver(fitHero).observe($('#hero-main'));
// 设计实验室里切了屏幕尺寸（320×240 ↔ 480×320），主屏要重新算比例
new MutationObserver(fitHero).observe(heroScreen, { attributes: true, attributeFilter: ['data-size'] });

// ---------- 3D 机身：右栏小预览（头里是主屏的镜像），可以放大到屏幕的位置 ----------
// 视角：微侧（默认，有立体感又看得清屏） → 正面 → 3/4 侧视（看结构）
const cams = ['rotateX(-10deg) rotateY(-14deg)', 'rotateX(-6deg)', 'rotateX(-20deg) rotateY(-36deg)'];
const stage = $('#stage');
let cam = 0;
const body_big = () => document.body.classList.contains('big3d');
$('#robot').style.transform = cams[0];
$('#btn-cam').onclick = () => { cam = (cam + 1) % cams.length; $('#robot').style.transform = cams[cam]; };

// 整机约 800px 高，按舞台大小缩放
function fit() {
  const r = stage.getBoundingClientRect();
  if (!r.width || !r.height) return;
  const narrow = r.width < 700;   // 小预览 / 手机：机身只有 640 宽，不用留那么多边
  const k = Math.min(r.width / (narrow ? 820 : 1150), r.height / 1320);   // 留出上下边距，底座不被裁掉
  $('#fit').style.transform = `translateY(${110 * k}px) scale3d(${k}, ${k}, ${k})`;   // scale3d：深度也等比缩，透视才不会在小预览里夸张
  stage.style.perspective = `${1800 * k}px`;  // 透视随缩放走，小预览里不会显得特别近
}
new ResizeObserver(fit).observe(stage);
function setBig(on) {
  document.body.classList.toggle('big3d', on);
  (on ? $('#hero-3d') : $('#sec-3d')).appendChild(stage);
  $('#btn-big').textContent = on ? '还原' : '放大';
  fit();
  if (!on) fitHero();
}
$('#btn-big').onclick = () => setBig(!body_big());
function setPreview(on) {   // 右栏 3D 预览整块显示 / 隐藏（身体已停用，默认显示，可收起腾出空间给演示列表）
  $('#sec-3d').classList.toggle('off', !on);
  store.set('3d', on ? '1' : '0');
  if (on) fit();
}
setPreview(store.get('3d', '1') === '1');
if (params.get('view') === '3d') setBig(true);
setScale(scaleMode);

// ---------- 快捷键 ----------
const helpEl = $('#help');
const setHelp = (on) => { helpEl.hidden = !on; };
$('#btn-help').onclick = () => setHelp(helpEl.hidden);
$('#help-close').onclick = () => setHelp(false);
helpEl.onclick = (e) => { if (e.target === helpEl) setHelp(false); };
// 鼠标点完按钮就让它失焦，不然接着按空格会再点一次那个按钮（键盘操作产生的 click，detail 是 0，不受影响）
document.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b && e.detail > 0) b.blur(); });
const FACE_KEYS = { i: 'idle', p: 'play', z: 'sleep', h: 'happy', t: 'today', s: 'sky', w: 'watch', m: 'mkt' };
const SCENE_KEYS = ['morning', 'watch', 'close', 'booth', 'stop'];
window.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest?.('input, textarea, select, [contenteditable]')) return;
  if (e.key === 'Escape') return setHelp(false);
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (k === '?') return setHelp(helpEl.hidden);
  if (/^[1-5]$/.test(k)) return document.querySelector(`[data-scene="${SCENE_KEYS[k - 1]}"]`).click();
  if (k === '[' || k === ']') {
    const states = [...document.querySelectorAll('[data-face]')].map((b) => b.dataset.face);
    const i = states.indexOf(face.state);
    return act({ t: 'face', state: states[(i + (k === ']' ? 1 : -1) + states.length) % states.length] });
  }
  if (FACE_KEYS[k]) return act({ t: 'face', state: FACE_KEYS[k] });
  if (k === ' ') { e.preventDefault(); return pressHead(); }
  if (k === 'b') return toggleBoss();
  if (k === 'v') return chooseDensity(DENSITIES[(DENSITIES.indexOf(getDensity()) + 1) % DENSITIES.length]);
  if (k === 'f') return cycleScale();
  if (k === 'd') return setPreview($('#sec-3d').classList.contains('off'));
  if (k === 'l') return window.open('logs.html', '_blank');
});

// ?demo=moyu 打开就自动播放，方便录 Demo 视频
const autoplay = new URLSearchParams(location.search).get('demo');
if (autoplay in demos) document.querySelector(`[data-demo="${autoplay}"]`).click();
