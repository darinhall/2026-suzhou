// 单机演示剧本：不连笔记本也能跑完整流程。每一步都只发 §4 协议里的下行消息，
// 所以剧本可以原样搬到笔记本端的 Python 里。行情是编造的示例数据。

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

export async function feishu(bot) {
  await bot.handle({ t: 'face', state: 'blink', card: { count: 3 } });
  await wait(1500);
  await bot.handle({ t: 'pose', yaw: 35, pitch: 5, ms: 600 });
  await bot.handle({ t: 'gesture', name: 'nod', times: 1 });
  await bot.handle({
    t: 'face', state: 'msg',
    card: { title: '飞书 · 产品群 @你', body: '评审会改到 16:00', hint: '按一下我的头 = 已读' },
  });
  const pressed = await bot.waitPress(8000);
  await bot.handle({ t: 'face', state: pressed ? 'happy' : 'idle' });
  await wait(1200);
  await bot.handle({ t: 'gesture', name: 'home' });
  await bot.handle({ t: 'face', state: 'idle' });
}

export async function market(bot) {
  const spark = [12, 11, 12, 11, 12, 12];
  const card = (pct, vr, hint = '') => ({ name: '宁德时代', code: '300750.SZ', pct, vol_ratio: vr, spark: [...spark], hint });

  // 平稳阶段：身体当仪表盘，跟着涨跌幅轻微抬头/低头
  for (const [p, pct] of [[13, 0.4], [12, 0.1], [14, 0.9], [13, 0.6]]) {
    spark.push(p);
    await bot.handle({ t: 'face', state: 'mkt', card: card(pct, 1.0) });
    await bot.handle({ t: 'pose', yaw: 0, pitch: pct * 4, ms: 400 });
    await wait(700);
  }
  // 异动：放量拉升
  for (const p of [17, 20, 24, 23, 28]) {
    spark.push(p);
    await bot.handle({ t: 'face', state: 'mkt', card: card(1.5 + (p - 16) * 0.28, 1.8) });
    await wait(350);
  }
  await bot.handle({ t: 'pose', yaw: 35, pitch: 18, ms: 500 });
  await bot.handle({ t: 'gesture', name: 'nod', times: 2 });
  await bot.handle({ t: 'face', state: 'mkt', card: card(4.8, 2.3, '异动！按头 = 记入模拟单') });
  const pressed = await bot.waitPress(8000);
  if (pressed) {
    await bot.handle({ t: 'face', state: 'ok', card: { title: '已记入模拟单' } });
    await wait(1500);
  }
  await bot.handle({ t: 'gesture', name: 'home' });
  await bot.handle({ t: 'face', state: 'idle' });
}

// 摸鱼模式：上班时间，屏幕上只有表情。自选股慢慢涨 → 小跌 → 突然异动
export async function stealth(bot) {
  const day = [0.2, 0.4, 0.3, 0.7, 1.1, 0.9, 1.4, 1.8, 2.3, 2.6, 2.1, 1.2, 0.4, -0.3, -0.9, -1.4, -1.1, -0.6];
  for (const pct of day) {
    await bot.handle({ t: 'face', state: 'stealth', card: { pct, vol: Math.min(1, Math.abs(pct) / 3) } });
    await bot.handle({ t: 'pose', yaw: 0, pitch: pct * 2, ms: 600 });   // 只动一点点，外人看不出来
    await wait(700);
  }
  // 异动：眨个眼，慢慢转过来看你一眼，再转回去
  await bot.handle({ t: 'face', state: 'stealth', card: { pct: 3.4, vol: 0.9, alert: true } });
  await bot.handle({ t: 'pose', yaw: 25, pitch: 6, ms: 1200 });
  await wait(1500);
  await bot.handle({ t: 'pose', yaw: 0, pitch: 4, ms: 1200 });
  await wait(2500);
}

export async function all(bot) {
  await feishu(bot);
  await wait(800);
  await market(bot);
}
