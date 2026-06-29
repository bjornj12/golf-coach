#!/usr/bin/env bash
#
# release.sh — cut a release across every channel with one command.
#
# `main` is protected (no direct pushes), so the version bump goes through a PR
# that you merge; then the script tags and publishes. The flow:
#
#   1. bump the version in pyproject.toml, server.json, the plugin + marketplace
#      manifests, and the .mcpb manifest + launcher
#   2. run the quality gate (ruff + mypy + pytest)
#   3. push a release branch and open a PR (you as reviewer)
#   4. wait for you to merge it
#   5. tag vX.Y.Z and push the tag -> triggers the PyPI publish workflow (OIDC)
#   6. wait for the workflow; pause for your one-click `pypi` approval
#      (or --auto-approve), then wait until PyPI serves the version
#   7. publish server.json to the MCP Registry (mcp-publisher)
#
# __version__ is read from the installed metadata, so it never needs bumping.
#
# Usage:
#   scripts/release.sh <X.Y.Z | patch | minor | major> [--auto-approve] [--dry-run]
#
set -euo pipefail

REPO="bjornj12/trackman-mcp-client"
PKG="trackman-mcp"
WORKFLOW="publish.yml"
ENVIRONMENT="pypi"

cd "$(dirname "$0")/.."

err()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m⏸ %s\033[0m\n' "$*"; }

# --- parse args ------------------------------------------------------------
BUMP="" ; DRY_RUN=0 ; AUTO_APPROVE=0
for a in "$@"; do
  case "$a" in
    --dry-run)      DRY_RUN=1 ;;
    --auto-approve) AUTO_APPROVE=1 ;;
    -*)             err "unknown flag: $a" ;;
    *)              [ -z "$BUMP" ] || err "unexpected extra arg: $a" ; BUMP="$a" ;;
  esac
done
[ -n "$BUMP" ] || err "usage: scripts/release.sh <X.Y.Z|patch|minor|major> [--auto-approve] [--dry-run]"

for t in git gh uv curl python3; do command -v "$t" >/dev/null || err "missing required tool: $t"; done

# --- compute versions ------------------------------------------------------
CUR=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
NEW=$(python3 - "$CUR" "$BUMP" <<'PY'
import re, sys
cur, bump = sys.argv[1], sys.argv[2]
if re.fullmatch(r"\d+\.\d+\.\d+", bump):
    print(bump); raise SystemExit
major, minor, patch = (int(x) for x in cur.split("."))
if bump == "major":   major, minor, patch = major + 1, 0, 0
elif bump == "minor": minor, patch = minor + 1, 0
elif bump == "patch": patch += 1
else: sys.exit(f"not a version or patch|minor|major: {bump!r}")
print(f"{major}.{minor}.{patch}")
PY
)
[ "$NEW" != "$CUR" ] || err "new version equals current ($CUR) — nothing to release"
info "release: $CUR -> $NEW"

# Bump every version-bearing file; assert the expected hit count so a file that
# drifts in shape fails loudly instead of silently going un-bumped.
bump_versions() {  # $1 = apply|preview
  CUR="$CUR" NEW="$NEW" python3 - "$1" <<'PY'
import io, os, re, sys
cur, new, mode = os.environ["CUR"], os.environ["NEW"], sys.argv[1]
edits = [
    ("pyproject.toml",                  [(r'(?m)^version = "%s"' % re.escape(cur), 'version = "%s"' % new, 1)]),
    ("server.json",                     [(r'"version": "%s"' % re.escape(cur), '"version": "%s"' % new, 2)]),
    (".claude-plugin/plugin.json",      [(r'"version": "%s"' % re.escape(cur), '"version": "%s"' % new, 1)]),
    (".claude-plugin/marketplace.json", [(r'"version": "%s"' % re.escape(cur), '"version": "%s"' % new, 1)]),
    ("mcpb/manifest.json",              [(r'"version": "%s"' % re.escape(cur), '"version": "%s"' % new, 1)]),
    ("mcpb/pyproject.toml", [
        (r'(?m)^version = "%s"' % re.escape(cur), 'version = "%s"' % new, 1),
        (r'trackman-mcp>=%s' % re.escape(cur), 'trackman-mcp>=%s' % new, 1),
    ]),
]
for path, pairs in edits:
    text = io.open(path, encoding="utf-8").read()
    for pat, repl, want in pairs:
        text, n = re.subn(pat, repl, text)
        if n != want:
            sys.exit(f"{path}: pattern {pat!r} matched {n}, expected {want}")
    if mode == "apply":
        io.open(path, "w", encoding="utf-8").write(text)
    print(f"  {path}: {cur} -> {new}")
PY
}

# --- dry run ---------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  info "[dry-run] version changes that WOULD be made:"
  bump_versions preview
  info "[dry-run] then: gate -> push release-$NEW branch -> open PR -> wait for merge"
  info "[dry-run] then: tag v$NEW -> publish workflow ($([ "$AUTO_APPROVE" -eq 1 ] && echo auto-approve || echo manual approval)) -> PyPI -> mcp-publisher publish"
  ok "[dry-run] no changes made"
  exit 0
fi

# --- preconditions ---------------------------------------------------------
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || err "run from main (current: $(git rev-parse --abbrev-ref HEAD))"
[ -z "$(git status --porcelain)" ] || err "working tree not clean — commit or stash first"
git fetch origin --quiet
[ -z "$(git ls-remote --tags origin "refs/tags/v$NEW")" ] || err "tag v$NEW already exists on origin"
git pull --ff-only origin main --quiet

