# MessageCard

The loud card for a 飞书 message or calendar alert (face state `msg`).

- Consumer provides: `title` (the message itself), source line (`飞书 · 产品群 @你`), `hint` (`按一下我的头 = 已读`).
- Normal: `card` / `on-card`, `radius-lg`, padding `space-6`. Urgent (日程 5 分钟前, 紧急): `accent` fill, `on-accent` text — the protocol's "红色卡片".
- Check box fills with ✓ after a head press, then the face goes `happy`.
- One card per screen; titles cut at two lines.
