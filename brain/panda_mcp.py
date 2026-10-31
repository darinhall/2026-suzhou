"""PandaAI 数据 MCP（https://pandadatamcp.pandaaiquant.com/mcp）客户端：OAuth 登录 + 调工具。

    python brain/panda_mcp.py login     # 一次性：浏览器里授权（PandaAI 网页要已登录），令牌存进 data/mcp_token.json（不进 git）
    python brain/panda_mcp.py tools     # 列出 MCP 提供的工具
    python brain/panda_mcp.py call <工具名> '<JSON 参数>'

OAuth：动态注册客户端 + PKCE（S256）+ refresh_token，scope = pandadata:read（只读）。
令牌过期自动用 refresh_token 换新的；中枢在云端用同一个令牌文件（部署时拷过去）。
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

BASE = "https://pandadatamcp.pandaaiquant.com"
MCP_URL = BASE + "/mcp"
TOKEN_FILE = Path(__file__).resolve().parent.parent / "data" / "mcp_token.json"
REDIRECT_PORT = 8977
REDIRECT = f"http://127.0.0.1:{REDIRECT_PORT}/callback"


# ---------- OAuth ----------
def _save(tok: dict) -> None:
    tok["expires_at"] = time.time() + float(tok.get("expires_in", 3600)) - 60
    TOKEN_FILE.write_text(json.dumps(tok, ensure_ascii=False, indent=2))
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass


def login() -> None:
    reg = requests.post(BASE + "/register", timeout=15, json={
        "client_name": "DeskBot", "redirect_uris": [REDIRECT], "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "client_secret_post", "scope": "pandadata:read"}).json()
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = BASE + "/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"], "redirect_uri": REDIRECT, "scope": "pandadata:read",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "resource": MCP_URL})
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("DeskBot 已拿到 PandaAI 授权，可以关掉这个页面。".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    print("在浏览器里打开并授权：\n" + url, flush=True)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    for _ in range(600):
        if got:
            break
        time.sleep(0.5)
    srv.server_close()
    if got.get("state") != state or "code" not in got:
        raise SystemExit(f"授权失败：{got or '超时'}")
    tok = requests.post(BASE + "/token", timeout=15, data={
        "grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT, "code_verifier": verifier,
        "client_id": reg["client_id"], "client_secret": reg.get("client_secret", ""), "resource": MCP_URL}).json()
    if "access_token" not in tok:
        raise SystemExit(f"换令牌失败：{tok}")
    tok["client_id"], tok["client_secret"] = reg["client_id"], reg.get("client_secret", "")
    _save(tok)
    print(f"已保存令牌到 {TOKEN_FILE}（scope {tok.get('scope')}，{tok.get('expires_in')} 秒有效，可自动续期）")


def _token() -> str:
    tok = json.loads(TOKEN_FILE.read_text())
    if time.time() > tok.get("expires_at", 0) and tok.get("refresh_token"):
        new = requests.post(BASE + "/token", timeout=15, data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": tok["client_id"], "client_secret": tok.get("client_secret", ""), "resource": MCP_URL}).json()
        if "access_token" in new:
            tok.update(new)
            _save(tok)
    return tok["access_token"]


# ---------- MCP（Streamable HTTP，JSON-RPC）----------
class Client:
    def __init__(self):
        self.sid: str | None = None
        self.n = 0

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False):
        h = {"Authorization": "Bearer " + _token(), "Content-Type": "application/json",
             "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        body = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if not notify:
            self.n += 1
            body["id"] = self.n
        r = requests.post(MCP_URL, headers=h, json=body, timeout=30)
        self.sid = r.headers.get("Mcp-Session-Id", self.sid)
        if notify:
            return None
        r.raise_for_status()
        text = r.content.decode("utf-8")
        if r.headers.get("Content-Type", "").startswith("text/event-stream"):
            msg = None
            for event in text.replace("\r\n", "\n").split("\n\n"):   # 一个事件可能有多行 data:，拼起来才是完整 JSON
                data = "\n".join(line[5:].lstrip() for line in event.split("\n") if line.startswith("data:"))
                if data:
                    m = json.loads(data)
                    if m.get("id") == body["id"]:
                        msg = m
            if msg is None:
                raise RuntimeError(f"MCP {method}: 响应里没有结果")
        else:
            msg = json.loads(text)
        if "error" in msg:
            raise RuntimeError(f"MCP {method}: {msg['error']}")
        return msg["result"]

    def open(self) -> "Client":
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "deskbot", "version": "0.2"}})
        self._rpc("notifications/initialized", notify=True)
        return self

    def tools(self) -> list[dict]:
        return self._rpc("tools/list", {})["tools"]

    def call(self, name: str, args: dict) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": args})


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tools"
    if cmd == "login":
        login()
    elif cmd == "tools":
        for t in Client().open().tools():
            print(f"- {t['name']}: {(t.get('description') or '').strip().splitlines()[0][:100] if t.get('description') else ''}")
    elif cmd == "call":
        print(json.dumps(Client().open().call(sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")), ensure_ascii=False, indent=1)[:4000])
