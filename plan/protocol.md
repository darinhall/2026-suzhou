# 新增协议（问答 + 语音 + 动作）

> 现有消息（mode / profile / face / servo_* / audio_test …）见《开发交接.md》§6 和《场景.md》，**不变**。
> 这里只写**新加的**。三条轨道照这个并行开发；要改先改这个文件，再通知其他人。

## 问答

```jsonc
// 模拟器 / 板子 / 脚本 → 中枢：问一个问题
{"t":"ask","id":"a17","text":"宁德时代今天涨了吗","lang":"zh","src":"sim|voice|script"}

// 中枢 → 所有人：处理阶段（板子据此换表情）
{"t":"ask_state","id":"a17","stage":"listening|thinking|speaking|done|error","text":"…识别出的文字…"}

// 中枢 → 所有人：完整回答（模拟器用它渲染对话记录；板子不用，板子看下面的 face / gesture / spk）
{"t":"reply","id":"a17","intent":"quote|yesno|compare|overview|watchlist|explain|advice|control|unknown",
 "codes":["300750"],"say":"宁德时代收涨 2.1%，跑赢创业板 0.8 个点。",
 "gesture":"nod|shake|none","card":{…见下…},"followups":["和比亚迪比呢？","最近一个月呢？"],
 "llm":"ark|ollama|template","ms":1840}
```

## 答案卡片（`face` 消息的新 state：`answer`）

```jsonc
{"t":"face","state":"answer","card":{
  "v":2,
  "q":"宁德时代今天涨了吗",          // 问题（≤20 字，超出截断）
  "head":"收涨 2.1%",               // 结论（≤12 字，大字）
  "tone":"up|down|flat|warn",      // 颜色：红涨 / 绿跌 / 灰平 / 黄护栏
  "series":[{"name":"宁德时代","pts":[…≤48 个数…]},{"name":"创业板指","pts":[…]}],  // 0–2 条线，可省略
  "stats":[["涨跌","+2.10%"],["振幅","3.4%"],["vs 创业板","+0.8"]],   // ≤4 对，值已格式化成字符串
  "pts":["成交额放大 1.3 倍","站上 20 日均线"],                        // ≤3 条要点，每条 ≤16 字
  "src":"PandaAI · 10-30 收盘"       // 数据来源 + 时间（必须有，评委会问）
}}
```

- 所有数字由 Python 格式化好，**板子只负责画**，不做任何计算。
- `tone=warn` 用于护栏（投资建议），卡片显示黄色边框 + "我不做买卖建议"。

## 动作

```jsonc
// 中枢 → 板子
{"t":"gesture","name":"nod|shake","times":2,"amp":8}   // amp 单位：度，上限 15
```

## 语音：上行（板子麦克风 → 中枢）

```jsonc
{"t":"mic_start","id":"a18","sr":16000,"fmt":"s16le","trigger":"touch|vad"}
// 然后若干个 WebSocket 二进制帧：16 kHz 单声道 s16le，每帧 20–100 ms
{"t":"mic_end","id":"a18","ms":2300}
```

- 最长 8 秒，超过板子自己结束。中枢收到 `mic_end` 后识别，再按 `ask` 流程走（`src:"voice"`）。

## 语音：下行（中枢 → 板子喇叭）

```jsonc
{"t":"spk_start","id":"a18","sr":16000,"fmt":"s16le","ms":2600}
// 二进制帧，每帧 ≤ 4 KB
{"t":"spk_end","id":"a18"}
{"t":"spk_stop"}            // 打断：立刻停
```

- 板子播放时不录音、不做音量检测（现有逻辑）。播放用现有音量上限 0.3。
