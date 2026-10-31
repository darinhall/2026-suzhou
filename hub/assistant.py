"""语音问答 + 行情异动模拟（中枢这一侧）。协议见 plan/protocol.md「语音：上行 / 下行」「问答」。

板子：一句话录完 → {"t":"mic_start"} + 二进制 PCM（16 kHz s16le）+ {"t":"mic_end"}
中枢：火山语音识别 → brain/router 意图 → brain/qa 取 PandaAI 数据 → 卡片 + 点头 / 摇头 + 火山语音合成 → 板子喇叭
       {"t":"spk_start","sr":16000,"ms":…} + 二进制 PCM（每帧 ≤ 4 KB）+ {"t":"spk_end"}
模拟器 / 脚本也可以直接发 {"t":"ask","text":"…"}（打字）。

没听清、不是对机器人说的话（现场背景闲聊）：什么都不做，不动、不说话（只记日志）。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

SPK_CHUNK = 4000
MIC_MAX = 16000 * 2 * 10   # 10 秒


class Assistant:
    def __init__(self, robots: dict, broadcast, log, engine):
        self.robots, self.bc, self.log, self.engine = robots, broadcast, log, engine
        self.mic: dict = {}            # ws → bytearray（正在上传的那一句）
        self.router = None
        self.sim_task: asyncio.Task | None = None
        self.busy = asyncio.Lock()     # 一次只答一句

    async def _thread(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *a)

    def _faces(self):
        return [w for w, role in list(self.robots.items()) if role == "face"]

    # ---------- 上行：板子的麦克风 ----------
    def mic_start(self, ws, msg: dict) -> None:
        self.mic[ws] = bytearray()

    def mic_data(self, ws, data: bytes) -> None:
        buf = self.mic.get(ws)
        if buf is not None and len(buf) < MIC_MAX:
            buf += data

    async def mic_end(self, ws, msg: dict) -> None:
        pcm = bytes(self.mic.pop(ws, b""))
        if len(pcm) < 16000:   # 不到 0.5 秒
            return
        from brain import volc
        t0 = time.monotonic()
        try:
            text = await self._thread(volc.asr, pcm)
        except Exception as e:
            await self.log("error", "ASR_FAIL", f"语音识别失败：{type(e).__name__}: {e}"[:300])
            await self._idle(ws)
            return
        await self.log("info", "ASR", f"听到「{text}」（{len(pcm) / 32000:.1f} 秒，识别 {time.monotonic() - t0:.1f} 秒）")
        if not text:
            await self._idle(ws)
            return
        await self.ask(text, src="voice", ws=ws)

    async def _idle(self, ws) -> None:
        """没听清：让板子把"在听"的表情收回去，不说话、不动。"""
        try:
            await ws.send(json.dumps({"t": "listen_done"}))
        except Exception:
            pass

    # ---------- 问答 ----------
    async def ask(self, text: str, src: str = "sim", ws=None) -> None:
        from brain import qa
        from brain.router import Router
        if self.router is None:
            self.router = await self._thread(Router)
        async with self.busy:
            aid = uuid.uuid4().hex[:6]
            t0 = time.monotonic()
            intent = self.router.route(text)
            await self.bc({"t": "ask_state", "id": aid, "stage": "thinking", "text": text})
            try:
                rep = await self._thread(qa.answer, intent, self.engine.profile["watch"]["codes"])
            except Exception as e:
                await self.log("error", "QA_FAIL", f"「{text}」→ {intent.kind}：{type(e).__name__}: {e}"[:300])
                rep = None
            if rep is None:
                await self.log("info", "ASK_IGNORED", f"「{text}」→ {intent.kind}：不是对我说的 / 答不了，不反应")
                await self.bc({"t": "ask_state", "id": aid, "stage": "done", "text": text})
                if ws is not None:
                    await self._idle(ws)
                return
            await self.log("info", "ASK", f"「{text}」→ {intent.kind} {','.join(intent.codes)} · {rep['say'][:60]} · {time.monotonic() - t0:.1f}s")
            if rep["action"] == "sim_stop":
                await self.stop_sim()
            elif self.sim_task and not self.sim_task.done() and rep["action"] != "sim_start":
                await self.stop_sim(quiet=True)   # 模拟中途问别的：先停模拟
            await self.bc({"t": "reply", "id": aid, "intent": rep["intent"], "codes": rep["codes"], "say": rep["say"],
                           "gesture": (rep["gesture"] or {}).get("name", "none"), "ms": int((time.monotonic() - t0) * 1000)})
            await self.perform(rep["say"], rep["face"], rep["gesture"], hold=20)
            if rep["action"] == "sim_start":
                await self.start_sim()

    async def perform(self, say: str, face: dict | None, gesture: dict | None, hold: float = 20) -> None:
        """一次"表态"：换卡片 → 动作 → 说话。hold 秒内模式循环不覆盖这张卡。"""
        if face:
            self.engine.hold(hold)
            msg = {"t": "face", "state": face["state"], "card": face["card"]}
            self.engine.last_face = msg
            await self.bc(msg)
        if gesture:
            await self.bc({"t": "gesture", "name": gesture["name"], "times": gesture.get("times", 1), **({"hold": gesture["hold"]} if "hold" in gesture else {})})
        if say:
            await self.speak(say)

    # ---------- 下行：说话 ----------
    async def speak(self, text: str) -> None:
        from brain import volc
        try:
            pcm = await self._thread(volc.tts, text)
        except Exception as e:
            await self.log("error", "TTS_FAIL", f"语音合成失败：{type(e).__name__}: {e}"[:300])
            return
        faces = self._faces()
        if not faces or not pcm:
            return
        head = json.dumps({"t": "spk_start", "sr": 16000, "fmt": "s16le", "ms": len(pcm) // 32, "text": text[:80]}, ensure_ascii=False)
        for w in faces:
            try:
                await w.send(head)
                for i in range(0, len(pcm), SPK_CHUNK):
                    await w.send(pcm[i:i + SPK_CHUNK])
                await w.send(json.dumps({"t": "spk_end"}))
            except Exception:
                pass
        await asyncio.sleep(len(pcm) / 32000)   # 等它念完再做下一件事

    # ---------- 行情异动模拟 ----------
    async def start_sim(self) -> None:
        await self.stop_sim(quiet=True)
        self.sim_task = asyncio.create_task(self._sim())

    async def stop_sim(self, quiet: bool = False) -> None:
        t, self.sim_task = self.sim_task, None
        if t and not t.done():
            t.cancel()
            if not quiet:
                await self.log("info", "SIM_STOP", "行情异动模拟：停止")
        self.engine.hold(0)

    async def _sim(self) -> None:
        from brain import anomaly_sim, persona
        from watch import load_day
        try:
            day = await self._thread(load_day, 600, tuple(self.engine.profile["watch"]["codes"]))
            steps = anomaly_sim.steps(day, persona.load(self.engine.profile.get("persona")))
            await self.log("info", "SIM_START", f"行情异动模拟：{len(steps)} 个事件（基准 {day['date']} 收盘，数据 {day['source']}）")
            for st in steps:
                self.engine.hold(st.delay + 25)
                await asyncio.sleep(st.delay)
                a = st.alert
                await self.bc({**a.message(clock="模拟", persona="sim"), "sim": True})
                await self.log("info", "SIM_ALERT", f"L{a.level} {a.kind} · {a.say}")
                if a.level < 2:
                    await self.bc({"t": "gesture", "name": "glance"})
                    continue
                gesture = {"name": "look", "hold": 2}
                await self.perform(a.say, {"state": "mkt", "card": st.card}, gesture, hold=25)   # 转头看你 + 念出来
                if a.level >= 3:   # 3 级：念完再点头 / 摇头（板子上一个动作没做完会丢掉新的）
                    await self.bc({"t": "gesture", "name": "nod" if a.pct >= 0 else "shake", "times": 1})
            await asyncio.sleep(6)
            await self.perform("模拟结束，我继续帮你盯着。", None, {"name": "nod", "times": 1})
            await self.log("info", "SIM_DONE", "行情异动模拟：演完")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.log("error", "SIM_FAIL", f"行情异动模拟出错：{type(e).__name__}: {e}"[:300])
        finally:
            self.engine.hold(0)
