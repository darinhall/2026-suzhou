// 画像：从玩家在每一关的"真实操作"里算出 5 个维度，再匹配最近的交易人格。
// 不靠自我评价问卷，靠行为。

export const DIMS = [
  ['risk', '风险偏好'],
  ['trend', '趋势跟随'],
  ['contra', '逆向思维'],
  ['patience', '耐心'],
  ['speed', '果断'],
];

// decisions: [{kind: 'rally'|'crash'|'flat', action: -1|0|1, rt: ms}]，positions: 每一天的仓位 0–1
export function features(decisions, positions) {
  const of = (kind, action) => {
    const ds = decisions.filter((d) => d.kind === kind);
    return ds.length ? ds.filter((d) => d.action === action).length / ds.length : 0.5;
  };
  const chase = of('rally', 1), takeProfit = of('rally', -1);
  const panic = of('crash', -1), dip = of('crash', 1);
  const activity = decisions.filter((d) => d.action !== 0).length / decisions.length;
  const rts = decisions.map((d) => d.rt).sort((a, b) => a - b);
  const medianRt = rts[Math.floor(rts.length / 2)];
  const clamp = (v) => Math.max(0, Math.min(1, v));
  return {
    risk: positions.reduce((a, b) => a + b, 0) / positions.length,
    trend: (chase + panic) / 2,
    contra: (dip + takeProfit) / 2,
    patience: 1 - activity,
    speed: clamp(1 - (medianRt - 1500) / 6000),   // 1.5 秒内拍板 = 1，7.5 秒以上 = 0
  };
}

// 推荐 = PandaAI 已有的产品，引用官网自己的说法（pandaaiquant.com，2026-10-30 查看）
const PANDA = 'https://www.pandaaiquant.com/';
const P = {
  qube: { name: 'Qube 对话研究', why: '"一句话，把想法变成可回测的策略"', url: PANDA },
  a2a: { name: 'A2A 办公室', why: '"组一支 Agent 团队，替你跑完整条研究流水线"，每个交易日自动出盘前简报', url: PANDA },
  factor: { name: '量化因子中心', why: '因子检索、评估和因子池管理，免费版就能管 20 个因子', url: PANDA },
  sim: { name: 'Qube 仿真盘', why: '用模拟资金先练手，统计你真实的胜率和盈亏比', url: `${PANDA}docs/qube-sim` },
  app: { name: 'Qube App', why: '"移动端随时随地对话研究"', url: PANDA },
  course: { name: 'PandaAI 量化课程', why: '"系统的量化课程体系"，从零开始', url: PANDA },
  futures: { name: '全国期货模拟赛', why: '用仿真资金和全国玩家同场比一比', url: PANDA },
};

export const PERSONAS = [
  {
    id: 'surfer', name: '冲浪手', tag: '趋势追随型',
    proto: { risk: 0.8, trend: 0.9, contra: 0.1, patience: 0.3, speed: 0.7 },
    line: '浪来了就上，你相信趋势是朋友。',
    good: '敢于在强势行情里加仓，不错过大波段',
    blind: '容易追在高位，回撤来时扛得很辛苦',
    product: P.qube,
    skill: P.a2a,
    robot: '摸鱼模式下放量异动才眨眼提醒；回撤超过 8% 先劝你冷静',
  },
  {
    id: 'hunter', name: '抄底猎人', tag: '逆向型',
    proto: { risk: 0.6, trend: 0.1, contra: 0.9, patience: 0.3, speed: 0.6 },
    line: '别人恐惧时你贪婪，跌得越狠你越兴奋。',
    good: '不被情绪带着走，敢在恐慌里找机会',
    blind: '容易"接飞刀"，跌势没结束就重仓进场',
    product: P.factor,
    skill: P.qube,
    robot: '超跌时悄悄提醒你，连跌不止时摇头劝你再等等',
  },
  {
    id: 'guardian', name: '稳健守望者', tag: '低风险型',
    proto: { risk: 0.3, trend: 0.3, contra: 0.3, patience: 0.9, speed: 0.4 },
    line: '先活下来，再谈赚钱。',
    good: '仓位克制，很少被大回撤伤到',
    blind: '机会来了也可能只敢轻仓，收益偏保守',
    product: P.a2a,
    skill: P.app,
    robot: '每天开盘前一句「今天市场偏冷 / 偏热」，上班时间不打扰',
  },
  {
    id: 'holder', name: '佛系长持者', tag: '长期持有型',
    proto: { risk: 0.9, trend: 0.2, contra: 0.2, patience: 0.9, speed: 0.3 },
    line: '买了就拿着，涨跌随它去。',
    good: '不频繁交易，省下大量手续费和情绪成本',
    blind: '基本面变了也可能没察觉',
    product: P.a2a,
    skill: P.factor,
    robot: '平时只眨眼，每周五收盘后做一次复盘播报',
  },
  {
    id: 'flash', name: '闪电操盘手', tag: '高频型',
    proto: { risk: 0.6, trend: 0.5, contra: 0.5, patience: 0.1, speed: 0.95 },
    line: '每一次波动都是机会，你的手比脑子还快。',
    good: '反应快、执行力强，适合做策略化交易',
    blind: '交易太频繁，容易被噪音和手续费吃掉收益',
    product: P.sim,
    skill: P.qube,
    robot: '盘中异动及时提醒；一天下单太多次，它会转过身不看你的屏幕',
  },
];

// 玩家最后回答"平时关注什么"，用来微调推荐入口
export const MARKETS = [
  ['A股', 'a'], ['ETF / 基金', 'etf'], ['期货', 'futures'], ['还没开始投资', 'new'],
];

export function match(f) {
  const scored = PERSONAS.map((p) => {
    const d = Math.sqrt(DIMS.reduce((s, [k]) => s + (f[k] - p.proto[k]) ** 2, 0) / DIMS.length);
    return { p, score: Math.round(100 * (1 - d)) };
  }).sort((a, b) => b.score - a.score);
  return scored;
}

export function recommend(persona, market) {
  const recs = [persona.product, persona.skill];
  if (market === 'futures') recs[1] = P.futures;
  if (market === 'etf') recs[1] = P.app;
  if (market === 'new') recs.unshift(P.course);
  return recs.filter((r, i) => recs.indexOf(r) === i);
}
