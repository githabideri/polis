# Web UI design contract

Date: 2026-09-27 (13th pass)

## What this UI is

An **operations console for watching and nudging a live game world**, not a
website. Its consumer is a human supervising a bot: the center of gravity is
the live game image; everything else is status, control, and log. The four
functional areas the UI must keep distinct:

1. **Stage** — what is happening (live VNC, frame/screenshot feed)
2. **World** — who/what exists (bots with state, players)
3. **Control** — how to nudge it (movement/view pad, bot actions)
4. **Console** — what happened (event log, command line)

## Anti-slop research (the "unslop" question)

The community skill in question is **unslop-ui** (v1/v2,
r/ClaudeAI 2026; dataset: github.com/JCarterJohnson/vibecoded-design-tells —
3.2M posts across 47 AI/SaaS subs + 3,033 comments on "AI sites look the
same"). Its weighted list of what people actually complain about:

- the default shadcn/Tailwind look
- **purple/indigo as the primary color**
- **purple→blue gradients and gradient heading text**
- **unprompted neon glow**
- **emoji used as icons**
- **Inter/Geist default fonts**
- centered hero + three feature cards

Patterns the data says people do *not* complain about (do not avoid):
mesh/aurora backgrounds, bento grids, glassmorphism.

**The important part is the community's response to the skill** (the v1 and
v2 "after" screenshots got roasted as "slop v2" / "reslop-ui"): the anti-slop
default (cream/beige/earth palette + serif display face) is *itself* now a
recognizable AI signature. Consensus advice:

> "best anti-slop practice is simply to define your own colors, fonts and
> use layout reference image or some specific UI library ... you need to
> insert human taste, drop in some heavily opinionated instructions and
> references" (Johny-115, r/ClaudeAI)

So this UI follows **neither** default — no purple/gradient/neon/emoji/Inter,
and no beige/serif "anti-slop" tell. The design is derived from the function:

## Decisions (function-derived, stable)

- **Dark instrument panel.** The primary content is live game footage; the
  chrome must recede. Charcoal scale, never black-purple.
- **Palette**: warm off-white text (`#ddd9d0`) on layered charcoal
  (`#0c0e10` / `#121518` / `#1a1e23`), structural lines at `#262c33`.
  Single accent: **calm amber `#d9a05f`** (active/focus/selection). Semantic
  status colors only where they mean something: up/ok `#7fbf8f` green,
  attention `#d9a05f` amber, down/error `#d96f6f` red. No gradients, no
  glow, no glassmorphism, no shadows-for-decoration.
- **Type**: IBM Plex Sans (400/500/600) for labels, **IBM Plex Mono
  (400/500)** for all data (coords, clock, ids, log, commands) — self-hosted
  woff2 in `fonts/` (no CDN; the UI must work on LAN/Tailscale offline).
  13px base; 11px uppercase letter-spaced section labels.
- **Icons**: inline SVG line glyphs and unicode arrows (↑ ↓ ← → ↺ ⏎) — never
  emoji.
- **Layout**: top bar (identity + world state + connection) / left rail
  World / center Stage / right rail Control / bottom Console. The Stage is
  the largest area. No hero, no cards, no marketing structure.
- **Controls are physical, not clicky.** Movement and view use **hold to
  repeat** (pointer down = continuous, ~100 ms cadence; up/leave = stop) and
  keyboard bindings (arrows/WASD). A dedicated 180° "turn around" command
  because "look behind me" was the actual pain (pressing +15° eight times).
  Discrete one-shot commands are what caused the 2026-09-26 NaN crash — the
  server side keeps its guards (pole margin, NaN sanitization), the UI side
  keeps a minimum command interval, but the *UX* fix is continuity, not
  faster spamming.
- **State is at a glance.** Bots show a status dot (idle/mission/working)
  and the world shows time + counts in the top bar; nothing important lives
  in a tooltip.
- **Naming**: stable, functional, no version numbers (the old `ui2` in the
  URL is gone; the page is `/polis/ui/`).

## Change bar

If you change the palette or typeface, you are changing the identity — say
why in the commit. Adding a functional area requires a place in the four-area
map above.
