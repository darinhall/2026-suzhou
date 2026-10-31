# T00 地基 · 轨道 B · 阶段 0（00:10–01:00）

**目标：** 所有人能用一条命令跑测试、跑中枢；慢的下载现在就开始。

## 做什么
- [ ] `pyproject.toml`（已建）：依赖 + `dev` 组（pytest）。`uv run --group dev pytest` 能跑（现在应全部 skip）。
- [ ] `hub/run.sh` 改成 `uv run` 读 pyproject，不再手写 `--with`。
- [ ] 建 `brain/__init__.py`（空包）。
- [ ] **现在就后台下载**（场馆网络慢）：
  - `ollama pull qwen2.5:7b-instruct`
  - `uv run --group voice python -c "import mlx_whisper; mlx_whisper.transcribe('tests/fixtures/silence.wav', path_or_hf_repo='mlx-community/whisper-large-v3-turbo')"`（第一次会下模型）
- [ ] 方舟：开通豆包，拿 `ARK_API_KEY` + 模型 / 接入点 ID，写进 `data/.env`。**限时 20 分钟**，超时就先用 ollama。
- [ ] `curl` 测一次方舟（见 T05），记下延迟。

## 验收
- `uv run --group dev pytest` 退出码 0。
- `ollama list` 有 qwen；`data/.env` 有方舟密钥（或决定先不用）。
