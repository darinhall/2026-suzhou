// 演示剧本：按顺序播放 usecases.js 里的场景，不连笔记本也能跑。
// 需要按头的步骤会等最多 6 秒，没人按就继续。

import { USECASES } from './usecases.js';

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function play(bot, uc) {
  for (const step of uc.steps) {
    bot.caption?.(`${uc.name} · ${step.time} · ${step.say}`);
    for (const msg of step.msgs) await bot.handle(msg);
    if (step.wait === 'press') await bot.waitPress(6000);
    else await wait(2200);
  }
  bot.caption?.('');
  await bot.handle({ t: 'gesture', name: 'home' });
  await bot.handle({ t: 'face', state: 'idle' });
}

export const demos = Object.fromEntries(USECASES.map((uc) => [uc.id, (bot) => play(bot, uc)]));
demos.all = async (bot) => {
  for (const uc of USECASES) await play(bot, uc);
};