# --- bump + gate on a release branch ---------------------------------------
BRANCH="release-$NEW"
git rev-parse --verify "$BRANCH" >/dev/null 2>&1 && git branch -D "$BRANCH" >/dev/null
git checkout -b "$BRANCH" >/dev/null
info "bumping versions"; bump_versions apply
info "running quality gate (ruff + mypy + pytest)"
uv sync --extra dev >/dev/null
uv run ruff check src tests
uv run mypy
uv run pytest -q
ok "gate passed"

git commit -aqm "Release v$NEW"
git push -u origin "$BRANCH" --quiet
ok "pushed $BRANCH"

# --- open the release PR ----------------------------------------------------
gh pr create --base main --head "$BRANCH" --reviewer bjornj12 \
  --title "Release v$NEW" \
  --body "Version bump to v$NEW (every channel: pyproject, server.json, plugin + marketplace manifests, .mcpb manifest + launcher). Merge to publish — the release script then tags v$NEW and runs the PyPI + registry publish." \
  >/dev/null
PR=$(gh pr view "$BRANCH" --json number -q .number)
PR_URL=$(gh pr view "$BRANCH" --json url -q .url)
ok "opened release PR #$PR — $PR_URL"

# --- wait for you to merge --------------------------------------------------
warn "MERGE PR #$PR to continue: $PR_URL"
command -v open >/dev/null && open "$PR_URL" >/dev/null 2>&1 || true
for _ in $(seq 1 360); do          # ~60 min
  state=$(gh pr view "$PR" --json state -q .state 2>/dev/null || echo "")
  [ "$state" = "MERGED" ] && break
  [ "$state" = "CLOSED" ] && err "PR #$PR was closed without merging — aborting release"
  sleep 10
done
[ "$(gh pr view "$PR" --json state -q .state)" = "MERGED" ] || err "timed out waiting for PR #$PR to merge"
ok "PR #$PR merged"

# --- tag main and trigger the publish --------------------------------------
git checkout main --quiet
git pull --ff-only origin main --quiet
FILE_VER=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
[ "$FILE_VER" = "$NEW" ] || err "main is at $FILE_VER, expected $NEW after merge"
git tag -a "v$NEW" -m "$PKG $NEW"
git push origin "v$NEW" --quiet
SHA=$(git rev-parse HEAD)
ok "pushed tag v$NEW — publish workflow triggered"

# --- wait for the publish workflow -----------------------------------------
info "locating the publish run…"
RUN_ID=""
for _ in $(seq 1 30); do
  RUN_ID=$(gh run list --workflow "$WORKFLOW" --json databaseId,headSha \
            -q "[.[]|select(.headSha==\"$SHA\").databaseId][0]" 2>/dev/null || true)
  [ -n "$RUN_ID" ] && [ "$RUN_ID" != "null" ] && break
  RUN_ID=""; sleep 3
done
[ -n "$RUN_ID" ] || err "couldn't find a publish run for $SHA — check the Actions tab"
RUN_URL="https://github.com/$REPO/actions/runs/$RUN_ID"
info "run: $RUN_URL"

prompted=0
for _ in $(seq 1 300); do          # ~30 min
  [ "$(gh run view "$RUN_ID" --json status -q .status 2>/dev/null || echo "")" = "completed" ] && break
  PENDING=$(gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" -q 'length' 2>/dev/null || echo 0)
  if [ "${PENDING:-0}" -gt 0 ] && [ "$prompted" -eq 0 ]; then
    if [ "$AUTO_APPROVE" -eq 1 ]; then
      info "auto-approving the '$ENVIRONMENT' deployment"
      ENV_ID=$(gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" -q '.[0].environment.id')
      gh api -X POST "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" \
        -F "environment_ids[]=$ENV_ID" -f state=approved -f comment="release v$NEW" >/dev/null
    else
      warn "approve the '$ENVIRONMENT' deployment to publish: $RUN_URL"
      command -v open >/dev/null && open "$RUN_URL" >/dev/null 2>&1 || true
    fi
    prompted=1
  fi
  sleep 6
done
[ "$(gh run view "$RUN_ID" --json conclusion -q .conclusion 2>/dev/null || echo "")" = "success" ] \
  || err "publish workflow did not succeed — see $RUN_URL"
ok "PyPI publish workflow succeeded"

# --- wait for PyPI, then the registry --------------------------------------
info "waiting for $PKG $NEW on PyPI…"
for _ in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w "%{http_code}" "https://pypi.org/pypi/$PKG/$NEW/json")" = "200" ] \
    && { ok "PyPI is serving $NEW"; break; }
  sleep 6
done

if command -v mcp-publisher >/dev/null; then
  info "publishing server.json to the MCP Registry"
  mcp-publisher publish \
    || warn "mcp-publisher failed — run 'mcp-publisher login github' then 'mcp-publisher publish'"
else
  info "mcp-publisher not installed — finish the registry with:"
  echo "    brew install mcp-publisher && mcp-publisher login github && mcp-publisher publish"
fi

echo
ok "released v$NEW"
echo "    PyPI:    https://pypi.org/project/$PKG/$NEW/"
echo "    Release: https://github.com/$REPO/releases/tag/v$NEW"
