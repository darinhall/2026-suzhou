# T03 行情工具层 `brain/market.py` · 轨道 B · 阶段 1

**目标：** 给流水线一个**稳定、快、离线也能用**的取数接口。

## 接口
```python
day(code) -> dict          # 最近一个交易日：name, close, pre_close, high, low, amount, intraday[48], asof
history(code, days=22) -> pandas.DataFrame   # date, close, amount（日线，从早到晚）
index_day(code="399006") -> dict
watchlist() -> list[str]   # hub/profile.json 的自选
```
- 复用 `data/panda_client.py`（日线）和 `data/watch.py`（`load_day` 已经有当日 5 分钟线 + 缓存）。
- **缓存**：`data/cache/` 下按 code + 日期存 JSON，同一天不重复请求。
- **离线样本**：`tests/fixtures/market/*.json`（剧本用到的 5 只 + 3 个指数，10-30 的真实数据）。`DESKBOT_OFFLINE=1` 时只读样本——测试和断网演示都用它。
- **回放时钟**：`day(code, at=None)`。`at` 是回放下标（0–47，对应 `data/watch.py` 的 `TIMES`），由中枢的回放循环提供（`modes.py` 里的 `i`）；`close` 取那一刻的价格，`intraday` 截到那一刻，`asof` 写「10-30 回放 10:35」。`at=None` = 收盘。
- 试 1 分钟线：`PandaClient.get_minute("a", codes, d, d, "1m")`，能拿到就把回放精度提到 1 分钟（记在这里：能 / 不能）。
- 启动时预热剧本里的股票（`warm()`），演示时第一问不卡。

## 做什么
- [ ] 实现上面四个函数。
- [ ] `scripts/snapshot_fixtures.py`：联网抓一次，写 `tests/fixtures/market/`。**今天就跑一次并提交**（这是断网兜底）。

## 验收
- [ ] `day("300750", at=12)` 的 close 等于 10-30 10:35 那根 5 分钟线的收盘价。
- [ ] `DESKBOT_LIVE=1 pytest -m live` 里的行情测试全绿。
- [ ] `DESKBOT_OFFLINE=1` 下 `day("300750")`、`history("002594")` 有数。
- [ ] 联网冷启动 `warm()` < 10 秒；之后每次 < 50 ms。
