"""DeskBot 用的 PandaAI 数据客户端：包一层官方 SDK panda_data（1.0.5）。

不自己拼 HTTP：地址、鉴权、路径都交给 SDK。函数名和参数名是从 SDK 源码里读出来的（不是猜的）。
返回 pandas.DataFrame，已按时间从早到晚排序（接口原样是新的在前）。
实测列名（2026-10-30）：
- 股票日线：symbol date open high low close volume amount pre_close limit_up limit_down name trade_status
- 指数日线：symbol date open high low close volume amount pre_close
- 股票分钟线：symbol date datetime minute open high low close volume amount num_trades
期货代码不带交易所后缀：RB_DOMINANT（主力连续）或 RB2601，见 symbols.future_api()。

账号：环境变量 DEFAULT_USERNAME（注册手机号）/ DEFAULT_PASSWORD，或者写在 data/.env（已 gitignore）。
⚠️ SDK 默认用 http:// 登录（没有 https），密码是明文传输：用 PandaAI 专用密码，在自己的热点上登录。
"""

from __future__ import annotations

import os
from pathlib import Path

import panda_data

from symbols import symbol


def login() -> None:
    """从环境变量或 data/.env 读账号并登录。不打印任何账号信息。已经登录过（token 还有效）就直接返回，中枢每次请求都调它。"""
    if panda_data.is_authenticated():
        return
    env = Path(__file__).with_name(".env")
    if env.exists():
        from dotenv import load_dotenv   # panda_data 依赖里自带 python-dotenv
        load_dotenv(env)
    user, pwd = os.getenv("DEFAULT_USERNAME"), os.getenv("DEFAULT_PASSWORD")
    if not user or not pwd:
        raise SystemExit("缺少账号：在 data/.env 里写 DEFAULT_USERNAME=手机号 和 DEFAULT_PASSWORD=密码")
    panda_data.init_token(username=user, password=pwd)


def _asc(df, *keys):
    """接口返回新的在前，统一改成从早到晚。"""
    keys = [k for k in keys if df is not None and k in df.columns]
    return df.sort_values(keys).reset_index(drop=True) if keys else df


class PandaClient:
    """按 DeskBot 的需要分组：行情回放、盘中、交易日、股票池。"""

    # ---------- 日线（行情回放、游戏、复盘） ----------
    def get_bars(self, market: str, codes: list[str], start: str, end: str, fields=None):
        """日线。start / end 为 YYYYMMDD，跨度不超过 5 年（SDK 文档）。"""
        syms = [symbol(market, c) for c in codes]
        if market == "a":
            return _asc(panda_data.get_stock_daily(symbol=syms, start_date=start, end_date=end, fields=fields), "symbol", "date")
        if market == "index":
            return _asc(panda_data.get_index_daily(symbol=syms, start_date=start, end_date=end, fields=fields), "symbol", "date")
        if market == "future":
            return _asc(panda_data.get_future_daily(symbol=syms, start_date=start, end_date=end, fields=fields), "symbol", "date")
        # TODO: confirm HK / US daily functions in hk_reader / us_reader and whether our account has those modules
        raise NotImplementedError(f"{market} 日线还没接")

    # ---------- 分钟线（盘中异动、更细的回放） ----------
    def get_minute(self, market: str, codes: list[str], start: str, end: str, frequency: str = "1m", fields=None):
        """分钟线。股票支持 1m / 5m / 15m / 60m，指数只有 1m（SDK 文档）。"""
        syms = [symbol(market, c) for c in codes]
        if market == "a":
            return _asc(panda_data.get_stock_min(symbol=syms, start_date=start, end_date=end, frequency=frequency, fields=fields), "symbol", "datetime")
        if market == "index":
            return _asc(panda_data.get_index_min(symbol=syms, start_date=start, end_date=end, frequency="1m", fields=fields), "symbol", "datetime")
        if market == "future":
            return _asc(panda_data.get_future_min(symbol=syms, start_date=start, end_date=end, fields=fields), "symbol", "datetime")
        raise NotImplementedError(f"{market} 分钟线还没接")

    # ---------- 盘中快照（今天的日线 / 分钟线） ----------
    def get_snapshot(self, codes: list[str], fields=None):
        """A 股当日日线，盘中用来算涨跌幅。"""
        return panda_data.get_stock_rt_daily(symbol=[symbol("a", c) for c in codes], fields=fields)

    def get_today_minute(self, codes: list[str], fields=None):
        return panda_data.get_stock_rt_min(symbol=[symbol("a", c) for c in codes], fields=fields)

    # ---------- 交易日 ----------
    def last_trade_date(self) -> str | None:
        return panda_data.get_last_trade_date(exchange="SH")

    def trade_days(self, start: str, end: str):
        return panda_data.get_trade_cal(start_date=start, end_date=end, exchange="SH", is_trading_day=1)

    # ---------- 股票池 ----------
    def get_universe(self, index_code: str, date: str):
        """指数成分股（比如 000300 沪深300）。date 为 YYYYMMDD。"""
        return panda_data.get_index_weights(index_symbol=symbol("index", index_code), start_date=date, end_date=date)

    # ---------- 市场天气（涨跌家数） ----------
    def market_breadth(self):
        # TODO: SDK has MarketBreadthStreamClient (websocket). Its default URL is ws://127.0.0.1:8180/...,
        #       i.e. not public — ask PandaAI for the live websocket URL and whether our account can use it.
        #       Fallback: count up/down from get_snapshot() over the A-share universe.
        raise NotImplementedError("涨跌家数：等 PandaAI 给实时 websocket 地址")
