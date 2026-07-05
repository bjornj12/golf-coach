# Golf GameBook API — Discovery Notes

> **Status: PARTIALLY DISCOVERED (topology mapped, 2026-07-05).** Everything below
> was found from **public, unauthenticated** sources only: certificate
> transparency logs (crt.sh), the two public web SPAs' JavaScript bundles, and
> unauthenticated probes with obviously-fake values to read error contracts. **No
> account, credential, or token was used, and no personal-stats endpoint has been
> reached yet.** The personal-stats backend (`core`) is mobile-app-only and its
> routes are not yet known — see "The one remaining step".

## TL;DR

- **The data we want (personal per-course round stats: fairways, GIR, putts,
  averages) lives behind `core.golfgamebook.com`** — the backend the *mobile app*
  talks to. It is a Go service; the JSON API is mounted under `/api/`.
- **There is no personal web portal.** Unlike Trackman (which has a web portal we
  could capture a token from), the individual-golfer product is **mobile-only**.
  The two web portals that exist — `tournament.` and `office.` — are **B2B**
  (tournament organizers / clubs / GGB staff) and do **not** expose a golfer's
  personal round history.
- **No official API or export.** GGB support states plainly there is neither.
- **Consequence:** to authenticate and discover `core`'s endpoints we need **one
  interception of the mobile app's own traffic** (mitmproxy on the user's phone,
  the user's own account). That is the Phase-0 step and it needs the user in the
  loop. Everything up to that point is done.

## Backend topology (confirmed)

| Host | What it is | Auth | Relevant to personal stats? |
|------|------------|------|------------------------------|
| `core.golfgamebook.com` | **Mobile app backend** (Go). JSON API under `/api/`. | email/username + password (in-app) → token | **YES — this is the target.** Routes unknown. |
| `tournament-api.golfgamebook.com` | Tournament Manager backend. Paths `api/1/…`. | `POST api/1/login` (email/password → token) | No — tournament/club/organization data only. |
| `tournament.golfgamebook.com` | Tournament Manager web SPA (React). | posts to tournament-api | No |
| `office-api.golfgamebook.com` | GameBook Office backend. | **AWS Cognito OIDC** | No — office/staff data. |
| `office.golfgamebook.com` | GameBook Office web SPA (React). | Cognito (see below) | No |
| `static.golfgamebook.com` | Static assets (avatars, flags). | none | No |
| `go.golfgamebook.com` | Rebrandly link shortener. | n/a | No |

Other subdomains from crt.sh are environments/infra (`*.dev`, `*.staging`,
`*.qa`, `*.beta`, `*.sandbox`, `vpn`, `email.mailserv*`, `blog`, `shop`,
`careers`, `support`). No player-facing web app among them.

## `core` — the mobile backend (the target)

- Root `GET /` → Go's default `404 page not found` (plaintext, 19 bytes) → it's a
  Go HTTP service.
- `GET /api/` (and any unknown path under it) → structured JSON envelope:
  ```json
  {"success":false,"statusCode":404,"timestamp":<unix>,"data":null,
   "error":{"code":1,"subCode":1,"message":"not found"}}
  ```
  This envelope (`success` / `statusCode` / `timestamp` / `error{code,subCode}`)
  is **distinct** from tournament-api's (`{"status":…,"error":{"errorCode":…}}`),
  confirming `core` is a **separate service/framework** — so the web bundles do
  **not** reveal its routes.
- It does **not** use the `api/1/…` scheme (tried `/api/1/countries`,
  `/api/1/login`, `/api/1/validate-token` → all the "not found" envelope).
- Blind path guessing (`/api/v{1,2,3}/…`, `/api/me`, `/api/rounds`,
  `/api/statistics`, `/api/login`, `/api/session`, …) all returned the not-found
  envelope. **Routes are not guessable; stop guessing and intercept the app.**
