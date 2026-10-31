import { Body } from './body.js';
import { Face } from './face.js';
import { Link, defaultUrl, defaultToken } from './link.js';
import { demos } from './demo.js';
import { follow } from './design.js';
import { USECASES } from './usecases.js';

const $ = (s) => document.querySelector(s);

const body = new Body($('#robot'));
const link = new Link({ onMessage: (m) => onHub(m), onStatus });
// 双击屏幕 = 老板键。在机器人本地处理，不等笔记本，保证瞬间切换
let lastTap = 0;
// ?idle=秒数：安静多久开始玩球（默认 25，之后再玩 12 秒就睡）；?idle=0 关掉
const idleParam = new URLSearchParams(location.search).get('idle');
const face = new Face(body.screen, (x, y) => {
  const now = performance.now();
  if (now - lastTap < 350) toggleBoss();
  lastTap = now;
  up({ t: 'touch', x, y });
}, { idleAfter: idleParam === null ? 25 : Number(idleParam) });
body.screen.dataset.link = 'off';
follow(body.screen);   // 设计实验室里调的主题 / 字体等，这里实时跟着变
// ?face=decoy 之类：直接打开某个表情，方便看屏幕设计
face.set(new URLSearchParams(location.search).get('face') || 'idle');

// ---------- 日志 ----------
function log(kind, text) {
  const li = document.createElement('li');
  li.className = kind;
  li.textContent = text;
  const ol = $('#log');
  ol.prepend(li);
  while (ol.children.length > 200) ol.lastChild.remove();
}

function up(msg) {
  log('up', JSON.stringify(msg));
  link.send(msg);
}

// ---------- 下行消息分发（真机固件里是同一张表） ----------
let pressWaiters = [];

