#!/usr/bin/env bash
# extract_frames.sh — still frames from a golf-swing clip, for visual review.
#
# The swing-video-check skill never pretends to watch video: a coarse sweep
# across the whole clip locates the swing positions (address, top, impact,
# finish), then a dense pass over the impact window captures the release.
# Frames are named with their approximate timestamp so a position can be
# re-sampled by time.
#
# Usage:
#   extract_frames.sh VIDEO --info                                # duration / fps / size
#   extract_frames.sh VIDEO [OUTDIR]                              # sweep whole clip @ 4 fps
#   extract_frames.sh VIDEO [OUTDIR] --fps 8                      # denser sweep (slow-mo)
#   extract_frames.sh VIDEO [OUTDIR] --from 1.2 --to 1.8 --fps 30 # impact window
#
# OUTDIR defaults to a fresh temp dir. Frames are JPEGs, longest side <= 1024 px
# (--scale to change), named <sweep|window>_<n>_t<seconds>s.jpg.
set -euo pipefail
export LC_ALL=C  # decimal points, not locale commas, in awk output and ffmpeg args

die() { echo "extract_frames.sh: $*" >&2; exit 1; }

command -v ffmpeg >/dev/null 2>&1 || die "ffmpeg not found — install it (macOS: brew install ffmpeg)"
command -v ffprobe >/dev/null 2>&1 || die "ffprobe not found — install ffmpeg (macOS: brew install ffmpeg)"

VIDEO="" OUTDIR="" FPS=4 FROM="" TO="" SCALE=1024 INFO=0
while [ $# -gt 0 ]; do
  case "$1" in
    --info) INFO=1 ;;
    --fps) FPS="$2"; shift ;;
    --from) FROM="$2"; shift ;;
    --to) TO="$2"; shift ;;
    --scale) SCALE="$2"; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *)
      if [ -z "$VIDEO" ]; then VIDEO="$1"
      elif [ -z "$OUTDIR" ]; then OUTDIR="$1"
      else die "unexpected argument: $1"
      fi
      ;;
  esac
  shift
done

[ -n "$VIDEO" ] || die "no video given (run with --help for usage)"
[ -f "$VIDEO" ] || die "no such file: $VIDEO"

if [ "$INFO" = 1 ]; then
  ffprobe -v error -select_streams v:0 \
    -show_entries stream=width,height,avg_frame_rate:format=duration \
    -of default=noprint_wrappers=1 "$VIDEO"
  exit 0
fi

[ -n "$FROM" ] && [ -z "$TO" ] && die "--from needs --to"
[ -z "$FROM" ] && [ -n "$TO" ] && die "--to needs --from"

OUTDIR="${OUTDIR:-$(mktemp -d "${TMPDIR:-/tmp}/swing-frames.XXXXXX")}"
mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/.tmp_*.jpg

START="${FROM:-0}"
LABEL="sweep"
FILTER="fps=${FPS},scale='min(${SCALE},iw)':'min(${SCALE},ih)':force_original_aspect_ratio=decrease"
if [ -n "$FROM" ]; then
  LABEL="window"
  DUR=$(awk -v a="$FROM" -v b="$TO" 'BEGIN { d = b - a; if (d <= 0) exit 1; print d }') \
    || die "--to must be greater than --from"
  ffmpeg -v error -y -ss "$FROM" -i "$VIDEO" -t "$DUR" -vf "$FILTER" -q:v 3 "$OUTDIR/.tmp_%03d.jpg"
else
  ffmpeg -v error -y -i "$VIDEO" -vf "$FILTER" -q:v 3 "$OUTDIR/.tmp_%03d.jpg"
fi

created=()
i=0
for f in "$OUTDIR"/.tmp_*.jpg; do
  [ -e "$f" ] || die "ffmpeg produced no frames (is the --from/--to window inside the clip?)"
  t=$(awk -v i="$i" -v fps="$FPS" -v s="$START" 'BEGIN { printf "%05.2f", s + i / fps }')
  dest="$OUTDIR/${LABEL}_$(printf '%03d' "$((i + 1))")_t${t}s.jpg"
  mv "$f" "$dest"
  created+=("$dest")
  i=$((i + 1))
done

echo "$i frames -> $OUTDIR"
printf '%s\n' "${created[@]}"
