// WebSocket 客户端，和真机 ESP32 一样：主动连笔记本 ws://<laptop-ip>:8765/robot，断线自动重连。

export function defaultUrl() {
  const param = new URLSearchParams(location.search).get('ws');
  if (param) return param;
  try { const saved = localStorage.getItem('deskbot.ws'); if (saved) return saved; } catch {}
  if (location.protocol === 'https:') return `wss://${location.host}/robot`;   // 云端：网页和中枢在同一个域名下（nginx 转发 /robot）
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
  constructor({ onMessage, onStatus, quiet = false }) {
    this.quiet = quiet;   // true：不往中枢报告自己的连接事件（日志页自己用）
    this.pending = [];    // 离线时发生的事，连上之后补报
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
      for (const e of this.pending.splice(0)) this.send(e);
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
      this.report('warn', 'LINK_LOST', '网页和中枢的连接断了，2 秒后重连');
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

  // 往中枢的日志里报一条；离线时先存着（最多 20 条），连上后补发
  report(lvl, code, msg) {
    if (this.quiet) return;
    const e = { t: 'log', lvl, src: 'sim', code, msg };
    if (this.connected) this.send(e);
    else if (this.pending.length < 20) this.pending.push(e);
  }

  get connected() { return this.ws?.readyState === WebSocket.OPEN; }

  send(msg) {
    if (this.connected) this.ws.send(JSON.stringify(msg));
  }
}
