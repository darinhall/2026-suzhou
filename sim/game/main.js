// 「寻找你的交易人格」：互动（走行情做决定）→ 画像（行为算维度）→ 推荐 → 下一步。
// DeskBot 当主持人，指令用的就是机器人协议（face / pose / gesture），以后可以原样转发给真机。

import { Face } from '../face.js';
import { follow } from '../design.js';
import { fakeBars, fromBars } from './scenario.js';
import { DIMS, MARKETS, features, match, recommend } from './persona.js';

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pct = (r, digits = 1) => `${r >= 0 ? '+' : ''}${(r * 100).toFixed(digits)}%`;

// ---------- 主持人 ----------
const face = new Face($('#screen'), () => {});
follow($('#screen'));
const host = {
  send(msg) {
    if (msg.t === 'face') face.set(msg.state, msg.card);
    if (msg.t === 'pose') $('#head').style.transform = `rotateY(${(msg.yaw ?? 0) * 0.4}deg) rotateX(${msg.pitch ?? 0}deg)`;
    if (msg.t === 'gesture') {
      const el = $('#head-inner');
      el.classList.remove('g-nod', 'g-shake');
      void el.offsetWidth;   // 重新触发动画
      if (msg.name === 'nod' || msg.name === 'shake') el.classList.add(`g-${msg.name}`);
      if (msg.name === 'look_up') host.send({ t: 'pose', pitch: 15 });
      if (msg.name === 'look_down') host.send({ t: 'pose', pitch: -15 });
      if (msg.name === 'home') host.send({ t: 'pose', pitch: 0 });
    }
  },
};
// 480×320 屏幕按手机宽度等比缩放
new ResizeObserver(([e]) => $('#head-inner').style.setProperty('--k', e.contentRect.width / 520)).observe($('#head'));

const say = (text) => ($('#say').textContent = text);

function show(id) {
  document.querySelectorAll('.view').forEach((v) => (v.hidden = v.id !== id));
  window.scrollTo(0, 0);
}

// ---------- 行情来源 ----------
// 真实行情：data/export_game.py 用 PandaAI 导出的 game/data/scenarios.json（复权日线，每只票最有戏剧性的 40 天）。
// 读不到（比如离线打开）就退回示例数据，H5 照样能玩。
let real = null;
const offset = Math.floor(Math.random() * 100);   // 每次打开从不同的票开始

async function loadReal() {
  if (real) return real;
  try {
    const res = await fetch('game/data/scenarios.json');
    real = res.ok ? (await res.json()).scenarios : [];
  } catch {
    real = [];
  }
  const note = real.length ? '历史真实行情 · 数据来自 PandaAI · 不构成投资建议' : '示例数据 · 不构成投资建议';
  document.querySelectorAll('.legal').forEach((el) => (el.textContent = note));
  return real;
}

async function loadScenario(round) {
  const list = await loadReal();
  return fromBars(list.length ? list[(offset + round) % list.length] : fakeBars(7 + round));
}

// ---------- 游戏状态 ----------
let g = null;
let round = 0;

async function start() {
  const sc = await loadScenario(round++);
  g = { sc, day: 0, pos: 0.5, equity: [1], positions: [], decisions: [], stop: 0 };
  show('v-play');
  hud();
  chart();
  host.send({ t: 'face', state: 'happy' });
  say('出发！股票名字先保密，结束后揭晓。');
  await sleep(1400);
  host.send({ t: 'face', state: 'idle' });

  const { bars, stops } = sc;
  while (g.day < bars.length - 1) {
    const stop = stops[g.stop];
    if (stop && g.day === stop.i) {
      await decide(stop);
      g.stop++;
      hud();
    }
    step();
    await sleep(160);
  }
  host.send({ t: 'gesture', name: 'home' });
  ask();
}

function step() {
  const { bars } = g.sc;
  const r = bars[g.day + 1].close / bars[g.day].close - 1;
  g.equity.push(g.equity.at(-1) * (1 + r * g.pos));
  g.positions.push(g.pos);
  g.day++;
  // 身体当仪表盘：最近 5 天涨跌决定抬头 / 低头
  const r5 = bars[g.day].close / bars[Math.max(0, g.day - 5)].close - 1;
  host.send({ t: 'pose', pitch: Math.max(-18, Math.min(18, r5 * 150)) });
  hud();
  chart();
}

