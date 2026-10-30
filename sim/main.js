import { Body } from './body.js';
import { Face } from './face.js';
import { Link, defaultUrl } from './link.js';
import { demos } from './demo.js';
import { follow } from './design.js';

const $ = (s) => document.querySelector(s);

const body = new Body($('#robot'));
const link = new Link({ onMessage: (m) => handle(m), onStatus });
// 双击屏幕 = 老板键。在机器人本地处理，不等笔记本，保证瞬间切换
let lastTap = 0;
const face = new Face(body.screen, (x, y) => {
  const now = performance.now();
  if (now - lastTap < 350) toggleBoss();
  lastTap = now;
  up({ t: 'touch', x, y });
});
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
    case 'pose': return body.moveTo(msg.yaw, msg.pitch, msg.ms ?? 500);
    case 'gesture': return body.gesture(msg.name, msg.times ?? 1);
    case 'face':
      if (boss) { boss = { state: msg.state, card: msg.card }; return; }
      return face.set(msg.state, msg.card);
    case 'audio': return new Audio(msg.url).play().catch((e) => log('sys', `音频播放失败：${e.message}`));
    case 'torque': body.torque = Math.max(0, Math.min(100, msg.pct)); return;
    default: log('sys', `未知消息类型 ${msg.t}`);
  }
}

async function pressHead() {
  if (!(await body.press())) return log('sys', `扭矩 ${body.torque}% 太大，按不动（需 ≤ 60%）`);
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
  handle,
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
  $('#conn').className = `conn ${kind}`;
  $('#conn span').textContent = kind === 'on' ? '已连接' : kind === 'wait' ? '连接中' : '离线（单机模式）';
  log('sys', text);
}

$('#ws-url').value = defaultUrl();
$('#btn-connect').onclick = () => link.connect($('#ws-url').value.trim());
// https 页面（比如部署出去的 H5）连不了 ws:// 的笔记本，默认只在本地打开时自动连
if (location.protocol !== 'https:' || new URLSearchParams(location.search).has('ws')) link.connect($('#ws-url').value);

// ---------- 控件 ----------
let running = false;
document.querySelectorAll('[data-demo]').forEach((b) => (b.onclick = async () => {
  if (running) return;
  running = true;
  try { await demos[b.dataset.demo](bot); } finally { running = false; }
}));
document.querySelectorAll('[data-gesture]').forEach((b) => (b.onclick = () => handle({ t: 'gesture', name: b.dataset.gesture, times: 2 })));
document.querySelectorAll('[data-face]').forEach((b) => (b.onclick = () => handle({ t: 'face', state: b.dataset.face })));
$('#btn-press').onclick = pressHead;
$('#btn-boss').onclick = toggleBoss;
$('#btn-inject').onclick = () => {
  try {
    const parsed = JSON.parse($('#inject').value);
    (Array.isArray(parsed) ? parsed : [parsed]).reduce((p, m) => p.then(() => handle(m)), Promise.resolve());
  } catch (e) { log('sys', `JSON 解析失败：${e.message}`); }
};

// 视角：正面（方便看屏幕） ↔ 3/4 侧视（看结构）
const cams = ['rotateX(-8deg)', 'rotateX(-18deg) rotateY(-32deg)'];
let cam = 0;
$('#robot').style.transform = cams[0];
$('#btn-cam').onclick = () => { cam = (cam + 1) % cams.length; $('#robot').style.transform = cams[cam]; };

// 整机约 800px 高，按舞台大小缩放
function fit() {
  const r = $('#stage').getBoundingClientRect();
  const k = Math.min(r.width / 820, r.height / 980);
  $('#fit').style.transform = `translateY(${170 * k}px) scale(${k})`;
  $('#stage').style.perspective = `${1800 * k}px`;  // 透视随缩放走，手机上不会显得特别近
}
fit();
new ResizeObserver(fit).observe($('#stage'));

// ?demo=moyu 打开就自动播放，方便录 Demo 视频
const autoplay = new URLSearchParams(location.search).get('demo');
if (autoplay in demos) document.querySelector(`[data-demo="${autoplay}"]`).click();
