// WebSocket 客户端，和真机 ESP32 一样：主动连笔记本 ws://<laptop-ip>:8765/robot，断线自动重连。

export function defaultUrl() {
  const param = new URLSearchParams(location.search).get('ws');
  if (param) return param;
  try { const saved = localStorage.getItem('deskbot.ws'); if (saved) return saved; } catch {}
  return `ws://${location.hostname || 'localhost'}:8765/robot`;
}

// 令牌：?token=xxxx 打开页面时记下来（存在这个浏览器里），并把它从地址栏抹掉，不留在历史记录里
export function defaultToken() {
  const url = new URL(location.href);
  const param = url.searchParams.get('token');
  if (param) {
    try { localStorage.setItem('deskbot.token', param); } catch {}
    url.searchParams.delete('token');
    history.replaceState(null, '', url);
    return param;
  }
  try { return localStorage.getItem('deskbot.token') || ''; } catch { return ''; }
}

export class Link {
  constructor({ onMessage, onStatus }) {
    this.onMessage = onMessage;
    this.onStatus = onStatus;
    this.ws = null;
    this.url = null;
    this.token = '';
    this.retry = null;
  }

  connect(url, token = this.token) {
    this.close();
    this.url = url;
    this.token = token;
    try { localStorage.setItem('deskbot.token', token); } catch {}
    try { localStorage.setItem('deskbot.ws', url); } catch {}
    this.open();
  }

  open() {
    this.onStatus('wait', `连接中 ${this.url}`);
    let ws;
    try { ws = new WebSocket(this.url); } catch (e) { return this.onStatus('off', `地址无效：${e.message}`); }
    this.ws = ws;
    ws.onopen = () => {
      this.onStatus('on', '已连接');
      this.send({ t: 'hello', fw: 'sim-0.1.0', ...(this.token ? { token: this.token } : {}) });   // 中枢要求第一条是 hello（本机免令牌）
    };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return console.warn('bad json', e.data); }
      this.onMessage(msg);
    };
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this.ws = null;
      // 被中枢以 1008 断开 = 令牌不对 / 被锁，不要每 2 秒去撞（5 次错误会锁 30 秒）
      if (e.code === 1008) return this.onStatus('off', `被中枢拒绝：${e.reason || '令牌不对'}`);
      this.onStatus('off', '离线，2 秒后重连');
      this.retry = setTimeout(() => this.open(), 2000);
    };
  }

  close() {
    clearTimeout(this.retry);
    const ws = this.ws;
    this.ws = null;
    ws?.close();
  }

  get connected() { return this.ws?.readyState === WebSocket.OPEN; }

  send(msg) {
    if (this.connected) this.ws.send(JSON.stringify(msg));
  }
}
