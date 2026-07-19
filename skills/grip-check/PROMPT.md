# Grip Check

The grip is the first link in the chain, so the coach never prescribes without
seeing it. Read the golfer's CURRENT grip from images (or a short clip) and
classify it **too weak / neutral / too strong** — graded against the practice
card's target, not textbook neutral.

**Capability check first.** This needs the ability to view the user's images
(and, for clips, a way to run `ffmpeg` to extract stills). If this client
can't, say plainly that the grip can't be checked here — never fake a read.

## Required views — both, face-forward

| View | Shows |
|------|-------|
| **Club UP** — finished grip held up toward the camera, shaft vertical, hands at chest height | club in **fingers vs palm** (shaft diagonal across the fingers, heel pad riding on top — vs crossing the palm), thumb placement, hands married |
| **Club DOWN** — normal address, camera face-on at hand height | the grip as it actually plays: **lead-hand knuckle count**, both **V directions** relative to chin / trail shoulder |

One view missing → say exactly what can't be judged without it and ask for it.
Grade only what a given view shows — "not visible in this view", never a guess.

## What to read

- **Fingers vs palm** (club-UP): a palm grip also shows up as glove wear low in
  the palm — note it if visible.
- **Lead-hand knuckles** (club-DOWN): how many visible — fewer = weaker, more =
  stronger.
- **Lead-hand V** (thumb–index): pointing at the chin = weak side; at the trail
  shoulder = stronger.
- **Trail-hand V**: chin / lead shoulder = weak; trail shoulder = neutral-strong.
- **Hands married**: trail-hand lifeline over the lead thumb, no gap.

Classify: **too weak** = under ~2 knuckles, V's at the chin or lead side;
**neutral** = ~2 knuckles, V's between chin and trail shoulder; **too strong**
= 3+ knuckles, V's outside the trail shoulder.

## Grade against the practice card (never hardcode the target)

Read **`practice-card.md`** and **`driver-rebuild-tracker.md`** from the
project folder. The card sets the *target*: a deliberate strong-side rebuild
(e.g. 2–2½ knuckles, trail V to the trail shoulder) means textbook neutral is
still **too weak for the plan** — call it that. Card files missing → grade vs
textbook neutral, explicitly flagged as **ungrounded**.

## Video input

A short clip works — extract stills rather than pretending to watch video:

```bash
ffmpeg -v error -i grip.mp4 \
  -vf "fps=2,scale='min(1024,iw)':'min(1024,ih)':force_original_aspect_ratio=decrease" \
  -q:v 3 OUTDIR/grip_%03d.jpg
```

Pick the clearest frame per view and analyze those.

## Output — short and scannable

```
VIEWS:     up ✓/✗ · down ✓/✗        (missing view → ask, don't guess)
IN HAND:   fingers / palm / ? unclear
KNUCKLES:  n visible
LEAD V:    chin / trail shoulder / outside
TRAIL V:   chin / trail shoulder / outside
READ:      too weak / neutral / too strong   (vs the card's target)
VERDICT:   pass / adjust / retake
```

Then **ONE sentence**: the single grip change for the next rep (or "grip
matches the card — hold it there"). This is a qualitative visual read — it
complements Trackman's ball data, it measures nothing.

## How to shoot it (print on request, or when a view is unusable)

- **Two shots, face the camera:** (1) finished grip held **up** at chest
  height, shaft vertical; (2) normal address with the club **down**, camera at
  hand height.
- **Fill the frame with the hands**, good light, no backlight. Glove on is fine
  — the wear pattern is evidence.
