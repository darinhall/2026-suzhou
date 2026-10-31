# T02 指标计算 `brain/metrics.py` · 轨道 B · 阶段 1

**目标：** 纯函数，输入收盘价序列，输出指标。**卡片上所有数字都从这里来。**

## 接口（测试已写好：`tests/test_metrics.py`）
```python
pct_return(closes) -> float                 # 区间涨跌 %，(last/first - 1) * 100
day_change(close, pre_close) -> float       # 当日涨跌 %
moving_average(closes, n) -> list[float|None]  # 前 n-1 个为 None
volatility(closes, annualize=True) -> float # 日收益率标准差（ddof=1），年化 × sqrt(252)，单位 %
max_drawdown(closes) -> float               # 负数，单位 %，例如 -12.5
relative(a, b) -> float                     # pct_return(a) - pct_return(b)，单位：百分点
correlation(a, b) -> float                  # 日收益率的皮尔逊相关
normalize(closes, base=100) -> list[float]  # 画对比图用
summary(closes, pre_close=None, bench=None) -> dict   # 上面的打包，给 LLM 和卡片
```
- 输入可以是 list 或 pandas.Series。长度 < 2 时抛 `ValueError`（路由层转成"数据不足"，摇头）。
- 只用 numpy / pandas，不联网。

## 验收
- [ ] `uv run --group dev pytest tests/test_metrics.py` 全绿。
