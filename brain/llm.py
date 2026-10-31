"""大模型（火山方舟 Ark，OpenAI 兼容）：只负责「解释」和「闲聊兜底」，不算数、不决定动作（decisions.md §2）。

密钥：data/.env 的 ARK_API_KEY；模型 ARK_MODEL（默认 DeepSeek V4.1 Flash）。关掉深度思考，一句话 1–2 秒。
调用失败一律返回 None，调用方退回模板。
"""

from __future__ import annotations

import json
import os

MODEL = os.getenv("ARK_MODEL", "deepseek-v4-1-flash-260910")
SYSTEM = ("你是 DeskBot，一只放在工位上的熊猫盯盘机器人，用中文口语回答，像朋友提醒一样简短。"
          "绝不给买卖建议、不预测涨跌、不推荐股票。只能使用用户给出的数字，不编造任何数据。")

_client = None


def _c():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["ARK_API_KEY"], base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                         timeout=8, max_retries=0)
    return _client


def chat(user: str, system: str = SYSTEM, max_tokens: int = 200, json_mode: bool = False) -> str | None:
    try:
        r = _c().chat.completions.create(
            model=MODEL, max_tokens=max_tokens, temperature=0.3,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body={"thinking": {"type": "disabled"}},
            **({"response_format": {"type": "json_object"}} if json_mode else {}))
        return (r.choices[0].message.content or "").strip() or None
    except Exception as e:   # 网络 / 额度 / 没开通：退回模板
        print(f"[llm] {type(e).__name__}: {str(e)[:160]}")
        return None


def complete(messages: list, tools: list | None = None, max_tokens: int = 400):
    """带工具调用的一轮（brain/agent.py 用）。失败返回 None。"""
    try:
        return _c().chat.completions.create(
            model=MODEL, max_tokens=max_tokens, temperature=0.2, messages=messages,
            extra_body={"thinking": {"type": "disabled"}}, **({"tools": tools} if tools else {}))
    except Exception as e:
        print(f"[llm] {type(e).__name__}: {str(e)[:160]}")
        return None


def triage(text: str) -> dict | None:
    """规则认不出的话：是不是在跟机器人说话？是的话给一句 ≤40 字的回答。现场很吵，背景里的闲聊要忽略。"""
    out = chat(
        "下面是麦克风听到的一句话（可能是旁边的人在聊天，不是对你说的）。\n"
        f"「{text}」\n"
        '只输出 JSON：{"for_me": true/false, "say": "回答"}。'
        "for_me：像是在问你问题或给你指令（行情、股票、市场常识、你自己是谁、打招呼）才是 true；"
        "听不清、半句话、和你无关的闲聊都是 false。say 不超过 40 个字；涉及具体行情数字时说「你可以问我某只股票的行情」。",
        max_tokens=120, json_mode=True)
    if not out:
        return None
    try:
        d = json.loads(out)
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        return None
