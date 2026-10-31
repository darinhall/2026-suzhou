// 日志页：和真机一样连中枢（不报角色，所以中枢当它是网页），收 log / logs / peers。
import { Link, defaultUrl, defaultToken } from './link.js';

const $ = (s) => document.querySelector(s);
const MAX = 600;
const LVL = { info: 0, warn: 1, error: 2 };
const SRC_NAME = { face: '脸', body: '身体', hub: '中枢', sim: '网页' };

let items = [];
let paused = false;
let queued = 0;
let lvlFilter = 'all', srcFilter = 'all';

const link = new Link({ onMessage, onStatus, quiet: true });
link.token = defaultToken();

function onStatus(kind, text) {
  $('#conn').className = `conn ${kind}`;
  $('#conn span').textContent = kind === 'on' ? '已连接' : kind === 'wait' ? '连接中' : '离线';
  $('#conn').title = text;
  if (kind === 'on') $('#p-note').textContent = '';
  else if (kind === 'off') $('#p-note').textContent = text;   // 例如"被中枢拒绝：bad token"
  if (kind === 'off') for (const id of ['face', 'body', 'view']) setPeer(id, 0);
}

function setPeer(id, n) {
  const el = $(`#p-${id}`);
  el.classList.toggle('on', n > 0);
  el.querySelector('b').textContent = n;
}

function onMessage(m) {
  if (m.t === 'peers') { for (const id of ['face', 'body', 'view']) setPeer(id, m[id] | 0); return; }
  if (m.t === 'logs' && Array.isArray(m.items)) { items = m.items.filter(valid).slice(-MAX); render(); return; }
  if (m.t === 'log' && valid(m)) {
    items.push(m);
    if (items.length > MAX) items.shift();
    if (paused) { queued++; updateCount(); } else append(m);
  }
}

const valid = (e) => e && typeof e === 'object' && typeof e.ts === 'number';
const pass = (e) => (lvlFilter === 'all' || LVL[e.lvl] >= LVL[lvlFilter]) && (srcFilter === 'all' || e.src === srcFilter);

function rowFor(e) {
  const li = document.createElement('li');
  const lvl = LVL[e.lvl] === undefined ? 'info' : e.lvl;
  li.className = `ln ${lvl}`;
  const add = (cls, text) => { const s = document.createElement('span'); s.className = cls; s.textContent = text; li.appendChild(s); return s; };
  const d = new Date(e.ts);
  add('time', d.toTimeString().slice(0, 8));
  add('lvl', lvl);
  add('src', SRC_NAME[e.src] || e.src || '?');
  add('code', e.code || '');
  const msg = add('msg', e.msg || '');
  if (e.from && e.from !== '127.0.0.1') {   // 来源地址跟在消息后面（本机的不显示）
    const f = document.createElement('span');
    f.className = 'from';
    f.textContent = e.from;
    msg.appendChild(f);
  }
  return li;
}

const list = $('#log');

function nearBottom() { return list.scrollHeight - list.scrollTop - list.clientHeight < 40; }

function append(e) {
  if (!pass(e)) return updateCount();
  const stick = nearBottom();
  list.appendChild(rowFor(e));
  while (list.children.length > MAX) list.firstChild.remove();
  if (stick) list.scrollTop = list.scrollHeight;
  updateCount();
}

function render() {
  list.textContent = '';
  const frag = document.createDocumentFragment();
  for (const e of items) if (pass(e)) frag.appendChild(rowFor(e));
  list.appendChild(frag);
  queued = 0;
  list.scrollTop = list.scrollHeight;
  updateCount();
}

function updateCount() {
  const shown = items.filter(pass).length;
  $('#count').textContent = `${shown} / ${items.length} 条` + (paused && queued ? ` · 暂停中，新增 ${queued}` : '');
  $('#empty').hidden = list.children.length > 0;
}

document.addEventListener('change', (e) => {
  if (e.target.name === 'lvl') lvlFilter = e.target.value;
  else if (e.target.name === 'src') srcFilter = e.target.value;
  else return;
  render();
});
$('#btn-pause').onclick = () => {
  paused = !paused;
  $('#btn-pause').setAttribute('aria-pressed', paused);
  $('#btn-pause').textContent = paused ? '继续' : '暂停';
  if (!paused) render();
  else updateCount();
};
$('#btn-clear').onclick = () => { items = []; render(); };

updateCount();
if (location.protocol !== 'https:' || new URLSearchParams(location.search).has('ws')) link.connect(defaultUrl());
