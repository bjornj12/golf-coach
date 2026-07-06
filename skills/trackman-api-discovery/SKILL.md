---
name: trackman-api-discovery
description: Use FIRST, before writing any MCP tool, to reverse-engineer Trackman's golf web portal — capture its login/auth flow and the JSON data endpoints it calls, then catalogue them into docs/trackman-api.md. Trackman has no public golf API, so this discovery is Phase 0 of the project.
---

# Trackman API Discovery (Phase 0)

Trackman publishes **no public golf API**. The portal at
`https://portal.trackmangolf.com` (and the mobile app) talk to private
endpoints. This skill discovers those endpoints by observing the real web app,
then writes them down so the MCP can replicate them.

**Goal:** a filled-in `docs/trackman-api.md` describing the auth flow and every
data endpoint we need, with example request/response shapes (secrets scrubbed).

## Ground rules

- This is the user accessing **their own** account. Use the user's real login,
  driven by them or with their explicit go-ahead.
- **Never paste real tokens, cookies, passwords, or emails into the repo.**
  Record shapes with values redacted (`"token": "<REDACTED>"`).
- Don't hammer endpoints. A few calls to learn the shape is enough.

## Procedure

Use the **claude-in-chrome** browser tools (load them via ToolSearch first) with
the network panel, or have the user open DevTools → Network themselves.

1. **Find the login flow.**
   - Navigate to the Trackman golf portal sign-in page.
   - Watch the Network tab while logging in. Identify: the auth endpoint(s),
     whether it's OAuth/OIDC (Trackman uses an identity server —
     `login.trackmangolf.com` / `id.trackman...`), what token comes back
     (bearer JWT? cookie session?), and how it's attached to later requests
     (`Authorization: Bearer …` header vs cookie).
   - Record: token type, where it lives, refresh mechanism, expiry.

2. **Catalogue the data endpoints.** Click through the portal and record the
   XHR/fetch calls behind each screen we care about:
   - Profile / **handicap** page
   - Activity / sessions list (practice + course rounds)
   - A single practice session detail (shot-by-shot launch data)
   - A course round / scorecard
   - Any "my clubs" / club averages / gapping view
   - Filter by `Fetch/XHR`; ignore analytics, fonts, images.

3. **For each endpoint, record:** method, URL (+ path/query params), required
   headers, a scrubbed example response, and which fields matter (carry, ball
   speed, spin, side, score, handicap, etc.). Note GraphQL vs REST — if it's
   GraphQL (`/graphql`), capture the query/operation names and variables.

4. **Map endpoints → the MCP's `trackman` tool actions** (`profile`, `sessions`,
   `session`, `rounds`, `clubs`). Flag any action that has **no** backing
   endpoint, and any rich endpoint we should add an action for.

5. **Write it all into `docs/trackman-api.md`** using the template already in
   that file. Replace every `TODO`. This document becomes the contract the
   Phase 1 server is built against.

## Done when

- `docs/trackman-api.md` describes the auth flow and at least the endpoints
  behind profile/handicap, sessions list, session detail, and scorecards.
- Every recorded sample is scrubbed of secrets.
- The planned-tool table in `CLAUDE.md` has been reconciled with reality.

If an endpoint can't be found for something we want, say so explicitly in the
doc rather than guessing — that's a real finding the build needs.
