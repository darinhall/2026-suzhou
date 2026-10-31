# T05 大模型解释层 `brain/llm.py` · 轨道 B · 阶段 1

**目标：** 给算好的指标，拿回一段结构化 JSON。任何失败都降级，**绝不让演示卡住**。

## 接口
```python
explain(intent, facts: dict, lang="zh") -> Explanation   # say, head, pts[≤3], followups[≤3], provider
extract(text) -> Intent | None                           # 路由兜底：抽意图 + 股票名
```
- `DESKBOT_LLM=ark|ollama|template`。ark 和 ollama 都走 OpenAI 兼容接口（`openai` 包，换 `base_url`）：
  - 方舟：`https://ark.cn-beijing.volces.com/api/v3`，model = 接入点 ID
  - Ollama：`http://127.0.0.1:11434/v1`，model = `qwen2.5:7b-instruct`
- **超时 4 秒** → 自动用 `template`。JSON 解析失败 → 重试 0 次，直接 `template`。
- 回复里的 `provider` 记实际用了哪一档（模拟器显示出来，评委问时有据可查）。

## 提示词 `brain/prompts/explain.md`
系统提示（双语，由 `lang` 决定输出语言）：
> 你是坐在用户工位旁的金融数据助手。你会收到 Python 算好的指标（JSON）。
> 任务：用一句口语（≤50 字）回答问题，给 ≤3 个要点（每条 ≤16 字），给 ≤3 个追问。
> 规则：只能使用给定数字，不得编造数据或新闻；历史数据不得说成实时；数据不足就直说；不给买卖建议。
> 输出必须是 JSON：{"say":…,"head":…,"pts":[…],"followups":[…]}

## 防编造
- `check_numbers(say, facts)`：`say` 里出现的每个数字（四舍五入到 1 位小数后）必须能在 facts 里找到，否则丢掉 LLM 的 `say` 用模板的。测试见 `tests/test_reply.py`。

## 验收
- [ ] `tests/test_reply.py` 全绿。
- [ ] 三档各手动跑一次剧本 1 的问题，记下延迟写在这里：ark ___ ms / ollama ___ ms / template ___ ms。
