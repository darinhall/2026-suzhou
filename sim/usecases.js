// 三个使用场景 + 示例数据。每一步就是一串协议消息（交接文档 §4 + README 新增），
// 实验室把每一步画成故事板，模拟器按顺序播放（带身体动作），以后笔记本中枢也可以原样发。
// 所有行情数字都是编造的示例数据。

const spark = [12, 11, 12, 11, 12, 12, 13, 12, 14, 13, 17, 20, 24, 23, 28];

export const USECASES = [
  {
    id: 'moyu',
    name: '盘中摸鱼看盘',
    who: '上班族散户 · 交易人格：冲浪手',
    pain: '交易时间和上班时间重合，只能偷偷看盘；一冲动就追涨。',
    panda: 'Panda Data 行情 · Qube 仿真盘',
    steps: [
      { time: '10:12', say: '平稳上涨，屏幕上只有表情', body: '俯仰 +1°（外人看不出来）',
        msgs: [{ t: 'face', state: 'stealth', card: { pct: 0.6, vol: 0.2 } }, { t: 'pose', yaw: 0, pitch: 1, ms: 800 }] },
      { time: '10:47', say: '自选股涨了 2.3%，眯眼笑、微微脸红', body: '俯仰 +5°',
        msgs: [{ t: 'face', state: 'stealth', card: { pct: 2.3, vol: 0.5 } }, { t: 'pose', yaw: 0, pitch: 5, ms: 800 }] },
      { time: '13:21', say: '宁德时代放量异动：眨眼，再转过来看你', body: '转身 25° + 点头 ×2',
        msgs: [{ t: 'face', state: 'stealth', card: { pct: 3.4, vol: 0.9, alert: true } }, { t: 'pose', yaw: 25, pitch: 8, ms: 900 },
          { t: 'gesture', name: 'nod', times: 2 },
          { t: 'face', state: 'mkt', card: { name: '宁德时代', code: '300750.SZ', pct: 4.8, vol_ratio: 2.3, spark, hint: '按头 = 记入模拟单' } }] },
      { time: '13:21', say: '冲浪手的护栏：冲动之前先问一句', body: '保持朝向你，等待按头', wait: 'press',
        msgs: [{ t: 'face', state: 'ask', card: { why: '冲浪手 · 今天第 3 次追涨', title: '确定要追吗？', meta: '宁德时代 ▲ +4.8% · 量比 2.3 · 已涨 3 天', hint: '按头 = 记入模拟单 · 不动 = 算了' } }] },
      { time: '13:22', say: '记入仿真盘（不是真的下单）', body: '点头',
        msgs: [{ t: 'face', state: 'ok', card: { title: '已记入模拟单' } }, { t: 'gesture', name: 'nod', times: 1 }] },
      { time: '13:30', say: '老板来了！双击屏幕', body: '瞬间回正',
        msgs: [{ t: 'pose', yaw: 0, pitch: 0, ms: 250 }, { t: 'face', state: 'decoy', card: { time: '13:30', date: '10月31日 星期六', meeting: '15:00 · 产品评审会', todo: 3 } }] },
    ],
  },
  {
    id: 'feishu',
    name: '飞书会议助手',
    who: '上班族 · 主赛道三 AI+生活办公',
    pain: '消息太多分不清轻重；会议一忙就忘；会后纪要没人整理。',
    panda: '思必驰 ASR / TTS · 飞书开放平台',
    steps: [
      { time: '14:02', say: '普通群消息：不动，只眨眼 + 角标', body: '不动',
        msgs: [{ t: 'face', state: 'blink', card: { count: 3 } }] },
      { time: '14:05', say: '产品群有人 @你', body: '转身 35° + 点头', wait: 'press',
        msgs: [{ t: 'pose', yaw: 35, pitch: 5, ms: 600 }, { t: 'gesture', name: 'nod', times: 1 },
          { t: 'face', state: 'msg', card: { title: '飞书 · 产品群 @你', body: '评审会改到 15:00，记得带数据', meta: '王经理 · 14:05', hint: '按一下我的头 = 已读' } }] },
      { time: '14:05', say: '按头已读，回写飞书', body: '点头 + 回正',
        msgs: [{ t: 'face', state: 'happy' }, { t: 'gesture', name: 'nod', times: 1 }, { t: 'gesture', name: 'home' }] },
      { time: '14:55', say: '会议 5 分钟后开始', body: '转身 + 左右扭两下', wait: 'press',
        msgs: [{ t: 'pose', yaw: 35, pitch: 0, ms: 600 }, { t: 'gesture', name: 'shake', times: 2 },
          { t: 'face', state: 'meeting', card: { minutes: 5, span: 30, title: '产品评审会 · 3 号会议室', hint: '按头 = 收到' } }] },
      { time: '15:03', say: '会议中：转向发言人，实时转写', body: '转向发言人 −40°',
        msgs: [{ t: 'pose', yaw: -40, pitch: 3, ms: 900 }, { t: 'face', state: 'listening' }] },
      { time: '15:41', say: '会议结束，纪要和待办推到飞书', body: '回正 + 点头', wait: 'press',
        msgs: [{ t: 'gesture', name: 'home' }, { t: 'face', state: 'brief', card: { title: '会议纪要 · 产品评审会 · 38 分钟', items: ['首页改版下周一上线，先灰度 10%', '数据看板延期一周，等埋点', '你的待办：周三前补齐转化数据'], hint: '按头 = 发到飞书', legal: false } },
          { t: 'gesture', name: 'nod', times: 1 }] },
    ],
  },
  {
    id: 'a2a',
    name: 'A2A 盘前简报',
    who: '上班族散户 · 交易人格：稳健守望者',
    pain: '早上没时间看新闻和盘面；信息很多，不知道哪些和自己的持仓有关。',
    panda: 'A2A 办公室（投研主持人 + 3 个 Agent）· Panda Data · 定时任务',
    steps: [
      { time: '09:08', say: '开机第一屏：今天。几号、周几、开不开市、天气、下一个会', body: '抬头看你',
        msgs: [{ t: 'pose', yaw: 0, pitch: 4, ms: 700 },
          { t: 'face', state: 'today', card: { month: 10, day: 30, weekday: '周五', market: '盘前', city: '苏州', temp: 16, text: '雾',
            tmr_text: '小阵雨', tmr_lo: 16, tmr_hi: 26, next_time: '09:30', next_in: '22 分钟后', next_title: '晨会', next_where: '3 号会议室' } }] },
      { time: '09:10', say: '轻点屏幕看天气详情：明天有雨，出门前就知道了', body: '保持朝向你',
        msgs: [{ t: 'pose', yaw: 0, pitch: 4, ms: 700 },
          { t: 'face', state: 'sky', card: { city: '苏州', time: '09:10', temp: 16, text: '雾', feels: 15, humidity: 88, wind: 1, hi: 23, lo: 14,
            tmr_text: '小阵雨', tmr_hi: 26, tmr_lo: 16, tmr_rain: 100, advice: '明天有雨，记得带伞' } }] },
      { time: '09:15', say: '市场天气：偏冷', body: '低头 −6°',
        msgs: [{ t: 'pose', yaw: 0, pitch: -6, ms: 800 }, { t: 'face', state: 'weather', card: { time: '09:15', word: '偏冷', up: 1284, down: 3702 } }] },
      { time: '09:16', say: '研究员发言：转向左边', body: '转身 −50°',
        msgs: [{ t: 'pose', yaw: -50, pitch: 0, ms: 900 }, { t: 'face', state: 'agent', card: { name: '研究员', n: 1, of: 3, say: '隔夜美股科技走弱，半导体板块承压' } }] },
      { time: '09:16', say: '风控官发言：转向正中', body: '转身 0°',
        msgs: [{ t: 'pose', yaw: 0, pitch: 0, ms: 900 }, { t: 'face', state: 'agent', card: { name: '风控官', n: 2, of: 3, say: '你的持仓里有 2 只波动偏大，今天不建议加仓' } }] },
      { time: '09:17', say: '交易员发言：转向右边', body: '转身 +50°',
        msgs: [{ t: 'pose', yaw: 50, pitch: 0, ms: 900 }, { t: 'face', state: 'agent', card: { name: '交易员', n: 3, of: 3, say: '重点看开盘后 15 分钟的量能，再决定' } }] },
      { time: '09:17', say: '投研主持人总结：转回来对着你', body: '转身 25°（朝向用户）+ 点头', wait: 'press',
        msgs: [{ t: 'pose', yaw: 25, pitch: 4, ms: 900 }, { t: 'gesture', name: 'nod', times: 1 },
          { t: 'face', state: 'brief', card: { title: '盘前简报 · 3 条要点', items: ['市场偏冷，上涨家数不到三成', '半导体承压，你持有的 1 只受影响', '今天不加仓，开盘 15 分钟后再看'], hint: '按头 = 推送到飞书' } }] },
      { time: '09:18', say: '简报已推送到飞书', body: '点头 + 回正',
        msgs: [{ t: 'face', state: 'ok', card: { title: '已推送到飞书' } }, { t: 'gesture', name: 'nod', times: 1 }, { t: 'gesture', name: 'home' }] },
    ],
  },
];


