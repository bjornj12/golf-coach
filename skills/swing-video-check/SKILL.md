---
name: swing-video-check
description: Use when the user shares a filmed golf swing — an *.mp4/*.mov clip dropped into the project (named like 2026-07-17_driver_grip-reset.mp4) — or says "check my swing", "here's my grip rep", "analyze this driver clip", "did I square it". One camera angle per clip. Extracts key frames with ffmpeg and returns a short drill-scoped checklist plus one swing thought, grounded in the current practice card. Qualitative visual read — complements Trackman, measures nothing.
---

# Swing Video Check

Turn one phone clip of one swing into short, drill-specific feedback. A clip
shows **one camera angle** (one phone — never assume a second view exists).
Never pretend to watch video natively: extract still frames with ffmpeg, view
those, and report only what that angle actually shows.

## Input contract

- **Filename** `DATE_CLUB_ACTION.mp4` (or `.mov`), e.g.
  `2026-07-17_driver_grip-reset.mp4`, `2026-07-17_7iron_9to3.mp4`,
  `2026-07-17_driver_50pct-draw.mp4`. Parse **date**, **club**, and **action**
  (the drill / intent — what the rep is graded against). Metadata typed in chat
  merges in and **wins over the filename on conflict**.
- The user should state **angle** (`face-on` / `down-the-line` /
  `hands-closeup`) and **speed** (`normal` / `slow-mo`). If angle is missing,
  infer it from the frames and **state the assumption before analyzing**
  ("Reading this as face-on — chest pointing at the camera").
- **Unusable clip** (feet or ball out of frame, too dark, swing cut off): don't
  force an analysis — give the one-line problem plus the filming card below.
- Never commit clips or extracted frames; frames go in a temp dir (the session
  scratchpad).

## Step 1 — Ground in the current practice card (never hardcode faults)

Read **`practice-card.md`** and **`driver-rebuild-tracker.md`** from the
project (look next to the clip first, then the project root). Extract four
things and grade the rep against them:

1. **Active fault chain** — the root cause being rebuilt and its knock-on
   effects.
2. **Rebuild direction** — what counts as **progress right now**. Rebuilds
   often deliberately overshoot: if the card says neutral-will-feel-like-a-hook,
   then a closing face / draw bias is PROGRESS, not a fault. Grade with the
   card's sign, not textbook neutral.
3. **Checkpoints** — the concrete positions the card names (e.g. club in the
   fingers not the palm, knuckle count, trail-hand V, glove-wear point).
4. **Standing red flags** — patterns the card says to always call out (e.g.
   clean strike + still-open face = the old swing sneaking back).

The card is the source of truth: when it changes, this skill's verdicts change
with it. If neither file is found, say so and give a generic read explicitly
flagged as **ungrounded**.

## Step 2 — Extract frames (ffmpeg)

Use `scripts/extract_frames.sh` in this skill's folder; frames land in a temp
dir, named with their approximate timestamp.

```bash
scripts/extract_frames.sh clip.mp4 --info                    # duration / fps / size
scripts/extract_frames.sh clip.mp4 OUTDIR                    # sweep: 4 fps, whole clip
scripts/extract_frames.sh clip.mp4 OUTDIR --fps 8            # denser sweep for slow-mo
scripts/extract_frames.sh clip.mp4 OUTDIR --from 1.2 --to 1.8 --fps 30   # impact window
```

1. **Sweep** the whole clip (default 4 fps; slow-mo stretches the motion, so
   sweep denser).
2. From the sweep, pick the swing positions by timestamp: **address,
   mid-takeaway, top, impact/pre-impact, follow-through**.
3. **Dense pass** over the ~0.5 s around impact — that's where face and release
   live. Sample extra densely there for slow-mo clips.
4. **View only the picked frames** (5–8 images with Read), not every frame.

No ffmpeg installed → tell the user to `brew install ffmpeg` and stop. Script
missing → raw fallback:
`ffmpeg -v error -i clip.mp4 -vf "fps=4,scale='min(1024,iw)':'min(1024,ih)':force_original_aspect_ratio=decrease" -q:v 3 OUTDIR/frame_%03d.jpg`

## Step 3 — Read only what the angle shows

| Angle | Judge |
|-------|-------|
| face-on | grip position, face rotation through the ball, early extension, sway |
| down-the-line | swing path, lag, sequencing, release direction |
| hands-closeup | palm-vs-finger grip, knuckle count, wrist hinge, glove-wear point |

Anything not on that row — and anything the frames genuinely don't settle — is
**"not visible from this angle"**, never a guess. This is a frame-by-frame
visual read of stills: grip, sequencing, face relative to the body, rhythm. It
does not measure launch, spin, or path in degrees — Trackman does; say so
when a number would settle the question.

## Output — short and scannable, always

A checklist scoped to the angle + drill (only rows this angle can show):

```
GRIP:      ✓ fingers / ✗ palm / ? unclear
TAKEAWAY:  square / open / closed
RELEASE:   forearm rotation firing / delayed / over-rotated
FACE:      open / square / closed   (vs the stated intent + the card's rebuild direction)
STRIKE:    heel / center / toe      (if visible)
VERDICT:   pass / adjust / repeat
```

- **pass** — the rep does what the drill intends, in the card's direction.
- **adjust** — one clear thing off; fixable on the next rep.
- **repeat** — can't tell (unclear frames) or the rep broke down; film it again.

Then **ONE sentence**: the single thing to change on the next rep — one swing
thought, matching the practice card's one-swing-thought-per-ball rule. Never a
wall of text, never three fixes.

## Filming card (print on request, or when a clip is unusable)

- **One angle per clip.** Feet-to-head in frame, ball visible, room for the finish.
- **Full swing at normal speed**; add a separate slow-mo clip for the release / impact zone.
- **Name it `DATE_CLUB_ACTION.mp4`**, e.g. `2026-07-17_driver_grip-reset.mp4`.
