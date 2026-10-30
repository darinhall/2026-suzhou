// WebSocket 客户端，和真机 ESP32 一样：主动连笔记本 ws://<laptop-ip>:8765/robot，断线自动重连。

export function defaultUrl() {
  const param = new URLSearchParams(location.search).get('ws');
  if (param) return param;
  try { const saved = localStorage.getItem('deskbot.ws'); if (saved) return saved; } catch {}
  return `ws://${location.hostname || 'localhost'}:8765/robot`;
}

export class Link {
  constructor({ onMessage, onStatus }) {
    this.onMessage = onMessage;
    this.onStatus = onStatus;
    this.ws = null;
    this.url = null;
    this.retry = null;
  }

  connect(url) {
    this.close();
    this.url = url;
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
      this.send({ t: 'hello', fw: 'sim-0.1.0' });
    };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return console.warn('bad json', e.data); }
      this.onMessage(msg);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
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
