#!/bin/sh
# 带全部功能启动中枢：websockets + PandaAI（行情 / 交易日历要它，账号在 data/.env）。
#   ./hub/run.sh            # 其余参数原样传给 mock_hub.py，比如 --no-auth
exec uv run --python 3.12 --with websockets --with panda-data==1.0.5 python "$(dirname "$0")/mock_hub.py" "$@"
