# T06 流水线 + 中枢接入 · 轨道 B · 阶段 1（阶段 1 的终点）

**目标：** 模拟器里打一句话 → 板子出答案卡 + 点头 / 摇头 + （阶段 2 起）说话。

## `brain/pipeline.py`
```python
class Brain:
    def __init__(self, market, llm, router=None, speak=None): ...
    async def ask(self, text: str, lang="zh", ask_id=None) -> Reply   # Reply = protocol.md 的 reply 消息
```
步骤：路由 → 取数（market）→ 算（metrics）→ 动作（gesture.decide）→ 解释（llm.explain）→ 拼卡片（cards.py）。
- `brain/gesture.py`：`decide(intent, facts) -> (name, times)`，规则见 decisions.md §6。
- `brain/cards.py`：`answer_card(intent, facts, expl) -> dict`，严格符合 protocol.md 的字段和长度。
- 依赖全部注入：测试用假的 market / llm（`tests/test_pipeline.py`）。

## 中枢 `hub/mock_hub.py`
- [ ] 收 `{"t":"ask"}` → 广播 `ask_state thinking` → `await brain.ask()` → 依次发 `gesture`、`face answer`、`reply`、（阶段 2）`spk_*` → `ask_state done`。
- [ ] 同一时间只处理一个问题；新问题来了取消旧的（`spk_stop`）。
- [ ] 答案卡显示 30 秒后回到之前的模式（`modes.py` 暂停 / 恢复，复用 `mode_ctl pause|resume`）。
- [ ] 出错：`ask_state error` + 摇头 1 次 + 日志 `ASK_FAIL`。

## 验收
- [ ] `tests/test_pipeline.py` 全绿。
- [ ] 真机：模拟器 `relay`/输入框发剧本 1–3 的问题，板子动作 + 卡片正确，端到端 < 3 秒（template 档 < 1 秒）。
