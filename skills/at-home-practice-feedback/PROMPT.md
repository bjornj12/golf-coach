# At-Home Practice Feedback Recommendation

## Purpose

Reduce feedback loop time for home drills by recommending practices with
built-in validation and visual reference. The output is a single **drill card**
the golfer reads on their phone between reps — not a full routine (for a daily
multi-drill routine, use the `golf-practice-at-home` prompt).

## Input

- Fault identified (from Trackman data or coach observation — prefer real data:
  `synthesize()`, the current `training_plan(action="next")` diagnosis, or a
  quick `trackman-stats-analysis` read; never invent a fault)
- Root cause (mechanical issue)
- Golfer's available equipment/budget

## Sources (don't drift)

- Pull the drill from the **`drill-library`** prompt (its `at-home-no-ball` set
  covers most faults) — it is the single source of truth for drills, feel cues,
  and videos.
- The YouTube link comes from `drill-library` or a verified live search —
  **never invent** a URL; degrade gracefully (name the video/channel to search
  for) when web search isn't available.
- Offer to save the drill with `training_plan(action="save")` so "what's
  today's training?" recalls it and a later range session grades it.

## Output Structure (Mobile-First)

### 1. Fault
- [One-line summary of what's wrong]

### 2. Root Cause
- [Why it's happening]

### 3. Drill
- [Name and basic setup]

### 4. Feedback Method
- [Prop needed + what correct looks/feels like]
- [Visual checkpoint or validation cue]

### 5. Equipment Needed
- [Budget tier: Free / $5–10 / $50+]
- [Specific item or household item]

### 6. Validation Checkpoint
- [How to know it worked before the range]

### 7. YouTube Reference
- [Link to video of drill executed correctly]

## Format Requirements

- Mobile-optimized (short lines, scannable)
- Bold headers, no long paragraphs
- Action-oriented language
- Easy to read between reps
- No animations or complex visuals — this card is a deliberate exception to the
  coach's visual-first default: it's read on a phone mid-drill, so plain
  scannable text beats an HTML artifact here