- **Auth (from GGB's own KB):** login is **email or username + password**,
  entered in the app. So `core` almost certainly has a credential-login endpoint
  that returns a token the app then sends as a header on data calls. Which of the
  three plausible token models it uses (custom bearer, or AWS Cognito
  `USER_PASSWORD_AUTH`, or something else) is **unknown until intercepted.**

## Tournament Manager API (documented, but NOT the target)

Real, clean, credential-based — recorded here because it's the clearest picture
of GGB's auth style, and tournament players use their normal GameBook accounts.

- Base: `https://tournament-api.golfgamebook.com/`
- Login: `POST api/1/login` (fake-cred probe → `{"status":false,"error":{"code":422,
  …,"message":"missing parameters"}}`, i.e. a plain param-based password login).
- Token check: `GET api/1/login/check/<token>`, `GET api/1/validate-token`.
- Other endpoints seen: `api/1/tournament(s)`, `api/1/organization(s)`,
  `api/1/club/…`, `api/1/clubs/search`, `api/1/game-formats`, `api/1/countries`
  (open, no auth), `api/1/match-play-brackets`, `api/1/reset`,
  `api/1/activate-account`, `api/1/logout`.
- **No personal round/stat endpoints here** — everything is tournament-scoped.

## Office (Cognito — documented, NOT the target)

- Auth: **AWS Cognito**, EU (Ireland) region.
  - Issuer/pool: `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_4mFCGyviQ`
  - Hosted UI: `https://eu-west-14mfcgyviq.auth.eu-west-1.amazoncognito.com`
  - Client id: `kkcihu7oot96b1ob0saoo8ph4`, flow `response_type=code`,
    scope `openid email profile`.
- This is the office/staff console. Not personal golfer stats.
- **Open question worth one check:** does the *mobile app* share this Cognito
  pool? If it does, player login could be a pure-HTTP Cognito
  `InitiateAuth`/`USER_PASSWORD_AUTH` call — replicable from email+password with
  **no phone and no browser**. The interception below will answer this directly
  (look for calls to `cognito-idp.eu-west-1.amazonaws.com`).

## The one remaining step (needs the user + their phone, ~10 min)

Discover `core`'s login + stats routes by watching the app authenticate and load
its Statistics screen once. This is the Phase-0 analog of `trackman-api-discovery`.

1. Install mitmproxy on this machine: `brew install mitmproxy`, run `mitmweb`.
2. On the phone: same Wi-Fi, set the proxy to this machine:8080, install the
   mitmproxy CA cert (`http://mitm.it`) and trust it.
   - Note: GGB may use TLS pinning. If pinned, the app's traffic won't decrypt
     and we'd need Frida/objection on a rooted/jailbroken device or an emulator —
     flag to the user before going down that road.
3. In the app: log out → log in (captures the **login request**: URL, field
   names, and the **token** in the response) → open **Statistics → Played
   Courses** (captures the **stats endpoints** and how the token is carried, e.g.
   `Authorization: Bearer …`).
4. Record into this file (scrub token/email/player-id): the login endpoint +
   payload shape, token type & lifetime, and each stats endpoint + response JSON.
   Then Phase 1 (MCP tools) is the same pattern as Trackman: MCP fetches raw data
   only, skills do the coaching.

**Alternative if pinning blocks mitmproxy:** static-analyze the Android APK
(`apktool` + `jadx`) for the `core` base URL, path constants, and whether auth is
Cognito vs custom. Slower, no device trust needed, but obfuscation may bite.

## What did NOT pan out

- No `app.` / `my.` / `web.` player portal (none resolve).
- `core` routes are not guessable and blind probing is a dead end (and abusive).
- Web SPAs (`tournament`/`office`) only reveal their own B2B backends, not `core`.

---

*Sources: crt.sh CT logs for `golfgamebook.com`; `tournament.golfgamebook.com`
and `office.golfgamebook.com` JS bundles; unauthenticated probes of `core` and
`tournament-api`. GGB "no export/API" per support KB.*
