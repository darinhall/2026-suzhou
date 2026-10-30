"""假的笔记本中枢：用来联调模拟器或真机。

    pip install websockets
    python hub/mock_hub.py

机器人连上 ws://<本机IP>:8765/robot 后：
- 打印所有上行消息（hello / head_press / touch；state 太多，默认不打印）
- 在终端里输入一行 JSON 回车，就发给机器人
- 输入 demo 回车，跑一遍"飞书 @我"的小剧本
"""

import asyncio
import json
import sys

from websockets.asyncio.server import serve

robots = set()

DEMO = [
    {"t": "pose", "yaw": 35, "pitch": 5, "ms": 600},
    {"t": "gesture", "name": "nod", "times": 1},
    {"t": "face", "state": "msg",
     "card": {"title": "飞书 · 产品群 @你", "body": "评审会改到 16:00", "hint": "按一下我的头 = 已读"}},
]


async def handler(ws):
    if ws.request.path != "/robot":
        await ws.close(code=1008, reason="path must be /robot")
        return
    robots.add(ws)
    print(f"[+] robot connected {ws.remote_address}")
    try:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("t") == "state":
                continue
            print(f"↑ {raw}")
            if msg.get("t") == "head_press":
                await broadcast({"t": "face", "state": "happy"})
    finally:
        robots.discard(ws)
        print("[-] robot disconnected")


async def broadcast(msg):
    raw = json.dumps(msg, ensure_ascii=False)
    print(f"↓ {raw}")
    for ws in list(robots):
        await ws.send(raw)


async def stdin_loop():
    loop = asyncio.get_running_loop()
    while True:
        line = (await loop.run_in_executor(None, sys.stdin.readline)).strip()
        if not line:
            continue
        if line == "demo":
            for msg in DEMO:
                await broadcast(msg)
                await asyncio.sleep(0.8)
            continue
        try:
            await broadcast(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")


async def main():
    async with serve(handler, "0.0.0.0", 8765):
        print("mock hub on ws://0.0.0.0:8765/robot — 输入 JSON 或 demo")
        await stdin_loop()


if __name__ == "__main__":
    asyncio.run(main())
