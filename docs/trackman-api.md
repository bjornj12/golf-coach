# Trackman Golf API — Discovered Endpoints

> **Status: DISCOVERED (Phase 0 done, 2026-06-27).** Findings below come from the
> public OIDC discovery document, the portal's login redirect, and
> **unauthenticated GraphQL introspection** (the schema is readable without a
> token). No real account, token, or credential was used — the only auth-server
> calls were probes with obviously-fake values to learn which grants are
> allowed. Nothing here is secret.

## TL;DR for the build

- **Data API**: single GraphQL endpoint, `POST https://api.trackmangolf.com/graphql`.
- **All player data hangs off the `me` root query** (`me.profile`, `me.hcp`,
  `me.scorecards`, `me.activities`, `me.activitySummary`, `me.equipment`).
- **Auth**: OIDC (Duende/IdentityServer) at `https://login.trackmangolf.com`.
  The web portal client is **confidential / backend-for-frontend** — the MCP
  cannot run the OAuth code exchange itself. The MCP authenticates by **using a
  Bearer access token captured from an authenticated portal session**
  (`Authorization: Bearer <token>` header on the GraphQL request).
- **Introspection is open**, so the schema can be re-checked anytime without auth.

## Authentication

OIDC discovery: `https://login.trackmangolf.com/.well-known/openid-configuration`

| Item | Value |
|------|-------|
| Issuer | `https://login.trackmangolf.com` |
| Authorize | `https://login.trackmangolf.com/connect/authorize` |
| Token | `https://login.trackmangolf.com/connect/token` |
| UserInfo | `https://login.trackmangolf.com/connect/userinfo` |
| JWKS | `https://login.trackmangolf.com/.well-known/openid-configuration/jwks` |
| Device auth | `https://login.trackmangolf.com/connect/deviceauthorization` |
| Grants supported | `authorization_code`, `client_credentials`, `refresh_token`, `implicit`, `password`, `device_code`, `token-exchange`, … |
| PKCE | `S256`, `plain` |

**Web portal client (observed from the portal login redirect):**
- `client_id = golf-portal.2dad6810-ef7c-4a0d-9c0a-0eaae2fb9e98`
- flow: `response_type=code` + PKCE (`code_challenge_method=S256`)
- `redirect_uri = https://portal.trackmangolf.com/account/callback`
- scopes: `openid profile email offline_access`
  `https://auth.trackman.com/dr/cloud https://auth.trackman.com/authorization`
  `https://auth.trackman.com/proamevent`

**Scopes relevant to player stats** (from `scopes_supported`):
`https://auth.trackman.com/playeractivities.read`,
`https://auth.trackman.com/playeractivities`,
`https://auth.trackman.com/golf/my-bag`,
`https://auth.trackman.com/golf/memberships.ro`,
`https://auth.trackman.com/person.read`, plus `openid profile email offline_access`.

### Why the MCP can't do the OAuth dance with the portal client

Probing `/connect/token` with the `golf-portal` client_id (and fake values)
returns `{"error":"invalid_client"}` for `password`, `refresh_token`, **and**
`authorization_code` grants. That means the portal client is **confidential**
(the code-for-token exchange runs server-side at `/account/callback`, a
backend-for-frontend). A public client doing pure browser PKCE would not require
client authentication here — this one does. So we cannot mint or refresh tokens
locally with this client_id.

### Auth strategy for the MCP (recommended)

**Bearer-token capture.** The user authenticates in a browser to
`https://portal.trackmangolf.com`; the access token the SPA sends to
`api.trackmangolf.com/graphql` is captured and handed to the MCP via
`TRACKMAN_TOKEN`. The MCP attaches it as `Authorization: Bearer <token>`.

- The MCP reads `TRACKMAN_TOKEN` from the environment (never logged, never
  returned to the model).
- Tokens last ~7 days (observed `iat`→`exp` = 604800s — a long-lived access
  token). On `401`, the MCP surfaces a clear "token expired — re-capture" error
  rather than failing silently.
- Capture can be **automated** with the `claude-in-chrome` browser tools: drive
  the portal login (user types their own password), then read the `Authorization`
  header off the GraphQL network request. This keeps passwords out of the MCP.

**Future options to investigate** (not needed for MVP): discover the native /
mobile-app `client_id` that permits `authorization_code`+PKCE with a loopback
redirect or the `device_code` flow — either would give a self-contained CLI
login without token capture.

## GraphQL Data API

- **Endpoint**: `POST https://api.trackmangolf.com/graphql`
- **Headers**: `Content-Type: application/json`,
  `Authorization: Bearer <token>` (required for `me`; introspection works without)
- **Style**: GraphQL (Hot Chocolate server). Collection fields use
  `skip`/`take` paging and return `…CollectionSegment { items, totalCount, pageInfo }`.

### Root query → `me`

`me : Me` is the entry point for the signed-in user. Key fields:

