"""语音问答 + 行情异动模拟（中枢这一侧）。协议见 plan/protocol.md「语音：上行 / 下行」「问答」。

板子：确认是一句话就 {"t":"mic_start","fmt":"ulaw"}，边说边传二进制（16 kHz μ-law，每帧 0.25 秒），说完 {"t":"mic_end"}
中枢：火山语音识别 → brain/router 意图 → brain/qa 取 PandaAI 数据 → 卡片 + 点头 / 摇头 + 火山语音合成 → 板子喇叭
       {"t":"spk_start","sr":16000,"fmt":"ulaw","ms":…} + 二进制 μ-law（每帧 4 KB）+ {"t":"spk_end"}，板子边收边放
μ-law（G.711）把数据量减半：板子走 SSL 上下行只有约 20 KB/s，16 位 PCM 比说话还慢。
模拟器 / 脚本也可以直接发 {"t":"ask","text":"…"}（打字）。

没听清、不是对机器人说的话（现场背景闲聊）：什么都不做，不动、不说话（只记日志）。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import numpy as np

SPK_CHUNK = 4000
MIC_MAX = 16000 * 2 * 10   # 10 秒


def ulaw_decode(b: bytes) -> bytes:
    u = ~np.frombuffer(b, np.uint8).astype(np.int32) & 0xFF
    exp, mant = (u >> 4) & 7, u & 0x0F
    v = (((mant << 3) + 0x84) << exp) - 0x84
    return np.where(u & 0x80, -v, v).astype("<i2").tobytes()


def ulaw_encode(pcm: bytes) -> bytes:
    s = np.frombuffer(pcm, "<i2").astype(np.int32)
    sign = np.where(s < 0, 0x80, 0)
    v = np.minimum(np.abs(s), 32635) + 0x84
    exp = np.clip(np.floor(np.log2(v)).astype(np.int32) - 7, 0, 7)
    mant = (v >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mant) & 0xFF).astype(np.uint8).tobytes()


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
        self.mic_fmt = str(msg.get("fmt", "s16le"))
        self.engine.hold(40)   # 有人在跟它说话：自选滚动别把"在听 / 想一想"的表情盖掉

    def mic_data(self, ws, data: bytes) -> None:
        buf = self.mic.get(ws)
        if buf is not None and len(buf) < MIC_MAX:
            buf += data

    async def mic_end(self, ws, msg: dict) -> None:
        pcm = bytes(self.mic.pop(ws, b""))
        if getattr(self, "mic_fmt", "") == "ulaw":
            pcm = ulaw_decode(pcm)
        if len(pcm) < 16000:   # 不到 0.5 秒
            await self._idle(ws)
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
        """没听清：让板子把"在听"的表情收回去，不说话、不动；自选滚动继续。"""
        if not (self.sim_task and not self.sim_task.done()):
            self.engine.hold(0)
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
                if intent.kind in ("watch_add", "watch_remove", "watch_list"):
                    rep = await self._watch(intent)
                else:
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

    async def _watch(self, intent) -> dict:
        """语音增删自选（T18）：brain/watchlist.py 判断，ModeEngine.profile_set 保存（名称解析、上限、广播都在那里）。"""
        import names
        from brain import qa, watchlist
        cur = list(self.engine.profile["watch"]["codes"])
        nm = lambda c: names.lookup(c) or c
        if intent.kind == "watch_list":
            lst = "、".join(nm(c) for c in cur)
            face = qa._ans(f"自选 {len(cur)} 只", "flat", "", "你的自选", pts=[nm(c) for c in cur[:3]],
                           stats=[[str(i + 1), nm(c)] for i, c in enumerate(cur[:4])], src="DeskBot 自选")
            return qa._reply(intent, f"你的自选有 {len(cur)} 只：{lst}。", face, "nod", 1)
        op = "add" if intent.kind == "watch_add" else "remove"
        code = intent.codes[0] if intent.codes else None
        new, res = watchlist.apply(op, code, cur)
        name = nm(code) if code else "这只股票"
        if res == "ok":
            ok, msg, _ = await self.engine.profile_set({"watch": {"codes": new}})
            if not ok:
                res = "fail"
        say = {"ok": f"已{'加入' if op == 'add' else '移出'}自选：{name}，现在 {len(new)} 只。",
               "exists": f"{name}已经在自选里了。", "missing": f"{name}本来就不在自选里。",
               "full": f"自选最多 {watchlist.MAX} 只，先删一只吧。", "empty": "自选至少留一只。",
               "unknown": "没听出是哪只股票。", "fail": "自选没保存成功。"}[res]
        good = res == "ok"
        await self.log("info", "WATCH_EDIT", f"{op} {code} → {res}（{len(new)} 只）")
        face = qa._ans(("已加入" if op == "add" else "已移出") if good else "没改", "up" if good else "warn", name if good else "",
                       f"自选 {len(new if good else cur)} 只", pts=[say[:14]],
                       stats=[[str(i + 1), nm(c)] for i, c in enumerate((new if good else cur)[-4:])], src="DeskBot 自选")
        return qa._reply(intent, say, face, "nod" if good else "shake", 1)

    async def perform(self, say: str, face: dict | None, gesture: dict | None, hold: float = 20) -> None:
        """一次"表态"：先合成语音（板子这时一直是"想一想"），再同时发 卡片 + 动作 + 语音。hold 秒内模式循环不覆盖这张卡。"""
        pcm = await self._tts(say) if say else b""
        if face:
            from brain import fontsafe
            self.engine.hold(hold)
            msg = {"t": "face", "state": face["state"], "card": fontsafe.card(face["card"])}   # 板子字体里没有的字换掉，不留空白
            self.engine.last_face = msg
            await self.bc(msg)
        if gesture:
            await self.bc({"t": "gesture", "name": gesture["name"], "times": gesture.get("times", 1), **({"hold": gesture["hold"]} if "hold" in gesture else {})})
        if pcm:
            await self._send_audio(pcm, say)
        if face:
            asyncio.create_task(self._back_to_panda(hold))

    async def _back_to_panda(self, after: float) -> None:
        """待机（熊猫）模式下：卡片停 after 秒后回到熊猫脸。期间又有新卡片（hold 被延长）就不回。"""
        await asyncio.sleep(after + 0.5)
        if self.engine.profile.get("mode") == "idle" and not self.engine.holding() and not (self.sim_task and not self.sim_task.done()):
            self.engine.last_face = {"t": "face", "state": "idle"}
            await self.bc(self.engine.last_face)

    # ---------- 下行：说话 ----------
    async def speak(self, text: str) -> None:
        pcm = await self._tts(text)
        if pcm:
            await self._send_audio(pcm, text)

    async def _tts(self, text: str) -> bytes:
        from brain import volc
        t0 = time.monotonic()
        try:
            pcm = await self._thread(volc.tts, text)
        except Exception as e:
            await self.log("error", "TTS_FAIL", f"语音合成失败：{type(e).__name__}: {e}"[:300])
            return b""
        await self.log("info", "TTS", f"合成 {len(pcm) / 32000:.1f} 秒语音，用时 {time.monotonic() - t0:.1f}s")
        return pcm

    async def _send_audio(self, pcm: bytes, text: str) -> None:
        faces = self._faces()
        if not faces:
            return
        ul = ulaw_encode(pcm)
        head = json.dumps({"t": "spk_start", "sr": 16000, "fmt": "ulaw", "ms": len(ul) // 16, "text": text[:80]}, ensure_ascii=False)

        async def one(w):
            try:
                await w.send(head)
                for i in range(0, len(ul), SPK_CHUNK):
                    await w.send(ul[i:i + SPK_CHUNK])
                await w.send(json.dumps({"t": "spk_end"}))
            except Exception:
                pass
        await asyncio.gather(*(one(w) for w in faces))
        await asyncio.sleep(len(ul) / 16000)   # 等它念完再做下一件事

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
            steps = anomaly_sim.steps(day, persona.load("standard"))   # 演示用标准人格：完整的提醒阶梯（瞥一眼 → 转头 → 叫你）
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
            if self.engine.profile.get("mode") == "idle":   # 待机（熊猫）模式：演完回到熊猫脸
                self.engine.last_face = {"t": "face", "state": "idle"}
                await self.bc(self.engine.last_face)