// ---- 一天的场景（单板：只有屏幕 + 数据；身体动作等以后接上舵机再加）----
const wl = (mode, asof, rows) => ({ title: '自选', asof, mode, index: { name: '上证指数', pct: 0.42 }, rows });
const NING = { name: '宁德时代', code: '300750', pct: 4.8, price: 215.3, spark };
const MAO = { name: '贵州茅台', code: '600519', pct: -0.6, price: 1432.5, spark: [20, 21, 20, 22, 21, 20, 19, 20, 19, 19, 18] };
const BYD = { name: '比亚迪', code: '002594', pct: 1.2, price: 268.4, spark: [14, 13, 14, 15, 14, 15, 16, 15, 16, 17] };

USECASES.push(
  {
    id: 'morning',
    name: '起床后 · 三十秒看完今天',
    who: '上班族 · 主赛道三 AI+生活办公',
    pain: '早上手忙脚乱：要查天气、查日程、看昨天自选涨跌，要开四个 App。',
    panda: 'Open-Meteo 天气 · 日历 · PandaAI 日线（上个交易日收盘）',
    steps: [
      { time: '07:30', say: '今天：日期、天气、下一个日程', body: '不动', msgs: [{ t: 'face', state: 'today' }] },
      { time: '07:30', say: '天气：一句话建议（要不要带伞）', body: '不动', msgs: [{ t: 'face', state: 'sky' }] },
      { time: '07:31', say: '早安简报：三条要点', body: '不动',
        msgs: [{ t: 'face', state: 'brief', card: { title: '早安简报', items: ['昨晚美股科技走弱，半导体承压', '今天 15:00 产品评审会，别迟到', '自选里宁德时代上个交易日 +4.8%'], legal: false } }] },
      { time: '07:31', say: '自选：上个交易日收盘，涨幅最大的一行最醒目', body: '不动',
        msgs: [{ t: 'face', state: 'watch', card: wl('close', '10-30 收盘', [NING, MAO, BYD]) }] },
    ],
  },
  {
    id: 'watching',
    name: '盯盘 · 数字在跳',
    who: '上班族散户 · 交易人格：冲浪手',
    pain: '要盯三只票，又不想一直开着交易软件。',
    panda: 'PandaAI 分钟线回放 / 盘中行情',
    steps: [
      { time: '13:15', say: '自选回放：数字每秒在动，涨幅最大的一行是深色药丸', body: '不动',
        msgs: [{ t: 'face', state: 'watch', card: wl('replay', '回放 13:15', [{ ...NING, pct: 2.1, price: 209.8 }, MAO, BYD]) }] },
      { time: '13:21', say: '宁德时代放量异动：行情卡，右上角只有一个橙色「异动」', body: '不动',
        msgs: [{ t: 'face', state: 'mkt', card: { name: '宁德时代', code: '300750.SZ', pct: 4.8, vol_ratio: 2.3, spark, price: 215.3, prev_close: 205.45, asof: '回放 13:21', mode: 'replay', alert: true, hint: '按头 = 记入模拟单' } }] },
      { time: '13:30', say: '老板来了！双击屏幕', body: '不动',
        msgs: [{ t: 'face', state: 'decoy', card: { time: '13:30', date: '10月31日 星期六', meeting: '15:00 · 产品评审会', todo: 3 } }] },
    ],
  },
  {
    id: 'close',
    name: '收盘 · 今天怎么样',
    who: '上班族 · 下班前',
    pain: '收盘后想知道今天赚亏多少、有没有异动，又不想翻账户。',
    panda: 'PandaAI 日线 · 模拟盘',
    steps: [
      { time: '15:05', say: '自选收盘：三只一眼看完', body: '不动',
        msgs: [{ t: 'face', state: 'watch', card: wl('close', '10-30 收盘', [NING, MAO, BYD]) }] },
      { time: '15:06', say: '收盘小结：三条要点', body: '不动',
        msgs: [{ t: 'face', state: 'brief', card: { title: '收盘小结', items: ['自选 3 只：2 涨 1 跌，平均 +1.8%', '最大异动：宁德时代 ▲ +4.8%，量比 2.3', '明天 09:30 开盘，我会提前叫你'], legal: false } }] },
      { time: '15:10', say: '没事了：安静下来，睡觉', body: '不动', msgs: [{ t: 'face', state: 'sleep' }] },
    ],
  },
);

// 一步里最后一个 face 消息：故事板上画它
export const faceOf = (step) => [...step.msgs].reverse().find((m) => m.t === 'face');
