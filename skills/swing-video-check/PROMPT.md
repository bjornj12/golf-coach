# Swing Video Check

Turn one phone clip of one golf swing into short, drill-specific feedback. A
clip shows **one camera angle** (one phone — never assume a second view
exists). Never pretend to watch video natively: extract still frames with
ffmpeg, view those as images, and report only what that angle actually shows.

**Capability check first.** This needs (a) a way to run shell commands with
`ffmpeg` available and (b) the ability to view the extracted image frames. If
this client can't do both, say plainly that swing video can't be analyzed here
— never fake a read.

## Input contract

- **Filename** `DATE_CLUB_ACTION.mp4` (or `.mov`), e.g.
  `2026-07-17_driver_grip-reset.mp4`, `2026-07-17_7iron_9to3.mp4`. Parse
  **date**, **club**, and **action** (the drill / intent — what the rep is
  graded against). Metadata typed in chat merges in and **wins over the
  filename on conflict**.
- The user should state **angle** (`face-on` / `down-the-line` /
  `hands-closeup`) and **speed** (`normal` / `slow-mo`). If angle is missing,
  infer it from the frames and **state the assumption before analyzing**.
- **Unusable clip** (feet or ball out of frame, too dark, swing cut off): don't
  force an analysis — give the one-line problem plus the filming card below.
- Keep extracted frames in a temp directory; never save them into the project.

## Step 1 — Ground in the current practice card (never hardcode faults)

Read **`practice-card.md`** and **`driver-rebuild-tracker.md`** from the
project folder (look next to the clip first, then the project root). Extract
four things and grade the rep against them:

1. **Active fault chain** — the root cause being rebuilt and its knock-ons.
2. **Rebuild direction** — what counts as **progress right now**. Rebuilds
   often deliberately overshoot: if the card says neutral-will-feel-like-a-hook,
   then a closing face / draw bias is PROGRESS, not a fault. Grade with the
   card's sign, not textbook neutral.
3. **Checkpoints** — the concrete positions the card names (e.g. club in the
   fingers not the palm, knuckle count, trail-hand V, glove-wear point).
4. **Standing red flags** — patterns the card says to always call out (e.g.
   clean strike + still-open face = the old swing sneaking back).

The card is the source of truth: when it changes, the verdicts change with it.
If neither file is found, say so and give a generic read explicitly flagged as
**ungrounded**.

## Step 2 — Extract frames (ffmpeg)

```bash
# Clip metadata (duration / fps / size):
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,avg_frame_rate:format=duration \
  -of default=noprint_wrappers=1 clip.mp4

# Sweep the whole clip (4 fps; use fps=8 for slow-mo — the motion is stretched):
ffmpeg -v error -i clip.mp4 \
  -vf "fps=4,scale='min(1024,iw)':'min(1024,ih)':force_original_aspect_ratio=decrease" \
  -q:v 3 OUTDIR/sweep_%03d.jpg          # frame N is at ~(N-1)/4 s

# Dense pass over the ~0.5 s around impact (frame N at FROM + (N-1)/30 s):
ffmpeg -v error -ss 1.2 -i clip.mp4 -t 0.6 \
  -vf "fps=30,scale='min(1024,iw)':'min(1024,ih)':force_original_aspect_ratio=decrease" \
  -q:v 3 OUTDIR/impact_%03d.jpg
```

From the sweep, pick the swing positions by timestamp — **address,
mid-takeaway, top, impact/pre-impact, follow-through** — then run the dense
pass around impact (extra dense for slow-mo). **View only the picked frames**
(5–8 images), not every frame. No ffmpeg → tell the user to install it (macOS:
`brew install ffmpeg`) and stop.

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