| `me` field | Type | Tool it backs |
|------------|------|---------------|
| `profile` | `Profile` | `trackman(action="profile")` |
| `hcp` | `Hcp` (`currentHcp`, `currentRecord`, `playerHistory`) | `trackman(action="profile"\|"handicap")` |
| `activities(kinds, timeFrom, timeTo, skip, take, includeHidden)` | `PlayerActivity[]` | `trackman(action="sessions"\|"session")` |
| `scorecards(skip, take, completed, numberOfHolesToPlay)` | `Scorecard[]` | `trackman(action="rounds")` |
| `activitySummary(timeFrom, timeTo, …)` | `ActivitySummary[]` | `trackman(action="summary")` |
| `equipment` | `AllEquipment` (`clubs`, `balls`) | `trackman(action="clubs")` |
| `playedWith`, `friends`, `visits`, `students`, `tournaments`, `leagues` | … | out of scope (MVP) |

### Key types (field names verbatim)

**Profile**: `id, dbId, playerName, fullName, firstName, lastName, gender, email,
nationality, birthDate, picture, outdoorHandicap, category, dexterity, …`

**Hcp**: `currentHcp: Float`, `currentRecord: HcpRecord`,
`playerHistory(onlyInAvg, skip, take): HcpRecord[]`.
**HcpRecord**: `hcpOld, hcpNew, adjustedGrossScore, scoreDifferential, isInAvg,
createdAt, scorecard, teeInfo, …`

**PlayerActivity** (interface — common fields): `id, time, kind (ActivityKind),
isHidden, player`. Concrete types include **`RangePracticeActivity`**
(`strokes: RangeStroke[]`, `numberOfStrokes`, `clubs`, `usedTargets`,
`location`) and **`CoursePlayActivity`** (`scorecard`, `gameType`, `grossScore`,
`netScore`, `toPar`, `thruHole`, `course`, …). Many other kinds exist (see enum).

**RangeStroke**: `time, bayName, club, teePosition, targetPosition,
measurement: RangeStrokeMeasurement`.
**RangeStrokeMeasurement**: `ballSpeed, carry, carrySide, total, totalSide,
launchAngle, launchDirection, landingAngle, maxHeight, ballSpin, spinAxis,
curve, hangTime, distanceFromPin, targetDistance, …`

**Scorecard**: `id, createdAt, startedAt, finishedAt, course, par,
numberOfHolesPlayed, isCompleted, grossScore, netScore, toPar, outScore,
inScore, courseHcp, teeName, isInHcp, holes: ScorecardHole[], stat: ScorecardStat`.
**ScorecardHole**: `holeNumber, par, strokeIndex, distance, grossScore, netScore,
putts, greenInRegulation, hcpStrokes, shots: ScorecardShot[]`.
**ScorecardShot**: `shotNumber, club, total, launchLie, finalLie, shotResult,
launchPosition, finalPosition, measurement: ShotMeasurement`.
**ScorecardStat**: `driveAverage, driveMax, driveTotal, driveCount,
highestBallSpeed, fairwayHitFairway/Left/Right, greenInRegulation, numberOfPutts,
averagePuttsPerHoleDecimal, birdies, pars, bogeys, doubleBogeys, …`

**Measurement / ShotMeasurement** (full launch-monitor metric set):
`clubSpeed, attackAngle, clubPath, dynamicLoft, faceAngle, spinLoft, faceToPath,
swingPlane, swingDirection, lowPointDistance, impactOffset, impactHeight,
ballSpeed, smashFactor, launchAngle, launchDirection, spinRate, spinAxis,
curve, maxHeight, carry, total, carrySide, totalSide, landingAngle, hangTime,
side, break, totalBreak, effectiveStimp, …` (~80 fields).

**AllEquipment**: `clubs(clubIds, includeRetired): Club[]`, `balls: Ball[]`,
`retiredClubs`, `retiredBalls`.
**Club**: `id, dbId, brand, clubHead { clubHeadKind, clubHeadType },
displayName, isRetired, findMyDistance: FindMyDistance`.
**FindMyDistance**: `numberOfShots, dispersionCircle: DispersionCircle,
clubStats: ClubStatistic, shots: FindMyDistanceShot[]` — **this is the gapping /
dispersion source**.
**ClubStatistic**: `carry, total, standardDeviationCarry, standardDeviationTotal`.
**DispersionCircle**: `centerX, centerY, minAxis, maxAxis, angle`.

### Enums

- **ActivityKind**: `SESSION, RANGE_PRACTICE, COURSE_PLAY,
  RANGE_FIND_MY_DISTANCE, VIRTUAL_GOLF_PLAY, VIRTUAL_GOLF_PRACTICE,
  PERFORMANCE_PUTTING, PERFORMANCE_CENTER, COMBINE_TEST, SHOT_ANALYSIS,
  MAP_MY_BAG, ON_COURSE, …` (38 values — filter `me.activities(kinds: …)`).
