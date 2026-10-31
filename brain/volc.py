"""火山引擎豆包语音（新版控制台 API Key，X-Api-Key 鉴权）：一句话识别（录音文件极速版）+ 语音合成（HTTP 单向流式）。

密钥：data/.env 的 VOLC_SPEECH_API_KEY。都是一次 HTTP 请求，不用 WebSocket：
- asr(pcm16k) → 文字。整句录完再识别，板子一句话最长 8 秒，极速版 1 秒内返回。
- tts(text) → 16 kHz s16le PCM，直接发给板子喇叭。
"""

from __future__ import annotations

import base64
import io
import json
import os
import uuid
import wave

import requests

ASR_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
TTS_SPEAKER = os.getenv("VOLC_TTS_SPEAKER", "zh_female_vv_uranus_bigtts")   # 语音合成 2.0 的音色


def _key() -> str:
    k = os.getenv("VOLC_SPEECH_API_KEY")
    if not k:
        raise RuntimeError("缺少 VOLC_SPEECH_API_KEY（data/.env）")
    return k


def _wav(pcm: bytes, sr: int = 16000) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
    return b.getvalue()


def asr(pcm: bytes, sr: int = 16000) -> str:
    """16 位单声道 PCM → 识别出的文字（空串 = 没听清）。"""
    r = requests.post(ASR_URL, timeout=15, headers={
        "X-Api-Key": _key(), "X-Api-Resource-Id": "volc.seedasr.auc",   # 豆包语音识别 2.0（这个账号开通的是它）
        "X-Api-Request-Id": str(uuid.uuid4()), "X-Api-Sequence": "-1",
    }, json={"user": {"uid": "deskbot"}, "audio": {"data": base64.b64encode(_wav(pcm, sr)).decode()},
             "request": {"model_name": "bigmodel", "enable_punc": True}})
    code = r.headers.get("X-Api-Status-Code")
    if r.status_code != 200 or code not in (None, "20000000", "20000003"):   # 20000003 = 静音
        raise RuntimeError(f"ASR {r.status_code} {code} {r.headers.get('X-Api-Message')} {r.text[:200]}")
    return ((r.json().get("result") or {}).get("text") or "").strip()


def tts(text: str, sr: int = 16000, speaker: str | None = None) -> bytes:
    """文字 → 16 kHz s16le PCM。"""
    r = requests.post(TTS_URL, timeout=20, stream=True, headers={
        "X-Api-Key": _key(), "X-Api-Resource-Id": "seed-tts-2.0", "X-Api-Request-Id": str(uuid.uuid4()),
    }, json={"user": {"uid": "deskbot"}, "req_params": {
        "text": text, "speaker": speaker or TTS_SPEAKER,
        "audio_params": {"format": "pcm", "sample_rate": sr, "speech_rate": 15}}})   # 稍快一点：念数字不拖
    if r.status_code != 200:
        raise RuntimeError(f"TTS {r.status_code} {r.headers.get('X-Api-Message')} {r.text[:200]}")
    out = bytearray()
    for line in r.iter_lines():
        if not line:
            continue
        d = json.loads(line)
        if d.get("data"):
            out += base64.b64decode(d["data"])
        elif d.get("code") not in (0, 20000000, None):
            raise RuntimeError(f"TTS {d.get('code')} {d.get('message')}")
    return bytes(out)


if __name__ == "__main__":   # 自测：合成一句再识别回来
    import pathlib, sys, time
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / "data" / ".env")
    text = sys.argv[1] if len(sys.argv) > 1 else "帮我看看中芯国际的行情"
    t = time.time(); pcm = tts(text); print(f"TTS {len(pcm) / 32000:.1f} 秒音频，用时 {time.time() - t:.1f}s")
    t = time.time(); print(f"ASR「{asr(pcm)}」用时 {time.time() - t:.1f}s")
