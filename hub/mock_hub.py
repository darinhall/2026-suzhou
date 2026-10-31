"""假的笔记本中枢：用来联调模拟器或真机。

    pip install websockets
    python hub/mock_hub.py

机器人连上 ws://<本机IP>:8765/robot 后：
- 打印所有上行消息（hello / head_press / touch；state 太多，默认不打印）
- 在终端里输入一行 JSON 回车，就发给机器人
- 输入 demo 回车，跑一遍"飞书 @我"的小剧本

双板（见 双板方案.md）：hello 里带 role=face（T5）或 role=body（ESP32），
face/audio 只发给 face，pose/gesture/torque 只发给 body；没报 role 的（如 sim/）收全部。
"""

import asyncio
import json
import sys

from websockets.asyncio.server import serve

robots = {}  # ws -> role ("face" / "body" / None = 全部)

ROUTE = {"face": "face", "audio": "face", "pose": "body", "gesture": "body", "torque": "body"}

DEMO = [
    {"t": "pose", "yaw": 35, "pitch": 5, "ms": 600},
    {"t": "gesture", "name": "nod", "times": 1},
    {"t": "sleep", "ms": 100},  # 两块板：动作先走，卡片晚 100ms
    {"t": "face", "state": "msg",
     "card": {"title": "飞书 · 产品群 @你", "body": "评审会改到 16:00", "hint": "按一下我的头 = 已读"}},
]


async def handler(ws):
    if ws.request.path != "/robot":
        await ws.close(code=1008, reason="path must be /robot")
        return
    robots[ws] = None
    print(f"[+] robot connected {ws.remote_address}")
    try:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("t") == "state":
                continue
            if msg.get("t") == "hello":
                robots[ws] = msg.get("role")
                print(f"    role = {robots[ws] or '全部'}")
            print(f"↑ {raw}")
            if msg.get("t") == "head_press":
                await broadcast({"t": "face", "state": "happy"})
    finally:
        robots.pop(ws, None)
        print("[-] robot disconnected")


async def broadcast(msg):
    raw = json.dumps(msg, ensure_ascii=False)
    target = ROUTE.get(msg.get("t"))
    print(f"↓ {raw}" + (f"  → {target}" if target else ""))
    for ws, role in list(robots.items()):
        if target is None or role is None or role == target:
            await ws.send(raw)


async def stdin_loop():
    loop = asyncio.get_running_loop()
    while True:
        raw = await loop.run_in_executor(None, sys.stdin.readline)
        if raw == "":   # EOF：没有键盘（后台运行 / 重定向），别空转，中枢继续服务就行
            await asyncio.Event().wait()
        line = raw.strip()
        if not line:
            continue
        if line == "demo":
            for msg in DEMO:
                if msg["t"] == "sleep":
                    await asyncio.sleep(msg["ms"] / 1000)
                    continue
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