const LINES = {
  rally: [(r) => `连涨了！最近 5 天 ${pct(r)}，成交量也在放大。`, (r) => `又涨了 ${pct(r)}，群里有人喊"还能翻倍"。`],
  crash: [(r) => `跳水了… 最近 5 天 ${pct(r)}。`, (r) => `还在跌，${pct(r)}，评论区一片"快跑"。`],
  flat: [(r) => `不温不火，最近 5 天 ${pct(r)}。`, (r) => `横着走，${pct(r)}，看不出方向。`],
};
const FACES = { rally: 'happy', crash: 'thinking', flat: 'idle' };

function decide(stop) {
  const lines = LINES[stop.kind];
  say(`${lines[g.stop % lines.length](stop.ret)} 你怎么办？`);
  host.send({ t: 'face', state: FACES[stop.kind] });
  if (stop.kind !== 'flat') host.send({ t: 'gesture', name: 'nod' });

  const box = $('#actions');
  box.querySelector('[data-act="1"]').disabled = g.pos >= 1;
  box.querySelector('[data-act="-1"]').disabled = g.pos <= 0;
  box.classList.add('on');
  const t0 = performance.now();
  return new Promise((resolve) => {
    box.onclick = (e) => {
      const b = e.target.closest('button');
      if (!b || b.disabled) return;
      box.onclick = null;
      box.classList.remove('on');
      const action = Number(b.dataset.act);
      g.decisions.push({ kind: stop.kind, action, rt: Math.round(performance.now() - t0), day: g.day });
      g.pos = Math.max(0, Math.min(1, g.pos + action * 0.5));
      host.send({ t: 'face', state: 'listening' });
      say(action > 0 ? '收到，加仓！' : action < 0 ? '收到，减仓。' : '收到，按兵不动。');
      setTimeout(resolve, 600);
    };
  });
}

function hud() {
  $('#hud-stop').textContent = `${Math.min(g.stop, g.sc.stops.length)}/${g.sc.stops.length}`;
  $('#hud-pos').textContent = `${Math.round(g.pos * 100)}%`;
  const r = g.equity.at(-1) - 1;
  const el = $('#hud-pnl');
  el.textContent = pct(r, 2);
  el.className = r >= 0 ? 'up' : 'down';
}

// 单序列走势：已走过的部分 + 决策点标记，未来的部分不画
function chart() {
  const { bars } = g.sc;
  const W = 440, H = 180, pad = 12;
  const closes = bars.map((b) => b.close);
  const lo = Math.min(...closes), hi = Math.max(...closes);
  const x = (i) => pad + (i / (bars.length - 1)) * (W - 2 * pad);
  const y = (v) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - 2 * pad);
  const seen = closes.slice(0, g.day + 1);
  const color = seen.at(-1) >= seen[0] ? 'var(--up)' : 'var(--down)';
  const grid = [0.25, 0.5, 0.75].map((k) => `<line class="grid" x1="0" x2="${W}" y1="${H * k}" y2="${H * k}"/>`).join('');
  const marks = g.decisions.map((d) => {
    const fill = d.action > 0 ? 'var(--up)' : d.action < 0 ? 'var(--down)' : 'var(--muted)';
    return `<circle class="mark" cx="${x(d.day)}" cy="${y(closes[d.day])}" r="5" fill="${fill}"><title>${d.action > 0 ? '加仓' : d.action < 0 ? '减仓' : '持有'}</title></circle>`;
  }).join('');
  $('#chart').innerHTML = `${grid}<polyline class="price" stroke="${color}" points="${seen.map((v, i) => `${x(i)},${y(v)}`).join(' ')}"/>${marks}`;
}

