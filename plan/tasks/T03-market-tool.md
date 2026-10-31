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
- 启动时预热剧本里的股票（`warm()`），演示时第一问不卡。

## 做什么
- [ ] 实现上面四个函数。
- [ ] `scripts/snapshot_fixtures.py`：联网抓一次，写 `tests/fixtures/market/`。**今天就跑一次并提交**（这是断网兜底）。

## 验收
- [ ] `DESKBOT_OFFLINE=1` 下 `day("300750")`、`history("002594")` 有数。
- [ ] 联网冷启动 `warm()` < 10 秒；之后每次 < 50 ms。
