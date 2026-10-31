// 设置（profile）和大模式（mode）的协议层。UI 只跟这个模块说话；协议改了只改这里。
//
// 客户端 → 中枢
//   {"t":"profile","set":{…部分字段…}}        改设置（深度合并）
//   {"t":"mode","name":"watch|weather|today|clock|idle|booth"}
//   {"t":"mode_ctl","op":"prev|next|pause|resume"}   （假设：翻页 / 暂停；中枢没实现就忽略）
//   {"t":"symbols","q":"宁德"}                  搜股票
// 中枢 → 客户端
//   {"t":"profile","profile":{…完整…}}           广播给所有人，连上 hello 之后也发一次
//   {"t":"profile_result","ok":true|false,"error":"…"}   只回给发起者
//   {"t":"symbols_result","q":"宁德","items":[{"code":"300750","name":"宁德时代"}]}
//   {"t":"scene_state","name","page","of","label","item"}
//
// 没连中枢时：设置存在 localStorage，立刻生效（离线示例模式）。

export const MODES = [
  { id: 'watch', label: '盯盘', desc: '自选逐只轮播（或列表）' },
  { id: 'weather', label: '天气', desc: '在设好的城市之间轮播' },
  { id: 'today', label: '今天', desc: '日期 · 天气 · 日程' },
  { id: 'clock', label: '时钟', desc: '老板键伪装屏' },
  { id: 'idle', label: '待机', desc: '眼睛 · 玩球 · 睡觉' },
  { id: 'booth', label: '展台', desc: '盯盘 → 天气 → 今天 循环' },
];

export const LIMITS = {
  watchMax: 8, cityMax: 6, watchInterval: [3, 120], weatherInterval: [3, 120], boothDwell: [5, 120], replay: [0.5, 4],
};

export const DEFAULTS = {
  mode: 'idle',
  display: 'pro',
  watch: { codes: ['300750', '688981', '600519', '002594', '600036'], names: {}, view: 'single', interval: 8 },
  weather: { cities: [{ name: '苏州', lat: 31.3, lon: 120.62 }], interval: 10 },
  today: { city: '苏州' },
  booth: { enabled: true, dwell: 15 },
  replay: { speed: 1 },
};

// 离线时能搜到的股票 / 认识的城市（连上中枢后由中枢负责，数据更全）
export const SYMBOLS = [
  ['300750', '宁德时代', 205.45], ['688981', '中芯国际', 100.1], ['600519', '贵州茅台', 1441.1], ['002594', '比亚迪', 265.2],
  ['600036', '招商银行', 43.29], ['601318', '中国平安', 52.8], ['000858', '五粮液', 138.5], ['300059', '东方财富', 21.6],
  ['002415', '海康威视', 32.4], ['601012', '隆基绿能', 17.3], ['600900', '长江电力', 28.9], ['000333', '美的集团', 71.2],
  ['601888', '中国中免', 68.5], ['002475', '立讯精密', 36.1], ['688111', '金山办公', 276.0], ['300760', '迈瑞医疗', 245.3],
].map(([code, name, prev]) => ({ code, name, prev }));
export const CITIES = {
  苏州: [31.3, 120.62], 上海: [31.23, 121.47], 北京: [39.9, 116.4], 深圳: [22.54, 114.06], 杭州: [30.27, 120.15], 广州: [23.13, 113.26],
  南京: [32.06, 118.8], 成都: [30.57, 104.07], 武汉: [30.59, 114.3], 西安: [34.34, 108.94], 重庆: [29.56, 106.55], 无锡: [31.49, 120.31],
};

const clone = (o) => JSON.parse(JSON.stringify(o));
const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);
export function merge(base, patch) {   // 对象深度合并，数组整体替换
  const out = clone(base);
  for (const [k, v] of Object.entries(patch ?? {})) out[k] = isObj(v) && isObj(out[k]) ? merge(out[k], v) : clone(v);
  return out;
}

