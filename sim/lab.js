// 设计实验室：用同一个 Face 渲染器，把三个使用场景的每一步画成故事板。
// 旋钮改的是 .screen 上的 data-* 和 CSS 变量，同时存进 localStorage，模拟器和游戏页实时跟着变。
// "并排对比"：选一个旋钮，每一步同时画出它的所有选项。

import { Face } from './face.js';
import { KNOBS, DEFAULTS, load, save, apply } from './design.js';
import { USECASES, faceOf } from './usecases.js';

const $ = (s) => document.querySelector(s);
const esc = (s = '') => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

let design = load();
let compare = 'none';
let current = new URLSearchParams(location.search).get('uc') || USECASES[0].id;

function seg(name, options, value) {
  return `<span class="seg">${options.map(([v, label]) =>
    `<label><input type="radio" name="${name}" value="${v}" ${String(value) === v ? 'checked' : ''}>${label}</label>`).join('')}</span>`;
}

function renderKnobs() {
  $('#knobs').innerHTML =
    KNOBS.map((k) => `<fieldset><legend>${k.label}</legend>${seg(k.key, k.options, design[k.key])}</fieldset>`).join('') +
    `<fieldset><legend>并排对比</legend>${seg('compare', [['none', '关'], ...KNOBS.map((k) => [k.key, k.label])], compare)}</fieldset>` +
    '<button class="reset" id="reset">恢复默认</button>';
}

$('#knobs').addEventListener('change', (e) => {
  const { name, value } = e.target;
  if (name === 'compare') compare = value;
  else { design = { ...design, [name]: value }; save(design); }
  renderBoard();
});
$('#knobs').addEventListener('click', (e) => {
  if (e.target.id !== 'reset') return;
  design = { ...DEFAULTS };
  compare = 'none';
  save(design);
  renderKnobs();
  renderBoard();
});

function renderTabs() {
  $('#tabs').innerHTML = USECASES.map((uc) =>
    `<button data-uc="${uc.id}" aria-pressed="${uc.id === current}">${uc.name}</button>`).join('');
}
$('#tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  current = b.dataset.uc;
  history.replaceState(null, '', `?uc=${current}`);
  renderTabs();
  renderBoard();
});

function renderBoard() {
  const uc = USECASES.find((u) => u.id === current) ?? USECASES[0];
  $('#uc-head').innerHTML = `
    <div><span>谁在用</span>${esc(uc.who)}</div>
    <div><span>痛点</span>${esc(uc.pain)}</div>
    <div><span>用到的能力</span>${esc(uc.panda)}</div>
    <div><span>带身体动作播放</span><a href="index.html?demo=${uc.id}" target="_blank">▶ 在模拟器里播放 ↗</a></div>`;

  const knob = KNOBS.find((k) => k.key === compare);
  const variants = knob ? knob.options.map(([v, label]) => ({ d: { ...design, [knob.key]: v }, label })) : [{ d: design, label: '' }];

  const board = $('#board');
  board.innerHTML = '';
  uc.steps.forEach((step, i) => {
    const li = document.createElement('li');
    li.className = 'step';
    li.innerHTML = `
      <div class="frames ${knob ? 'compare' : ''}"></div>
      <div class="notes">
        <div class="t">${i + 1} / ${uc.steps.length} · ${esc(step.time)}</div>
        <h3>${esc(step.say)}</h3>
        <div class="body-move">身体：${esc(step.body)}</div>
        ${step.wait === 'press' ? '<span class="press">等用户按头</span>' : ''}
        <details><summary>协议消息</summary><pre>${esc(step.msgs.map((m) => JSON.stringify(m)).join('\n'))}</pre></details>
      </div>`;
    const frames = li.querySelector('.frames');
    for (const { d, label } of variants) {
      const fig = document.createElement('figure');
      fig.className = 'frame';
      fig.style.margin = '0';
      fig.innerHTML = `<div class="screen"></div>${label ? `<figcaption>${label}</figcaption>` : ''}`;
      const screen = fig.querySelector('.screen');
      apply(screen, d);
      const f = faceOf(step);
      new Face(screen).set(f.state, f.card);
      frames.appendChild(fig);
    }
    board.appendChild(li);
  });
}

// 手机上旋钮默认折起来（它们占掉大半屏），摘要里显示当前设置
if (matchMedia('(max-width: 560px)').matches) $('#knobs-wrap').open = false;
const sizeName = { l: '3.5″', s: '2.8″' };
const nowText = () => `${sizeName[design.size]} · ${design.theme === 'dark' ? '深色' : '浅色'}`;
renderKnobs();
renderTabs();
renderBoard();
$('#knobs-now').textContent = nowText();
$('#knobs').addEventListener('change', () => ($('#knobs-now').textContent = nowText()));