async function handle(msg) {
  if (msg.t !== 'face' || msg.state !== 'mkt') log('down', JSON.stringify(msg));
  switch (msg.t) {
    case 'pose':
      // 眼睛先看过去，头再跟上（真机上 T5 屏也这么做，动作才显得有意图）
      face.glance(Math.sign((msg.yaw ?? body.yaw) - body.yaw) * 14, Math.sign((msg.pitch ?? body.pitch) - body.pitch) * -8, msg.ms ?? 500);
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
    $('#peers').textContent = `真机：脸 ${m.face} · 身体 ${m.body}`;
    return;
  }
  if (m.t === 'notice') {
    if (m.level === 'error') link.report('error', 'REQ_FAILED', String(m.text).slice(0, 200));
    endPending();
    log('sys', m.text);
    bot.caption(m.text);
    setTimeout(() => bot.caption(''), 5000);
    return;
  }
  if (m.t === 'head_press') {   // 真机被按了头：等按头的演示脚本继续往下走
    if (flatOn) { flatEl.classList.add('pressed'); setTimeout(() => flatEl.classList.remove('pressed'), 260); }
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
  if (flatOn) { flatEl.classList.add('pressed'); setTimeout(() => flatEl.classList.remove('pressed'), 260); }   // 屏幕视图里没有头，让整块屏幕往下压一下
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
setInterval(() => {
  const s = { t: 'state', yaw: +body.yaw.toFixed(1), pitch: +body.pitch.toFixed(1), volt: 7.4, temp: 38 };
  $('#telemetry').textContent =
    `yaw   ${s.yaw.toFixed(1).padStart(6)}°\npitch ${s.pitch.toFixed(1).padStart(6)}°\n扭矩  ${String(body.torque).padStart(5)}%\n表情  ${face.state.padStart(6)}`;
  if (link.connected) link.send(s);
}, 1000);

// ---------- 连接 ----------
function onStatus(kind, text) {
  body.screen.dataset.link = kind === 'on' ? 'on' : 'off';   // 屏幕右上角的连接图标
  $('#conn').className = `conn ${kind}`;
  $('#conn span').textContent = kind === 'on' ? '已连接' : kind === 'wait' ? '连接中' : '离线（单机模式）';
  log('sys', text);
}

$('#ws-url').value = defaultUrl();
link.token = defaultToken();
$('#ws-token').value = link.token;
$('#btn-connect').onclick = () => link.connect($('#ws-url').value.trim(), $('#ws-token').value.trim());
// https 页面（比如部署出去的 H5）连不了 ws:// 的笔记本，默认只在本地打开时自动连
if (location.protocol !== 'https:' || new URLSearchParams(location.search).has('ws')) link.connect($('#ws-url').value);

// ---------- 控件 ----------
// 场景卡片：标题 + 谁在用，来自 usecases.js
$('#scenes').innerHTML =
  USECASES.map((uc) => `<button class="scene" data-demo="${uc.id}"><b>${uc.name}</b><span>${uc.who}</span><i>▶</i></button>`).join('') +
  '<button class="all" data-demo="all">▶ 三个连播</button>';
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

// 视角：微侧（默认，有立体感又看得清屏） → 正面 → 3/4 侧视（看结构） → 屏幕（只看屏幕，手机默认）
const cams = ['rotateX(-10deg) rotateY(-14deg)', 'rotateX(-6deg)', 'rotateX(-20deg) rotateY(-36deg)', 'flat'];
const stage = $('#stage'), flatEl = $('#flat');
let cam = 0, flatOn = false;

// 屏幕视图：把屏幕从 3D 头里摘出来，等比放大到整行宽度，外面一圈黑色边框
function fitFlat() {
  if (!flatOn) return;
  const s = body.screen, w = flatEl.clientWidth - 24;      // 24 = 左右边框
  const k = w / s.offsetWidth;
  s.style.transform = `scale(${k})`;
  flatEl.style.height = `${s.offsetHeight * k + 24}px`;
}
function setView(i) {
  cam = i;
  const flat = cams[i] === 'flat', s = body.screen;
  if (flat !== flatOn) {
    flatOn = flat;
    stage.classList.toggle('flat', flat);
    s.classList.toggle('in-head', !flat);
    s.classList.toggle('flat-screen', flat);
    if (flat) flatEl.querySelector('.flat-inner').appendChild(s);
    else { s.style.transform = ''; body.screenHome.appendChild(s); }
  }
  if (!flat) $('#robot').style.transform = cams[i];
  fit();
  fitFlat();
}
$('#btn-cam').onclick = () => setView((cam + 1) % cams.length);
// 窗口窄（手机）默认只看屏幕；?view=3d 可以强制 3D
const phone = matchMedia('(max-width: 820px)').matches && new URLSearchParams(location.search).get('view') !== '3d';
$('#robot').style.transform = cams[0];

// 整机约 800px 高，按舞台大小缩放
function fit() {
  if (flatOn) return;
  const r = stage.getBoundingClientRect();
  const narrow = r.width < 700;   // 手机：机身只有 640 宽，不用留那么多边
  const k = Math.min(r.width / (narrow ? 820 : 1150), r.height / 1320);   // 留出上下边距，底座不再被裁掉
  $('#fit').style.transform = `translateY(${110 * k}px) scale(${k})`;
  stage.style.perspective = `${1800 * k}px`;  // 透视随缩放走，手机上不会显得特别近
}
new ResizeObserver(() => { fit(); fitFlat(); }).observe(stage);
// 设计实验室里切了屏幕尺寸（320×240 ↔ 480×320），屏幕视图要重新算比例
new MutationObserver(fitFlat).observe(body.screen, { attributes: true, attributeFilter: ['data-size'] });
setView(phone ? cams.indexOf('flat') : 0);

// ?demo=moyu 打开就自动播放，方便录 Demo 视频
const autoplay = new URLSearchParams(location.search).get('demo');
if (autoplay in demos) document.querySelector(`[data-demo="${autoplay}"]`).click();
