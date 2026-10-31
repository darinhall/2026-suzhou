"""T04：一句话 → 意图 + 股票代码（规则优先，认不出再交给大模型，见 brain/qa.py）。

    Router().route("帮我看看中芯国际的行情") → Intent(kind="quote", codes=["688981"], period_days=1)

股票名识别：全名 → 别名（宁王、茅台）→ 拼音同音（语音识别的错字：宁德时带 → 宁德时代）。
名单来自 data/names.py（内置 + PandaAI 全市场缓存）。语音识别常把「异动」听成「移动 / 一动」，这里统一纠正。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))

ALIASES = {   # 口语 / 简称 → 代码
    "宁王": "300750", "宁德": "300750", "茅台": "600519", "招行": "600036", "中芯": "688981",
    "比亚迪": "002594", "平安": "601318", "五粮液": "000858", "工行": "601398",
}
ASR_FIX = [(re.compile(r"(移动|一动|易动|意动|异洞)"), "异动"),
           (re.compile(r"(大阪|大班|打盘|大判|大潘)"), "大盘")]   # 11-01 现场：「大盘怎么样」被听成「大阪怎么样」


@dataclass
class Intent:
    kind: str                 # quote yesno compare overview sector sector_top watchlist advice control explain research watch_add watch_remove watch_list sim_start sim_stop unknown
    codes: list[str] = field(default_factory=list)
    period_days: int = 1
    text: str = ""
    op: str = ""              # control：next / prev / pause / resume
    sector: tuple = ()        # sector：(说法, 指数代码, 指数名)，见 brain/sectors.py


def _pinyin(s: str) -> list[str]:
    from pypinyin import lazy_pinyin
    return lazy_pinyin(s)


class Router:
    def __init__(self, names: dict[str, str] | None = None):
        if names is None:
            import names as N
            names = N._load()
        self.names = {c: n for c, n in names.items() if n and len(n) >= 2}
        self._py: dict[str, list[str]] | None = None
        self.prev_codes: list[str] = []
        self.prev_sector: tuple = ()   # 上一次说到的行业：「这个板块 / 这个行业 / 这里面」指它

    # ---------- 股票 ----------
    def _name_py(self) -> dict[str, list[str]]:
        if self._py is None:
            self._py = {c: _pinyin(n) for c, n in self.names.items()}
        return self._py

    def find_codes(self, text: str) -> list[str]:
        hits: list[tuple[int, int, str]] = []   # (位置, -长度, 代码)
        for code, name in self.names.items():
            p = text.find(name)
            if p >= 0:
                hits.append((p, -len(name), code))
        for alias, code in ALIASES.items():
            p = text.find(alias)
            if p >= 0:
                hits.append((p, -len(alias), code))
        for m in re.finditer(r"(?<!\d)([036]\d{5})(?!\d)", text):   # 直接说代码
            if m.group(1) in self.names:
                hits.append((m.start(), -6, m.group(1)))
        if not hits:   # 同音字：语音识别错字
            tp = _pinyin(text)
            for code, py in self._name_py().items():
                L = len(py)
                for i in range(len(tp) - L + 1):
                    if tp[i:i + L] == py:
                        hits.append((i, -L, code))
                        break
        hits.sort()
        out, covered = [], []
        for p, negl, code in hits:   # 长名字优先，重叠的短名字不要（「中芯国际」里的「中芯」）
            if code in out or any(a <= p < b for a, b in covered):
                continue
            out.append(code)
            covered.append((p, p - negl))
        return out

    # ---------- 意图 ----------
    def route(self, text: str) -> Intent:
        t = text.strip()
        for rx, rep in ASR_FIX:
            t = rx.sub(rep, t)
        t = re.sub(r"[，。！？、,.!?\s]", "", t)
        codes = self.find_codes(t)
        period = 22 if re.search(r"一个月|一月|这个月|近一月", t) else 5 if re.search(r"一周|一个星期|这周|这礼拜|五天", t) else 1

        def it(kind, cs=None, **kw):
            res = Intent(kind, list(codes if cs is None else cs), period, text, **kw)
            if res.codes:
                self.prev_codes = res.codes
            if res.sector:
                self.prev_sector = res.sector
            return res

        sec: tuple = ()
        if not codes:   # 行业：这句话里直接说了，或者用「这个板块」指上一次说的
            from brain import sectors
            sec = sectors.find(t) or (self.prev_sector if re.search(r"这个板块|该板块|这个行业|这个领域|这个方向|这里面|板块里|行业里", t) else ()) or ()

        if "模拟" in t and re.search(r"停|结束|关|别|退出|取消", t):
            return it("sim_stop", [])
        if "异动" in t and "模拟" in t:
            return it("sim_start", [])
        ctl = {"下一只": "next", "下一个": "next", "上一只": "prev", "上一个": "prev", "暂停": "pause", "继续": "resume"}
        if t in ctl:
            return it("control", [], op=ctl[t])
        this = codes or (self.prev_codes[:1] if re.search(r"它|这只|这个", t) else [])   # 「把它加到自选」= 上一次说的那只
        if re.search(r"加到自选|加入自选|加自选|关注", t) and this:
            return it("watch_add", this)
        if re.search(r"删掉|删除|移除|移出|去掉|取消关注|不看.*了|不关注", t) and this:
            return it("watch_remove", this)
        if re.search(r"自选.*(有哪些|有什么|是什么|列表)", t):
            return it("watch_list", [])
        if re.search(r"推荐|该不该|应不应该|应该.*[买卖]|能不能买|可以买|值得买|全仓|满仓|抄底|买什么|买哪|卖不卖|要不要[买卖]", t):
            return it("advice", sector=sec)   # 说到了行业：拒绝推荐后，讲这个行业成分股的数据
        if re.search(r"比较|对比|比一下|比呢|哪个强|哪个好|和.+比|跟.+比", t):
            cs = codes if len(codes) >= 2 else (self.prev_codes + [c for c in codes if c not in self.prev_codes])[:3]
            return it("compare", cs)
        if re.search(r"^(为什么|为啥|怎么回事)", t):
            return it("explain", self.prev_codes)
        if re.search(r"自选.*(谁|哪只|哪个|最强|最弱|怎么样|表现)", t):
            return it("watchlist", [])
        if sec and re.search(r"哪只|哪些|哪几只|成分|个股|龙头|领涨|涨得最|跌得最|最强|最弱", t):
            return it("sector_top", [], sector=sec)   # 行业里涨跌最多的成分股（只讲数据）
        if sec:   # 行业 / 板块：「生物医药现在怎么样」→ 行业指数（快速通道）
            return it("sector", [], sector=sec)
        if not codes and re.search(r"大盘|指数|市场|上证|深证|创业板|沪深|a股|A股", t):
            return it("overview", [])
        if codes and re.search(r"概念|行业|板块|题材|业绩|财报|预告|快报|营收|利润|净利|龙虎榜|融资|融券|两融|北向|股东|解禁|估值|市盈率|市净率|分红|港股|美股|主营|做什么的", t):
            return it("research")   # 要查更多数据：交给大模型 + PandaAI MCP（brain/agent.py）
        if codes and re.search(r"涨了吗|跌了吗|涨了没|跌了没|涨没涨|跌没跌|是不是[涨跌]|[涨跌]了没有|有没有[涨跌]", t):
            return it("yesno")
        if codes:
            return it("quote")
        return it("unknown", [])