// ---------- 画像 + 推荐 ----------
function ask() {
  show('v-ask');
  host.send({ t: 'face', state: 'listening' });
  say('走完了！最后问你一句，我就能告诉你你是哪种交易人格。');
  $('#markets').innerHTML = MARKETS.map(([label, id]) => `<button data-m="${id}">${label}</button>`).join('');
  $('#markets').onclick = (e) => {
    const b = e.target.closest('button');
    if (b) result(b.dataset.m);
  };
}

async function result(market) {
  show('v-result');
  host.send({ t: 'face', state: 'thinking' });
  say('让我想想…');
  const f = features(g.decisions, g.positions);
  const [{ p, score }] = match(f);
  const recs = recommend(p, market);
  const { sc } = g;
  const hold = sc.bars.at(-1).close / sc.bars[0].close - 1;
  const mine = g.equity.at(-1) - 1;

  $('#r-name').textContent = p.name;
  $('#r-tag').textContent = `${p.tag} · 匹配度 ${score}%`;
  $('#r-line').textContent = p.line;
  $('#r-good').textContent = p.good;
  $('#r-blind').textContent = p.blind;
  $('#r-traits').innerHTML = DIMS.map(([k, label]) => {
    const v = Math.round(f[k] * 100);
    return `<div class="trait"><span>${label}</span><div class="track"><div class="fill" style="width:${v}%"></div></div><b>${v}</b></div>`;
  }).join('');
  $('#r-reveal').innerHTML =
    `揭晓：这段行情是 <b>${sc.name}</b>（${sc.code}，${sc.period}）。<br>` +
    `你的收益 <b class="${mine >= 0 ? 'up' : 'down'}">${pct(mine, 2)}</b>，一直拿着不动是 <b class="${hold >= 0 ? 'up' : 'down'}">${pct(hold, 2)}</b>。`;
  $('#r-recs').innerHTML = recs.map((r) => `<li><a href="${r.url}" target="_blank" rel="noopener">${r.name}</a><p>${r.why}</p></li>`).join('');
  $('#r-go').href = recs[0].url;

  // 画像格式和交接文档 §8 一致，DeskBot 和推荐引擎都读这个
  const profile = {
    persona: p.id, match: score, market,
    traits: Object.fromEntries(DIMS.map(([k]) => [k, +f[k].toFixed(2)])),
    decisions: g.decisions.map(({ kind, action, rt }) => ({ kind, action, rt })),
    recommend: recs.map((r) => r.name),
    robot_habit: p.robot,
  };
  $('#r-json').textContent = JSON.stringify(profile, null, 2);
  try { localStorage.setItem('deskbot.profile', JSON.stringify(profile)); } catch {}

  const sub = $('#r-sub');
  sub.className = '';
  sub.textContent = '让 DeskBot 每天提醒我';
  sub.onclick = () => {
    sub.className = 'done';
    sub.textContent = `✓ 已订阅：${p.robot}`;
    host.send({ t: 'face', state: 'ok', card: { title: '已订阅提醒' } });
    host.send({ t: 'gesture', name: 'nod' });
    say('好，以后我就这样提醒你。');
  };

  await sleep(900);
  host.send({ t: 'face', state: 'happy' });
  host.send({ t: 'gesture', name: 'nod' });
  say(`你是「${p.name}」！${p.line}`);
}

// ?auto=1：自动随机玩一局（截图测试、展台无人值守循环用）
if (new URLSearchParams(location.search).has('auto')) {
  new MutationObserver(() => {
    const box = $('#actions');
    if (box.classList.contains('on') && !box.dataset.auto) {
      box.dataset.auto = '1';
      setTimeout(() => {
        const opts = [...box.querySelectorAll('button:not(:disabled)')];
        opts[Math.floor(Math.random() * opts.length)].click();
        delete box.dataset.auto;
      }, 700);
    }
    const m = $('#markets button');
    if (m && !$('#v-ask').hidden) m.click();
  }).observe(document.body, { subtree: true, attributes: true, childList: true });
  setTimeout(start, 500);
}

$('#btn-start').onclick = start;
loadReal();
$('#r-again').onclick = start;
host.send({ t: 'face', state: 'idle' });
say('嗨，我是 DeskBot。想知道你是哪种交易人格吗？');
