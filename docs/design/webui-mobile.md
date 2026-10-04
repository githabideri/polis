# Web UI — mobile / field variant (design addendum)

Date: 2026-10-04. Companion to `webui-design.md`. The desktop layout is
untouched; this document defines the narrow-viewport branch
(< 860 CSS px, what a phone gets today).

## What was observed

One day of use from a phone (1080×2400): the ≤860 px branch collapses
the grid into a single scrollable column of equal-weight fixed-height
panels, and the result fails at the console's own job:

1. **Primary navigation is a tiny horizontal icon strip**, clipped at
   the right edge with no scroll affordance — you can't see that it
   scrolls, and the buttons are well under 44 px.
2. **Panels clip each other**: the bot-list row is half-covered by the
   next panel's header; every region competes for the same scroll.
3. **The stage — the contract's center of gravity — is not first** and
   occupies only a third of the screen.
4. **The command line is buried** at the bottom of a long scroll, below
   the log — the operator's primary intervention channel is the hardest
   thing to reach.
5. **The console is mostly noise**: the UI's own 5 s world-clock poll is
   rendered as log lines (a fresh minute of screen = 12 lines that all
   say "1. June, Year 0, 00:xx"). Real events drown in heartbeats.
6. **Duplicated, cramped state** in the stage control row ("stream"
   checkbox *and* "stream on" label; four controls in one row).

Net: the console is unusable for the use case that motivated it —
watch the bot, intervene when needed, from wherever you are.

## What it has to do

A field operator has exactly two jobs: **see** (is the agent doing the
right thing?) and **intervene** (nudge / stop). The variant makes both
zero-scroll and one-thumb. Everything else is secondary.

## The variant (< 860 CSS px)

1. **Fixed bottom tab bar** replaces the top icon strip: the five areas
   (World · Stage · Console · Control · Oikistes) as tab *pages* —
   label + glyph, ≥44 px targets, always visible. Bottom navigation is
   the standard mobile primary nav: always visible, thumb-reachable,
   3–5 sections (UXPin, "Mobile Navigation Patterns": *"for
   right-handed users, the bottom of the screen is naturally within
   thumb reach … far more ergonomic than navigation options placed at
   the top"*; and the warning that icon-only strips lose context —
   hence labels, not glyphs alone). Each tab owns the whole screen for
   its region: no more sliced panels clipping each other.
2. **Stage is the default page**: video full-width; one compact control
   row under it — a single Live/Frames segmented control, one stream
   toggle (the duplicated "stream on" label goes away), capture-frame as
   an icon button on the right, and the **prominent STOP** (item 4).
   The movement/view hold-to-repeat pads live at the **top of the
   adjacent Control tab** (one tap from seeing to nudging) rather than
   under the video: moving them in the DOM would risk the pointer-
   capture state of an in-flight hold, and one tap is close enough to
   thumb-reachable. The continuity UX and minimum-interval guards are
   unchanged.
3. **Command bar pinned** above the tab bar on **every page** (the
   chat-app pattern): collapsed it is one line — prompt, input, submit —
   and focusing the input expands a log preview above it. One thumb-
   motion from anywhere on any page; the Console tab is the full log.
4. **One prominent STOP** in the stage control row (the existing one-shot
   `stop`; server guards unchanged). The agent-UX literature agrees on
   what operators value most: *step-level intervention* — pausing or
   overriding the agent's current step without restarting anything
   (Fuselab, "Agent UX: UI Design for AI Agents in 2026", Sep 2026:
   *"that override architecture became the most valued part of the
   entire interface"*). A phone operator's most important control is
   "stop what the agent is doing right now"; today it is buried.
   (Source caveat: vendor blog — used as directional evidence, not
   standard. The STOP also follows the console's own pilot rule:
   operator override is the safety boundary.)
5. **One line of "what the agent is doing now"** in the header — the
   mission system already computes the current step; the Oikistes tab
   already shows the mission. The same source calls this *proactive
   status*: "the agent communicates what it is doing before the user
   asks." One mono line, truncated: the difference between "I can watch
   from anywhere" and "I must open the app."
6. **Log hygiene (a code fix, not a layout one)**: the 5 s world-clock
   poll was issued as a `time` *command*, which recorded a command event
   per poll — 12 identical lines per minute, and it polluted the
   agent's action stream to boot. The fix is a plain `GET /polis/clock`
   (a GET is not a command: no event, no actor attribution) that the
   header clock reads instead. The log keeps real events only.
7. **Tap targets ≥ 44×44 CSS px** everywhere (WCAG 2.2 SC 2.5.5; the AA
   minimum is 2.5.8's 24 px — TestParty: *"interactive targets must be
   at least 24x24 CSS pixels … the stricter WCAG 2.5.5 (Level AAA)
   requires 44x44"*): tab bar, pad cells, stage tabs, entity rows, the
   STOP. The theme dots (the three little circles in the top bar — auto
   / dark / light) are dropped on mobile in favour of **auto** (follows
   the OS, the contract's default); the full toggle stays a desktop
   affordance — three 44 px dots would eat the header on a narrow screen.
8. **Landscape bonus**: a short-height/landscape query → two-pane
   Stage | Control, which is already close to the desktop grid — the
   "watch the bot while on the move" case.
9. **Header stays honest and compact**: wordmark + ONLINE dot + world
   clock + bot badge; everything else moves into the ⋯ menu.

## What does NOT change (contract)

Palette, typeface, iconography, the four-area map, hold-to-repeat
continuity, no-marketing-structure, and the entire desktop layout. This
is a **layout remap only**: the same areas, one at a time, ordered by
field-use frequency (Stage first). No new stack, no new functional
area, no theme change — the change-bar of the main contract is not
triggered; this addendum exists so the <860 branch stops being an
accident.

## Research notes

- UXPin, *Mobile Navigation Patterns: Pros and Cons*
  (uxpin.com/studio/blog/mobile-navigation-patterns-pros-and-cons):
  bottom tab bars "always visible, easy access, ergonomic"; 3–5 key
  sections; icon-only = lost context.
- UXPin *What Is Progressive Disclosure in UX? (2026)* / LogRocket /
  Justinmind: accordions and labeled tabs control vertical space on
  mobile ("especially effective on mobile where vertical space is
  limited") — the basis for tab-pages-over-stacked-panels.
- WCAG 2.2 target size: SC 2.5.8 (AA) 24×24 CSS px minimum; 2.5.5 (AAA)
  44×44 (AllAccessible / TestParty implementation guides).
- Fuselab, *Agent UX: UI Design for AI Agents in 2026*
  (fuselabcreative.com/ui-design-for-ai-agents, vendor blog, Sep 2026):
  transparency layer (what the agent is doing and why), step-level
  pause/override as the most-valued capability, proactive status.
  Adopted: items 4–5 above. Not adopted: confidence indicators and
  explanation trails (out of scope; the mission log already carries the
  why).
