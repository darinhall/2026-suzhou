// 机身：CSS 3D 搭出 底座 → 转塔(偏航) → 叉臂 → 头盒(俯仰)，并模拟两个 ST3215 舵机的运动。
// 坐标单位是 px，屏幕按 1:1 的 480×320 渲染，方便直接对照真机 LVGL 的像素尺寸。

export const LIMITS = { yaw: [-150, 150], pitch: [-25, 25] };  // 与交接文档 §5 的软件限位一致

const clamp = (v, [lo, hi]) => Math.min(hi, Math.max(lo, v));
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function box(cls, w, h, d) {
  const el = document.createElement('div');
  el.className = `box ${cls}`;
  const faces = [
    ['front', w, h, `translateZ(${d / 2}px)`],
    ['back side', w, h, `rotateY(180deg) translateZ(${d / 2}px)`],
    ['right side', d, h, `rotateY(90deg) translateZ(${w / 2}px)`],
    ['left side', d, h, `rotateY(-90deg) translateZ(${w / 2}px)`],
    ['top', w, d, `rotateX(90deg) translateZ(${h / 2}px)`],
    ['bottom', w, d, `rotateX(-90deg) translateZ(${h / 2}px)`],
  ];
  for (const [name, fw, fh, tf] of faces) {
    const f = document.createElement('div');
    f.className = `face ${name}`;
    Object.assign(f.style, { width: `${fw}px`, height: `${fh}px`, left: `${-fw / 2}px`, top: `${-fh / 2}px`, transform: tf });
    el.appendChild(f);
  }
  return el;
}

function at(el, x, y, z = 0) {
  el.style.transform = `translate3d(${x}px, ${y}px, ${z}px)`;
  return el;
}

export class Body {
  constructor(root) {
    this.yaw = 0;
    this.pitch = 0;
    this.torque = 50;
    this.pressDip = 0;   // 按头时被手压下的角度
    this.token = 0;

    root.append(
      at(box('plinth', 640, 30, 560), 0, 175),
      at(box('base', 600, 160, 520), 0, 80),
    );
    this.turret = document.createElement('div');
    this.turret.className = 'part';
    this.turret.append(
      at(box('plate', 560, 24, 420), 0, -12),
      at(box('arm', 30, 306, 70), -295, -177),
      at(box('arm', 30, 306, 70), 295, -177),
    );
    this.head = document.createElement('div');
    this.head.className = 'part';
    const shell = at(box('shell head', 520, 360, 200), 0, 0);
    this.screen = document.createElement('div');
    this.screen.className = 'screen in-head';
    shell.querySelector('.front').appendChild(this.screen);
    const cam = document.createElement('div');
    cam.className = 'cam';
    at(cam, 0, -230, 40);
    this.head.append(shell, cam);
    this.turret.appendChild(this.head);
    root.appendChild(this.turret);
    this.render();
  }

  render() {
    this.turret.style.transform = `rotateY(${this.yaw}deg)`;
    // 俯仰轴在叉臂顶端；抬头为正
    this.head.style.transform = `translateY(-300px) rotateX(${this.pitch - this.pressDip}deg)`;
  }

  moveTo(yaw = this.yaw, pitch = this.pitch, ms = 500) {
    const token = ++this.token;   // 新指令打断旧动作，和舵机写新目标位置一样
    const from = { yaw: this.yaw, pitch: this.pitch };
    const to = { yaw: clamp(yaw, LIMITS.yaw), pitch: clamp(pitch, LIMITS.pitch) };
    const t0 = performance.now();
    return new Promise((resolve) => {
      const step = (now) => {
        if (token !== this.token) return resolve(false);
        const k = ms <= 0 ? 1 : Math.min(1, (now - t0) / ms);
        this.yaw = from.yaw + (to.yaw - from.yaw) * ease(k);
        this.pitch = from.pitch + (to.pitch - from.pitch) * ease(k);
        this.render();
        if (k < 1) requestAnimationFrame(step);
        else resolve(true);
      };
      requestAnimationFrame(step);
    });
  }

  async gesture(name, times = 1) {
    const { yaw, pitch } = this;
    for (let i = 0; i < times; i++) {
      switch (name) {
        case 'nod':
          await this.moveTo(yaw, pitch - 15, 180);
          await this.moveTo(yaw, pitch, 180);
          break;
        case 'shake':
          await this.moveTo(yaw - 15, pitch, 150);
          await this.moveTo(yaw + 15, pitch, 250);
          await this.moveTo(yaw, pitch, 150);
          break;
        case 'look_up': return this.moveTo(yaw, 20, 400);
        case 'look_down': return this.moveTo(yaw, -18, 400);
        case 'home': return this.moveTo(0, 0, 600);
        default: console.warn('unknown gesture', name);
      }
      await wait(60);
    }
  }

  // 真机：扭矩小于约 60% 才按得动；俯仰被压低超过 8° 持续 200ms 才算按头
  async press() {
    if (this.torque > 60) return false;
    for (const d of [4, 9, 12]) { this.pressDip = d; this.render(); await wait(70); }
    await wait(200);
    this.pressDip = 0;
    this.render();
    return true;
  }
}
