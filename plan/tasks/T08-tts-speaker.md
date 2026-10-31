# T08 语音合成 → 喇叭 · 轨道 B（a）+ A（b）· 阶段 2

> **喇叭是辅助。** 字幕（答案卡的 `say`）永远显示；这个任务失败不影响演示。

## T08a 中枢 `brain/tts.py`
- [ ] `synth(text, lang) -> bytes`：`say -v Tingting`（英文 `-v Samantha`）→ `ffmpeg` 转 16 kHz mono s16le。缓存：同一句话只合成一次（剧本问题提前合成）。
- [ ] 中枢按 protocol.md 发 `spk_start` + 二进制帧（4 KB）+ `spk_end`。
- [ ] `DESKBOT_SPEAK=board|laptop|both`：laptop 用 `afplay` 在笔记本上放。
- [ ] 测试：`tests/test_tts.py`（只在 macOS 上跑；检查采样率、长度 ≈ 时长）。

## T08b 板子 `audio.cpp`
- [ ] 收二进制帧 → PSRAM 环形缓冲（≥ 2 秒）→ I2S 播放；`spk_end` 后放完；`spk_stop` 立即清空。
- [ ] 播放时停掉说话检测（已有逻辑，确认一下）；音量上限 0.3 不变。
- [ ] 播放时屏幕表情 `speaking`（嘴动或右下角波形）。

## T08c（可选）豆包语音合成
- 只在阶段 1 完成、方舟已经能用之后做。火山引擎控制台开通"语音合成"，拿 AppID + Token（写 `data/.env`）。
- `DESKBOT_TTS=doubao`：HTTP 接口要 16 kHz、pcm 格式直接给板子；选一个活泼的中文音色。
- 超时 2 秒或失败 → 退回 `say`，日志 `TTS_FALLBACK`。

## 验收
- [ ] 一句 3 秒的话，板子出声完整、不卡顿、无爆音。
- [ ] 在 1 米外、展台噪音下听得清吗？记录结论（听不清也没关系，有字幕）。