export function validate(set) {   // 返回 null 或 { field, error }
  const w = set.watch, c = set.weather, b = set.booth, r = set.replay;
  const range = (v, [lo, hi]) => typeof v === 'number' && v >= lo && v <= hi;
  if (w?.codes) {
    if (w.codes.length > LIMITS.watchMax) return { field: 'watch', error: `自选最多 ${LIMITS.watchMax} 只` };
    if (w.codes.some((x) => !/^\d{6}$/.test(x))) return { field: 'watch', error: '股票代码是 6 位数字' };
    if (new Set(w.codes).size !== w.codes.length) return { field: 'watch', error: '已经在自选里了' };
  }
  if (w?.interval !== undefined && !range(w.interval, LIMITS.watchInterval)) return { field: 'watch', error: `轮播间隔 ${LIMITS.watchInterval.join('–')} 秒` };
  if (w?.view !== undefined && !['single', 'list'].includes(w.view)) return { field: 'watch', error: '视图只能是 单股轮播 / 列表' };
  if (c?.cities && c.cities.length > LIMITS.cityMax) return { field: 'weather', error: `城市最多 ${LIMITS.cityMax} 个` };
  if (c?.cities && new Set(c.cities.map((x) => x.name)).size !== c.cities.length) return { field: 'weather', error: '这个城市已经加过了' };
  if (c?.interval !== undefined && !range(c.interval, LIMITS.weatherInterval)) return { field: 'weather', error: `轮播间隔 ${LIMITS.weatherInterval.join('–')} 秒` };
  if (b?.dwell !== undefined && !range(b.dwell, LIMITS.boothDwell)) return { field: 'booth', error: `每页停留 ${LIMITS.boothDwell.join('–')} 秒` };
  if (r?.speed !== undefined && !range(r.speed, LIMITS.replay)) return { field: 'replay', error: `回放速度 ${LIMITS.replay.join('–')}×` };
  return null;
}

const KEY = 'deskbot.sim.profile';
const NO_REPLY_MS = 3000;

export class ProfileSync {
  // io: { connected():bool, send(msg) }
  constructor(io) {
    this.io = io;
    this.listeners = new Set();
    this.state = 'offline';   // offline | pending | applied | error | noreply
    this.error = '';          // 最近一次错误（{field,error}）
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(KEY)); } catch {}
    this.profile = merge(DEFAULTS, saved ?? {});
    this.confirmed = clone(this.profile);
    this.timer = null;
    this.searchWait = null;
    this.mode = this.profile.mode;
  }

  onChange(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit() { for (const fn of this.listeners) fn(this); }
  save() { try { localStorage.setItem(KEY, JSON.stringify(this.profile)); } catch {} }
  setState(state, error = '') { this.state = state; this.error = error; this.emit(); }

  // 改设置：先本地乐观生效，连着中枢就发过去等确认；没连就直接存下
  set(patch) {
    const bad = validate(patch);
    if (bad) { this.setState('error', bad); return false; }
    this.profile = merge(this.profile, patch);
    this.save();
    if (!this.io.connected()) { this.confirmed = clone(this.profile); this.setState('offline'); return true; }
    this.io.send({ t: 'profile', set: patch });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.setState('noreply'), NO_REPLY_MS);   // 中枢没应答（旧版本？）：设置只在本机生效
    this.setState('pending');
    return true;
  }

  // 中枢广播来的完整设置：以它为准
  applyRemote(p) {
    clearTimeout(this.timer);
    this.profile = merge(DEFAULTS, p ?? {});
    this.confirmed = clone(this.profile);
    this.save();
    this.setState('applied');
  }

  // 中枢对我们这次修改的答复
  result(m) {
    clearTimeout(this.timer);
    if (m.ok) return this.setState('applied');
    this.profile = clone(this.confirmed);   // 被拒绝：回到上次确认的状态
    this.save();
    this.setState('error', { field: m.field ?? '', error: m.error || '中枢拒绝了这次修改' });
  }

  switchMode(name) {
    this.mode = name;
    if (this.io.connected()) this.io.send({ t: 'mode', name });
    this.emit();
  }

  ctl(op) { if (this.io.connected()) this.io.send({ t: 'mode_ctl', op }); }

  // 搜股票：连着中枢问中枢，3 秒没回或离线就用本地那张小表
  search(q) {
    q = q.trim();
    const local = () => SYMBOLS.filter((s) => s.code.startsWith(q) || s.name.includes(q)).slice(0, 8);
    if (!q) return Promise.resolve([]);
    if (!this.io.connected()) return Promise.resolve(local());
    return new Promise((resolve) => {
      const t = setTimeout(() => { this.searchWait = null; resolve(local()); }, 3000);
      this.searchWait = { q, done: (items) => { clearTimeout(t); this.searchWait = null; resolve(items); } };
      this.io.send({ t: 'symbols', q });
    });
  }
  symbolsResult(m) { if (this.searchWait && (m.q === undefined || m.q === this.searchWait.q)) this.searchWait.done(m.items ?? []); }

  // 加城市：连着中枢只发名字（坐标由中枢查）；离线时查本地小表
  addCity(name) {
    name = name.trim();
    if (!name) return false;
    const cities = this.profile.weather.cities;
    if (this.io.connected()) return this.set({ weather: { cities: [...cities, { name }] } });
    const ll = CITIES[name];
    if (!ll) { this.setState('error', { field: 'weather', error: `离线时只认识：${Object.keys(CITIES).join('、')}` }); return false; }
    return this.set({ weather: { cities: [...cities, { name, lat: ll[0], lon: ll[1] }] } });
  }

  nameOf(code) { return this.profile.watch.names?.[code] || SYMBOLS.find((s) => s.code === code)?.name || code; }
}