- **ClubEnum**: `DRIVER, WOOD2..9, HYBRID1..9, IRON1..9, PITCHING_WEDGE,
  SAND_WEDGE, LOB_WEDGE, WEDGE50/52/54/56/58/60, PUTTER, UNKNOWN`.
- **BayKind**: `SIMULATOR_BAY, RANGE_BAY`.

## Example queries

**Profile + handicap** (`trackman(action="profile")`):
```graphql
query { me {
  profile { fullName email outdoorHandicap category dexterity }
  hcp { currentHcp currentRecord { hcpNew scoreDifferential createdAt } }
} }
```

**Recent sessions** (`trackman(action="sessions")`):
```graphql
query($skip:Int,$take:Int,$kinds:[ActivityKind!]) {
  me { activities(skip:$skip, take:$take, kinds:$kinds) {
    totalCount
    items {
      id time kind isHidden
      ... on RangePracticeActivity { numberOfStrokes clubs location { name } }
      ... on CoursePlayActivity { grossScore toPar course { displayName } }
    }
  } }
}
```

**Range practice shots** (`trackman(action="session")` for a RANGE_PRACTICE activity):
```graphql
query($id:ID!) { node(id:$id) { ... on RangePracticeActivity {
  time numberOfStrokes
  strokes { club time measurement {
    ballSpeed carry total launchAngle spinAxis curve totalSide
  } }
} } }
```

**Course rounds / scorecards** (`trackman(action="rounds")`):
```graphql
query($take:Int) { me { scorecards(take:$take, completed:true) {
  id startedAt course { displayName } par grossScore toPar
  stat { fairwayHitFairway greenInRegulation numberOfPutts driveAverage }
  holes { holeNumber par grossScore putts greenInRegulation
    shots { shotNumber club total measurement { ballSpeed carry } } }
} } }
```

**Club gapping / dispersion** (`trackman(action="clubs")`):
```graphql
query { me { equipment { clubs(includeRetired:false) {
  displayName clubHead { clubHeadType }
  findMyDistance { numberOfShots
    clubStats { carry total standardDeviationCarry standardDeviationTotal }
    dispersionCircle { minAxis maxAxis angle } }
} } } }
```

## Tool ↔ endpoint reconciliation

> Historical note: this section originally listed one planned tool per
> endpoint (Phase 0, before the server existed). The shipped server folds all
> of these Trackman reads into a single `trackman(action, …)` tool — the
> `action` column below is what each row became.

| `trackman` action | Backing | Notes |
|--------------|---------|-------|
| `auth` (its own tool) | OIDC token capture | Validates/loads `TRACKMAN_TOKEN`; not a real OAuth exchange (confidential client). |
| `profile` | `me.profile` + `me.hcp` | handicap = `hcp.currentHcp` (also `profile.outdoorHandicap`). |
| `sessions` | `me.activities` | Filter by `kinds`, `timeFrom/timeTo`; paged. |
| `session` | `node(id)` / `me.activities` | Use inline fragments per `ActivityKind`. |
| `rounds` | `me.scorecards` | Per-hole + `stat` aggregates. |
| `clubs` | `me.equipment.clubs.findMyDistance` | Carry/total + std-dev + dispersion = gapping. |
| `session` (shot detail) | `RangeStroke.measurement` / `ScorecardShot.measurement` | Full `Measurement` field set — folded into `session` rather than a separate action. |
| `summary` | `me.activitySummary` | Activity counts by kind over a window. |

**Handicap history** (`hcp.playerHistory`) and **activity summary**
(`me.activitySummary`) were the "new tools worth adding" this discovery
surfaced — both now live as `trackman(action="handicap")` and
`trackman(action="summary")`.

**Units** (confirmed against a live account, 2026-06-27): metrics are **metric** —
`ballSpeed`/`clubSpeed` in **m/s** (e.g. 43.3 m/s), `carry`/`total`/distances in
**meters**, `spinRate` in rpm, angles in degrees. The analysis skill must convert
to mph/yards if the user expects imperial.

**Gaps / honest findings**:
- No local OAuth: the MCP depends on a captured Bearer token (see auth strategy).
- "Strokes Gained" is **not** a first-class field; it must be derived in the
  analysis skill from shot/score data, not fetched.
- `trackman(action="session")` currently has inline fragments for
  `RangePracticeActivity` and `CoursePlayActivity` only. Other shot-bearing
  kinds — notably `MapMyBagSessionActivity`, `ShotAnalysisSessionActivity`,
  `RangeFindMyDistanceActivity` — return just the interface fields until
  fragments are added. (Validated: a `MapMyBagSessionActivity` came back without
  strokes for this reason.)

## Live validation (2026-06-27)

`scripts/validate.py` run against a real account returned data for **every**
category: profile, handicap (current index + history), activities, course rounds,
club gapping (carry + std-dev per club), activity summary, and shot-level launch
metrics from a course round. All tool GraphQL queries are confirmed correct
end-to-end. (Specific values omitted — run the validator yourself to see yours.)
