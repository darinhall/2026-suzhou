# MarketCard

Watch-list card for face state `mkt` — name, code, change %, sparkline, hint.

- Consumer provides the protocol's `card`: `name`, `code`, `pct`, `vol_ratio`, `spark[]`, `hint`.
- `pct` in `numeral-xl`-style dot face (72px here), `up` or `down`, ALWAYS with ▲/▼ and sign.
- Sparkline: bars in `rule`, the latest bar in `accent`.
- The disclaimer `示例数据 · 不构成投资建议` in `caption` is required, every time.
