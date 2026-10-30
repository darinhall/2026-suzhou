DeskBot's face: a 3.5" touch screen on a desk robot that nods, turns and gets pressed on the head. The look is quiet instrument: warm grey, black type, numbers set big, and one orange signal. The screen is read from a metre away, at a glance, so each state shows **one** thing.

## Content

- Chinese first, short. Titles are the message itself ("评审会改到 16:00"), not a label for it ("新消息").
- The hint line says what the head does: "按一下我的头 = 已读", "按头 = 记入模拟单". Always the `=` form.
- Small labels are lowercase Latin or plain Chinese in `label`: `total amount`, `300750.SZ`, `飞书 · 产品群`.
- No emoji. Status is said with a glyph (▲ ▼ ● ✓ ×) or a word.
- Every market screen carries `示例数据 · 不构成投资建议` in `caption`, `ink-muted`. This is required.

## Colour

- `ground` for the whole screen; `surface` for panels on it; `surface-sunk` for empty cells and idle ticks.
- One `card` per screen, at most: it is the thing to look at. It inverts in dark (`on-card` on top).
- `ink` for text, `ink-muted` for secondary text. `ink-faint` is decoration only (picker neighbours, idle ticks).
- `accent` is the only colour that shouts: the live dot beside a numeral, the "now" tick on a ruler, the active/pause button. One accent element per screen. It is a fill; put `on-accent` on it, never accent text on `ground`.
- `lilac` belongs to the AI: listening, thinking, Qube suggestions. Never used for anything else.
- Market: `up` = red, `down` = green (A-share convention). Always pair with ▲/▼ and a +/− sign, so the states read without hue.

## Type

- `sans` (Geist) for words; `dot` (Doto, a dot-matrix face) for the hero number; `mono` (Geist Mono) for codes and units.
- One `numeral-xl` per screen. Clock-like figures use `numeral-lg` with the trailing part in `ink-muted` (09<span>:41</span>).
- `title` for the card's message, `headline` for a name, `body` for hints, `label` for codes and axis labels, `caption` for disclaimers.
- On device (LVGL) the faces are converted to bitmap fonts at these exact sizes; only include the glyph ranges used (digits, %, +, −, and the CJK set for the demo copy).

## Layout & shape

- Panel: 480 × 320 landscape. Gutter `space-4`; loud card padding `space-6`.
- Corners: cards `radius-md`, the loud card `radius-lg`, controls `radius-pill`.
- Flat by default. `shadow-lift` only on a floating circle button or a card stack.
- Hairlines in `rule`. Tick rulers are the house pattern: thin `rule` ticks, past ticks in `ink`, now in `accent`.

## Controls

- Circle buttons, 48px: primary `ink` fill with `on-ink` icon (+, ✓); secondary `surface` with `ink` icon (×); active `accent` with `on-accent` icon (pause).
- The head press is the main "confirm". Touch is for onboarding answers and dismissing.
- Focus/pressed: a 2px `ink` ring offset 2px (3:1+ on every surface).

## Motion

- Short and physical: 160ms ease-out for screen changes, timed to the body gesture (a nod lands as the card appears).
- Numerals roll digit by digit; dots blink at 1Hz for live.

## Iconography

- Line icons, 1.5px stroke, round caps, `ink`. Geometric glyphs (+ × ✓ ▲ ▼ ●) set in the text faces are preferred over drawn icons.
- No logo was provided; DeskBot is set in plain `headline` type.
