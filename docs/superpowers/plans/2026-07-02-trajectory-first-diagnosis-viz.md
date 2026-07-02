# Trajectory-First Diagnosis Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Animate the golfer's real measured ball flight (new side-view hero + per-shot top-down tracers), keep the deterministic explanation layer, and replace the flat plan list with a grouped multi-link "Fix it" section (range + home) — per the approved spec `docs/superpowers/specs/2026-07-02-trajectory-first-diagnosis-viz-design.md`.

**Architecture:** All rendering stays in the single self-contained HTML template in `src/trackman_mcp/visualize.py` (pure canvas/JS, zero deps). A shared animation clock (duration scaled by measured `hangTime`) drives all panels in sync. `queries.py` gains the trajectory fields for every session kind. Four skills are rewired away from stick-figure/freehand animation — SKILL.md and PROMPT.md together.

**Tech Stack:** Python 3.12+, FastMCP, inline canvas/JS in one HTML template, pytest, Playwright (headless render check only).

## Global Constraints

- The artifact is **self-contained**: no external `src`/`href`, no network, inline canvas/JS only (`test_build_html_is_self_contained_and_nonempty` enforces).
- **Injection safety**: all data reaches the page via `_json_for_script`; DOM writes via `el()`/`textContent`; every URL through `safeHref` (http/https only).
- **No fabricated numbers**: geometry may estimate a curve's shape, but a *label* renders only when the field was measured.
- **Metric units** everywhere (m, m/s, seconds).
- **Fail loudly**: malformed input → `ValueError` naming the offending entry; never silent skip.
- **SKILL.md and PROMPT.md change together, every time** (Desktop only sees PROMPT.md via `prompts.py`).
- `tests/test_skill_content.py` guards must stay green: drill-library keeps the phrases "no exceptions", "never invent", "video link" and the drill names wall / pump-and-drop / trail-arm / split-hands / step-through; golf-coaching keeps "build_visualization", "verify", "animat", "video link", "never invent", "never give text-only"; golf-practice-at-home keeps "no ball"/"no-ball" and "training_plan".
- Run tests with `uv run pytest` from the repo root.
- The abandoned `worktree-multi-angle-drill-viz` branch is NOT a source: do not port the `drill` key, fragments, or archetypes.

---

### Task 1: Trajectory fields for every session kind in GET_SESSION

**Files:**
- Modify: `src/trackman_mcp/queries.py:74-179` (the `GET_SESSION` string)
- Test: `tests/test_queries.py`

**Interfaces:**
- Consumes: nothing (pure query-string change).
- Produces: `get_session` responses now carry `maxHeight`, `hangTime`, `launchDirection`, `landingAngle` for all seven session kinds + course-round hole shots. Task 4's side view reads these fields from shot dicts.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_queries.py`:

```python
def test_get_session_selects_trajectory_fields_everywhere():
    # The side-view flight reconstruction (visualize.py) needs these fields for
    # every activity kind a session can be — not just RangePracticeActivity.
    # 8 = 7 session kinds + CoursePlay hole shots.
    q = queries.GET_SESSION
    for field in ("maxHeight", "hangTime", "launchDirection", "landingAngle"):
        assert q.count(field) >= 8, f"{field} missing from some GET_SESSION kinds"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_queries.py::test_get_session_selects_trajectory_fields_everywhere -v`
Expected: FAIL — `maxHeight missing from some GET_SESSION kinds` (count is 1).

- [ ] **Step 3: Add the fields to each fragment**

In `GET_SESSION` in `src/trackman_mcp/queries.py`:

(a) `RangeFindMyDistanceActivity` — replace:

```
          ballSpeed carry total carrySide totalSide
          launchAngle launchDirection landingAngle ballSpin spinAxis curve
```

with:

```
          ballSpeed carry total carrySide totalSide
          launchAngle launchDirection landingAngle ballSpin spinAxis curve
          maxHeight hangTime
```

(b) The five identical bay/sim measurement blocks (`MapMyBagSessionActivity`, `ShotAnalysisSessionActivity`, `SimulatorSessionActivity`, `VirtualRangeSessionActivity`, `SessionActivity`) — replace **all five** occurrences of:

```
          clubSpeed attackAngle ballSpeed smashFactor carry total
          launchAngle spinRate spinAxis curve carrySide totalSide landingAngle
```

with:

```
          clubSpeed attackAngle ballSpeed smashFactor carry total
          launchAngle launchDirection spinRate spinAxis curve carrySide totalSide
          landingAngle maxHeight hangTime
```

(c) `CoursePlayActivity` hole shots — replace:

```
              ballSpeed clubSpeed smashFactor carry total
              launchAngle spinRate curve carrySide totalSide landingAngle
```

with:

```
              ballSpeed clubSpeed smashFactor carry total
              launchAngle launchDirection spinRate curve carrySide totalSide
              landingAngle maxHeight hangTime
```

`RangePracticeActivity` already has all four fields — leave it.

All kinds select the same GraphQL `Measurement` type (see `docs/trackman-api.md` lines 124/142 — the superset includes these fields), so the additions are schema-safe. If a `TRACKMAN_TOKEN` is available, `TRACKMAN_TOKEN=... uv run python scripts/validate.py` confirms against the live API; if not, note it for the final task.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_queries.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/queries.py tests/test_queries.py
git commit -m "Select trajectory fields for every session kind in GET_SESSION"
```

---

### Task 2: Fail-loud validation for blocks/links in build_html

**Files:**
- Modify: `src/trackman_mcp/visualize.py:299-318` (`build_html`)
- Test: `tests/test_visualize.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_validate_blocks(data: dict) -> None` (module-level, raises `ValueError`); `build_html` calls it first. Task 3's renderer can then trust `blocks`/`links` shape.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visualize.py` (add `import pytest` to the imports):

```python
def test_unknown_where_is_a_loud_error():
    with pytest.raises(ValueError, match="where.*'gym'.*home, range"):
        build_html({"blocks": [{"name": "x", "where": "gym"}]})


def test_malformed_links_entry_is_a_loud_error():
    # a bare string instead of {label, url} must be rejected, not skipped
    with pytest.raises(ValueError, match=r"blocks\[0\]\.links\[0\]"):
        build_html({"blocks": [{"name": "x", "links": ["https://y"]}]})


def test_links_must_be_a_list():
    with pytest.raises(ValueError, match=r"blocks\[0\]\.links must be a list"):
        build_html({"blocks": [{"name": "x", "links": "https://y"}]})


def test_valid_blocks_with_links_and_legacy_link_pass():
    html = build_html({"blocks": [
        {"name": "a", "where": "home",
         "links": [{"label": "video", "url": "https://example.com/v"}]},
        {"name": "b", "link": "https://example.com/w"},   # legacy single link
    ]})
    assert html.lstrip().lower().startswith("<!doctype html>")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_visualize.py -v -k "where or links"`
Expected: the three error tests FAIL (no ValueError raised).

- [ ] **Step 3: Implement `_validate_blocks`**

In `src/trackman_mcp/visualize.py`, above `build_html`:

```python
_VALID_WHERE = ("home", "range")


def _validate_blocks(data: dict) -> None:
    """Fail loudly on malformed practice blocks (repo convention: no silent skips)."""
    blocks = data.get("blocks")
    if blocks is None:
        return
    if not isinstance(blocks, list):
        raise ValueError("blocks must be a list")
    for i, b in enumerate(blocks):
        if not isinstance(b, dict):
            raise ValueError(f"blocks[{i}] must be an object")
        where = b.get("where", "range")
        if where not in _VALID_WHERE:
            raise ValueError(
                f"blocks[{i}].where is {where!r}; expected one of: home, range")
        links = b.get("links")
        if links is None:
            continue
        if not isinstance(links, list):
            raise ValueError(f"blocks[{i}].links must be a list of {{label, url}}")
        for j, link in enumerate(links):
            if not (isinstance(link, dict) and isinstance(link.get("url"), str)
                    and isinstance(link.get("label", ""), str)):
                raise ValueError(
                    f"blocks[{i}].links[{j}] must be {{label, url}} with a string url")
```

And make the first line of `build_html`'s body:

```python
    _validate_blocks(data)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: all PASS (existing 6 + new 4).

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/visualize.py tests/test_visualize.py
git commit -m "Validate blocks/links input to build_html, failing loudly"
```

---

### Task 3: Grouped multi-link "Fix it" section

**Files:**
- Modify: `src/trackman_mcp/visualize.py` (the `_TEMPLATE` string: CSS, HTML, `renderBars`, new `renderBlocks`, bootstrap line)
- Test: `tests/test_visualize.py`

**Interfaces:**
- Consumes: validated `blocks` shape from Task 2.
- Produces: `renderBlocks()` JS function and a `#fixit` container; `blocks[].where` (`"range"`/`"home"`, default `"range"`) and `blocks[].links[]` (`{label, url}`) render as two groups; legacy `blocks[].link` still renders as a single `video ↗` link.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visualize.py`:

```python
def test_fixit_section_replaces_flat_plan_list():
    html = build_html({"title": "ok"})
    assert 'id="fixit"' in html
    assert 'id="plan"' not in html          # the old flat list is gone
    assert "renderBlocks" in html
    # groups render only when they have items (no empty headers)
    assert "if(!items.length) return" in html


def test_hostile_link_label_and_url_cannot_break_out():
    html = build_html({
        "title": "ok",
        "blocks": [{"name": "Drill", "where": "home",
                    "links": [{"label": "</script><script>alert(1)</script>",
                               "url": "javascript:alert(1)"}]}],
    })
    # embedded JSON stays breakout-safe; only the template's own script closes
    assert html.count("</script>") == 1
    assert "<script>alert(1)" not in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_visualize.py -v -k "fixit or hostile"`
Expected: both FAIL (`id="fixit"` absent).

- [ ] **Step 3: Edit the template**

All edits inside `_TEMPLATE` in `src/trackman_mcp/visualize.py`.

(a) CSS — replace:

```
  .plan{margin-top:18px} .plan li{margin:6px 0;color:#cfe0f5}
  .plan a{color:var(--acc)} .full{grid-column:1/-1}
```

with:

```
  .fixhead{margin:10px 0 4px;font-size:13px;color:#bcd2f0;letter-spacing:.3px;text-transform:uppercase}
  .fixlist{margin:0 0 6px;padding-left:20px} .fixlist li{margin:6px 0;color:#cfe0f5}
  .fixlist a{color:var(--acc)} .full{grid-column:1/-1}
```

(b) HTML — replace the targets card:

```
    <div class="card full"><h2>Progress vs targets</h2>
      <div class="bars" id="bars"></div>
      <div class="plan"><ul id="plan"></ul></div>
      <button onclick="replay()">↻ Replay animation</button>
    </div>
```

with:

```
    <div class="card full"><h2>Progress vs targets</h2>
      <div class="bars" id="bars"></div>
      <button onclick="replay()">↻ Replay animation</button>
    </div>
    <div class="card full"><h2>Fix it — drills</h2>
      <div id="fixit"></div>
    </div>
```

(c) JS — in `renderBars()`, delete the trailing plan loop:

```
  const plan=$('#plan');plan.textContent="";
  (DATA.blocks||[]).forEach(b=>{const li=document.createElement('li');
    li.appendChild(el('b',null,b.name||''));
    li.appendChild(document.createTextNode(' — '+(b.detail||b.goal||'')+' '));
    const href=safeHref(b.link);
    if(href){const a=el('a',null,'video ↗'); a.href=href; a.target='_blank';
      a.rel='noopener noreferrer'; li.appendChild(a);}
    plan.appendChild(li);});
```

and add a new function after `renderBars()`:

```
// ---------- fix it: drills grouped by where, multiple links each ----------
function renderBlocks(){
  const host=$('#fixit'); host.textContent="";
  [["range","At the range"],["home","At home — no ball"]].forEach(([key,label])=>{
    const items=(DATA.blocks||[]).filter(b=>(b.where||"range")===key);
    if(!items.length) return;
    host.appendChild(el('h3','fixhead',label));
    const ul=el('ul','fixlist');
    items.forEach(b=>{const li=el('li');
      li.appendChild(el('b',null,b.name||''));
      li.appendChild(document.createTextNode(' — '+(b.detail||b.goal||'')+' '));
      const links=Array.isArray(b.links)?b.links
        :(b.link?[{label:'video',url:b.link}]:[]);
      let shown=0;
      links.forEach(L=>{const href=safeHref(L&&L.url); if(!href) return;
        if(shown++) li.appendChild(document.createTextNode(' · '));
        const a=el('a',null,(L.label||'video')+' ↗');
        a.href=href; a.target='_blank'; a.rel='noopener noreferrer';
        li.appendChild(a);});
      ul.appendChild(li);});
    host.appendChild(ul);});
}
```

(d) Bootstrap — replace:

```
renderBars();drawFlight();drawSwing();
```

with:

```
renderBars();renderBlocks();drawFlight();drawSwing();
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/visualize.py tests/test_visualize.py
git commit -m "Group Fix-it drills by range/home with multiple safe links"
```

---

### Task 4: Side-view flight hero + shared hangTime-scaled clock

**Files:**
- Modify: `src/trackman_mcp/visualize.py` (`_TEMPLATE`: hero card HTML, side-view JS, clock refactor of `drawFlight`/`drawSwing`/`replay`)
- Test: `tests/test_visualize.py`

**Interfaces:**
- Consumes: shot fields from Task 1 (`launchAngle`, `maxHeight`, `landingAngle`, `hangTime`, `carry`, `total`).
- Produces: JS `sideCurve(shot)` → `{carry,total,xa,apex,apexMeasured,tl,td}|null`, `sidePoint(flight,t)` → `{x,y}` in meters, `drawSide(t)`, `sideCaption()`, `meanOf(field,positiveOnly)`, shared clock (`DUR`, `tick`, `replay()`), and `drawFlight(t)`/`drawSwing(t)` now take the clock's `t` (0..1) instead of self-animating. Task 5 rewrites `drawFlight(t)`'s body but keeps this signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visualize.py`:

```python
def test_side_view_hero_present_with_honest_guards():
    html = build_html({"shots": [{"carry": 200, "launchAngle": 12,
                                  "maxHeight": 25, "landingAngle": 35,
                                  "hangTime": 5.5}]})
    assert 'id="side"' in html and 'id="sideCard"' in html
    # reconstruction exists and estimates geometry only when unmeasured
    assert "sideCurve" in html and "apexMeasured" in html
    # the apex label renders only behind the measured guard
    assert "repSide.apexMeasured" in html
    # panel hides itself when no shot has usable height data
    assert "card.style.display='none'" in html
    # the embedded page JSON carries the shots with vertical fields intact
    assert '"maxHeight": 25' in html and '"hangTime": 5.5' in html


def test_animation_duration_scales_with_hangtime():
    html = build_html({"title": "ok"})
    # duration = 600ms x clamped hang seconds; default 4 when unmeasured
    assert "600*Math.min(7,Math.max(2.5" in html
    # one clock drives all panels in sync
    assert "drawSide(clockT);drawFlight(clockT);drawSwing(clockT)" in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_visualize.py -v -k "side_view or hangtime"`
Expected: both FAIL.

- [ ] **Step 3: Add the hero card HTML**

In `_TEMPLATE`, insert between `<div class="diag">__DIAGNOSIS__</div>` and `<div class="grid">`:

```
  <div class="card hero" id="sideCard"><h2>Ball flight — side view</h2>
    <canvas id="side" width="1040" height="330"></canvas>
    <div class="legend">
      <span><i class="dot" style="background:#4ea1ff"></i>average flight</span>
      <span><i class="dot" style="background:rgba(78,161,255,.4)"></i>each shot</span>
      <span><i class="dot" style="background:#ffd166"></i>roll after carry</span>
    </div>
    <div class="why" id="sideWhy"></div>
  </div>
```

And add to the CSS (next to the `.card` rule):

```
  .hero{margin:0 0 18px}
```

- [ ] **Step 4: Add the side-view JS**

In `_TEMPLATE`, insert directly after the `const A={...}` aggregate block (before `// ---------- ball flight ----------`):

```
// ---------- side view: the real measured flight, reconstructed ----------
// Arc passes EXACTLY through launch (0,0), apex (xa, apex), landing (carry, 0);
// end tangents match launchAngle / landingAngle. Geometry may estimate an
// unmeasured apex for shape — but it is never labeled (apexMeasured guards).
const D2R=Math.PI/180;
function sideCurve(s){
  const carry=(typeof s.carry==='number'&&s.carry>0)?s.carry:
              ((typeof s.total==='number'&&s.total>0)?s.total:null);
  const la=(typeof s.launchAngle==='number'&&s.launchAngle>0)?s.launchAngle:null;
  if(carry===null||la===null) return null;
  const da=(typeof s.landingAngle==='number'&&s.landingAngle>0)?s.landingAngle:la;
  const tl=Math.tan(la*D2R), td=Math.tan(da*D2R);
  let xa=carry*td/(tl+td);                       // where the tangents cross
  xa=Math.min(0.75*carry,Math.max(0.4*carry,xa)); // real flights peak past mid
  const apexMeasured=(typeof s.maxHeight==='number'&&s.maxHeight>0);
  const apex=apexMeasured?s.maxHeight:xa*tl*0.5;  // estimate: geometry only
  const total=(typeof s.total==='number'&&s.total>carry)?s.total:null;
  return {carry,total,xa,apex,apexMeasured,tl,td};
}
function cubicPt(p0,c1,c2,p1,u){const v=1-u;return{
  x:v*v*v*p0.x+3*v*v*u*c1.x+3*v*u*u*c2.x+u*u*u*p1.x,
  y:v*v*v*p0.y+3*v*v*u*c1.y+3*v*u*u*c2.y+u*u*u*p1.y};}
function sidePoint(f,t){
  const frac=f.xa/f.carry;
  if(t<=frac){const u=frac?t/frac:0;
    return cubicPt({x:0,y:0},{x:0.4*f.xa,y:0.4*f.xa*f.tl},
                   {x:0.65*f.xa,y:f.apex},{x:f.xa,y:f.apex},u);}
  const w2=f.carry-f.xa, u=(t-frac)/(1-frac);
  return cubicPt({x:f.xa,y:f.apex},{x:f.xa+0.35*w2,y:f.apex},
                 {x:f.carry-0.4*w2,y:0.4*w2*f.td},{x:f.carry,y:0},u);
}
const sideFlights=shots.map(sideCurve).filter(Boolean);
function meanOf(k,pos){const vs=shots.map(s=>s[k])
  .filter(v=>typeof v==='number'&&(!pos||v>0));
  return vs.length?vs.reduce((a,b)=>a+b,0)/vs.length:null;}
const repSide=sideCurve({carry:meanOf('carry',true)??meanOf('total',true),
  total:meanOf('total',true),launchAngle:meanOf('launchAngle',true),
  maxHeight:meanOf('maxHeight',true),landingAngle:meanOf('landingAngle',true)});
function drawSide(t){
  const card=$('#sideCard');
  if(!sideFlights.length){card.style.display='none';return;}
  const c=$('#side'); const {ctx,w,h}=fit(c); ctx.clearRect(0,0,w,h);
  const maxX=Math.max(...sideFlights.map(f=>f.total||f.carry),1)*1.05;
  const maxY=Math.max(...sideFlights.map(f=>f.apex),1)*1.35;
  const padL=38,padR=14,padT=14,gY=h-26;
  const px=x=>padL+x/maxX*(w-padL-padR);
  const py=y=>gY-y/maxY*(gY-padT);
  ctx.font="11px sans-serif";
  const stepX=Math.ceil(maxX/6/10)*10;
  for(let d=0;d<=maxX;d+=stepX){ctx.strokeStyle="#16213a";ctx.beginPath();
    ctx.moveTo(px(d),gY);ctx.lineTo(px(d),padT);ctx.stroke();
    ctx.fillStyle="#5b6a85";ctx.fillText(d+"m",px(d)+2,gY+14);}
  const stepY=Math.max(5,Math.ceil(maxY/4/5)*5);
  for(let y=stepY;y<=maxY;y+=stepY){ctx.strokeStyle="#141f36";ctx.beginPath();
    ctx.moveTo(padL,py(y));ctx.lineTo(w-padR,py(y));ctx.stroke();
    ctx.fillStyle="#5b6a85";ctx.fillText(y+"m",4,py(y)+4);}
  ctx.strokeStyle="#3a4a66";ctx.beginPath();
  ctx.moveTo(padL,gY);ctx.lineTo(w-padR,gY);ctx.stroke();
  sideFlights.forEach(f=>{ctx.strokeStyle="rgba(78,161,255,.22)";ctx.lineWidth=1.5;
    ctx.beginPath();for(let u=0;u<=1.001;u+=0.02){const p=sidePoint(f,u);
      u===0?ctx.moveTo(px(p.x),py(p.y)):ctx.lineTo(px(p.x),py(p.y));}ctx.stroke();
    if(f.total){ctx.setLineDash([3,4]);ctx.strokeStyle="rgba(255,209,102,.5)";
      ctx.beginPath();ctx.moveTo(px(f.carry),gY);ctx.lineTo(px(f.total),gY);
      ctx.stroke();ctx.setLineDash([]);}});
  if(!repSide) return;
  ctx.strokeStyle="#4ea1ff";ctx.lineWidth=3;ctx.beginPath();
  for(let u=0;u<=t;u+=0.02){const p=sidePoint(repSide,u);
    u===0?ctx.moveTo(px(p.x),py(p.y)):ctx.lineTo(px(p.x),py(p.y));}
  ctx.stroke();
  const b=sidePoint(repSide,t);
  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(px(b.x),py(b.y),5,0,7);ctx.fill();
  if(repSide.apexMeasured&&t>=0.5){ctx.fillStyle="#ffd166";
    ctx.fillText(repSide.apex.toFixed(0)+" m",px(repSide.xa)+4,py(repSide.apex)-6);}
}
function sideCaption(){
  const cap=$('#sideWhy'); if(!sideFlights.length){cap.textContent="";return;}
  const parts=[];
  const la=meanOf('launchAngle',true), mh=meanOf('maxHeight',true),
        da=meanOf('landingAngle',true);
  if(la!=null)parts.push(`launches at ${la.toFixed(1)}°`);
  if(mh!=null)parts.push(`peaks at ${mh.toFixed(0)} m`);
  if(da!=null)parts.push(`lands at ${da.toFixed(0)}°`);
  if(hangMean!=null)parts.push(`${hangMean.toFixed(1)} s in the air`);
  cap.textContent=parts.length?`Average flight ${parts.join(' · ')}.`:"";
}
// ---------- shared flight clock (all panels animate in sync) ----------
const hangVals=shots.map(s=>s.hangTime).filter(v=>typeof v==='number'&&v>0);
const hangMean=hangVals.length?hangVals.reduce((a,b)=>a+b,0)/hangVals.length:null;
const DUR=600*Math.min(7,Math.max(2.5,hangMean==null?4:hangMean)); // ms
let t0=null,clockT=0,rafId=null;
function tick(now){ if(t0===null)t0=now;
  clockT=Math.min(1,(now-t0)/DUR);
  drawSide(clockT);drawFlight(clockT);drawSwing(clockT);
  if(clockT<1)rafId=requestAnimationFrame(tick); }
```

Note `hangMean` is referenced by `sideCaption` but only called at bootstrap — `const` hoisting across the same script block is fine because `sideCaption()`/`drawSide()` run after the whole block evaluates.

- [ ] **Step 5: Refactor drawFlight/drawSwing/replay to the shared clock**

Still in `_TEMPLATE`:

(a) `drawFlight`: change signature `function drawFlight(){` → `function drawFlight(t){`; delete the line `let flightT=0, raf1;` above it; inside, replace the two uses of `flightT` with `t`:

```
  ctx.strokeStyle="#4ea1ff";ctx.lineWidth=3;ctx.beginPath();
  for(let u=0;u<=t;u+=0.02){const p=bez(p0,ctrl,end,u);u==0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y);}
  ctx.stroke();
  const b=bez(p0,ctrl,end,t);
```

and delete its self-scheduling last line `if(flightT<1){flightT+=0.012;raf1=requestAnimationFrame(drawFlight);}`.

(b) `drawSwing`: change signature `function drawSwing(){` → `function drawSwing(t){`; delete the line `let swingT=0, raf2;` above it. Replace the clubhead block:

```
  // animated clubhead travelling up the actual path
  const a=ang(path)-Math.PI/2;
  const t=(swingT*2-1); // -1..1
  const hx=cx+Math.cos(a)*L*t, hy=cy+Math.sin(a)*L*t;
  ctx.fillStyle="#ff9aa2";ctx.beginPath();ctx.arc(hx,hy,6,0,7);ctx.fill();
  // face line at impact (rotate by faceAngle)
  if(swingT>0.5){
```

with (local `tt` avoids shadowing the clock's `t`):

```
  // animated clubhead travelling up the actual path
  const a=ang(path)-Math.PI/2;
  const tt=(t*2-1); // -1..1
  const hx=cx+Math.cos(a)*L*tt, hy=cy+Math.sin(a)*L*tt;
  ctx.fillStyle="#ff9aa2";ctx.beginPath();ctx.arc(hx,hy,6,0,7);ctx.fill();
  // face line at impact (rotate by faceAngle)
  if(t>0.5){
```

then replace the degree-label guard `if(swingT>0.5){ctx.fillStyle="#ffd166";` with `if(t>0.5){ctx.fillStyle="#ffd166";`, and delete the trailing self-scheduler `if(swingT<1){swingT+=0.012;raf2=requestAnimationFrame(drawSwing);}`.

(c) Replace the old replay/bootstrap:

```
function replay(){cancelAnimationFrame(raf1);cancelAnimationFrame(raf2);
  flightT=0;swingT=0;drawFlight();drawSwing();}
renderBars();renderBlocks();drawFlight();drawSwing();
window.addEventListener('resize',()=>{drawFlight();drawSwing();});
```

with:

```
function replay(){ if(rafId)cancelAnimationFrame(rafId); t0=null;
  rafId=requestAnimationFrame(tick); }
renderBars();renderBlocks();sideCaption();replay();
window.addEventListener('resize',()=>{drawSide(clockT);drawFlight(clockT);drawSwing(clockT);});
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: all PASS (the handedness source-assertions in `test_swing_path_not_mirrored_for_right_handers` must still hold — do not touch the `ang()` helper).

- [ ] **Step 7: Commit**

```bash
git add src/trackman_mcp/visualize.py tests/test_visualize.py
git commit -m "Add side-view flight hero driven by a shared hangTime-scaled clock"
```

---

### Task 5: Per-shot tracers in the top-down panel

**Files:**
- Modify: `src/trackman_mcp/visualize.py` (`_TEMPLATE`: `drawFlight(t)` body)
- Test: `tests/test_visualize.py`

**Interfaces:**
- Consumes: `drawFlight(t)` signature and shared clock from Task 4.
- Produces: JS `shotCurve(s)` → `{p0,ctrl,end}` (pixel-space bezier per shot); every shot renders as a faint curved tracer + landing dot; the representative (mean) shot stays the bright animated one.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_visualize.py`:

```python
def test_topdown_draws_every_shot_as_its_own_tracer():
    html = build_html({"shots": [{"carry": 150, "launchDirection": -2,
                                  "totalSide": 10},
                                 {"carry": 160, "launchDirection": 1,
                                  "totalSide": -5}]})
    assert "shotCurve" in html
    # per-shot faint tracer color distinct from the bright animated mean
    assert "rgba(78,161,255,.22)" in html
    # tracers go through the handedness-aware sx() mapping (regression guard)
    assert "(RH? v: -v)" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_visualize.py::test_topdown_draws_every_shot_as_its_own_tracer -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite the drawing section of `drawFlight(t)`**

In `_TEMPLATE`, inside `drawFlight(t)`, replace everything from the `// landing spots` comment through the tee-marker lines:

```
  // landing spots
  shots.forEach(s=>{const px=sx(s.totalSide||0),py=sy(s.carry||s.total||0);
    ctx.fillStyle="rgba(255,209,102,.55)";ctx.beginPath();ctx.arc(px,py,3.5,0,7);ctx.fill();});
  // representative path (animated): bezier from tee to avg landing
  const p0={x:sx(0),y:sy(0)};
  const end={x:sx(A.side),y:sy(A.carry)};
  const launchDx=Math.tan(A.launch*Math.PI/180)*(A.carry*0.55);
  const ctrl={x:sx(launchDx),y:sy(A.carry*0.5)};   // sx() already handles handedness
  ctx.strokeStyle="#28406a";ctx.lineWidth=2;ctx.beginPath();
  for(let t=0;t<=1;t+=0.02){const p=bez(p0,ctrl,end,t); t==0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y);}
  ctx.stroke();
```

with:

```
  // every shot: its own faint curved tracer + landing spot
  const shotCurve=s=>{const carry=(typeof s.carry==='number'&&s.carry>0)?s.carry:(s.total||0);
    const side=(typeof s.totalSide==='number')?s.totalSide:0;
    const launch=(typeof s.launchDirection==='number')?s.launchDirection:0;
    return {p0:{x:sx(0),y:sy(0)},
            ctrl:{x:sx(Math.tan(launch*Math.PI/180)*(carry*0.55)),y:sy(carry*0.5)},
            end:{x:sx(side),y:sy(carry)}};};   // sx() already handles handedness
  shots.forEach(s=>{const q=shotCurve(s);
    ctx.strokeStyle="rgba(78,161,255,.22)";ctx.lineWidth=1.5;ctx.beginPath();
    for(let u=0;u<=1.001;u+=0.02){const p=bez(q.p0,q.ctrl,q.end,u);
      u===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y);}ctx.stroke();
    ctx.fillStyle="rgba(255,209,102,.55)";ctx.beginPath();
    ctx.arc(q.end.x,q.end.y,3.5,0,7);ctx.fill();});
  // representative shot (field means): the bright animated tracer
  const {p0,ctrl,end}=shotCurve({carry:A.carry,totalSide:A.side,launchDirection:A.launch});
```

(The animated-trail lines that follow — `ctx.strokeStyle="#4ea1ff"...` through the tee marker — already use `p0`/`ctrl`/`end` and the clock `t` from Task 4; they stay as they are.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/visualize.py tests/test_visualize.py
git commit -m "Draw every shot as its own curved tracer in the top-down panel"
```

---

### Task 6: Demo data, docstrings, and the headless render gate

**Files:**
- Modify: `src/trackman_mcp/visualize.py` (module docstring `DATA SCHEMA`, `_DEMO`)
- Modify: `src/trackman_mcp/server.py:514-529` (`build_visualization` docstring)
- Modify: `scripts/check-visualization.py:36` (animation wait)
- Test: existing `tests/test_visualize.py::test_demo_data_renders` + headless render

**Interfaces:**
- Consumes: everything from Tasks 2–5.
- Produces: `_DEMO` exercising every new field; accurate docs for skill/tool consumers.

- [ ] **Step 1: Update the module docstring schema**

In `src/trackman_mcp/visualize.py`, replace the docstring's schema block:

```
{
  "title": str, "subtitle": str, "diagnosis": str, "handedness": "RH"|"LH",
  "shots": [{"launchDirection": deg, "carry": m, "totalSide": m,
             "curve": m, "club": str}],            # one or many
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label": str, "value": num, "target": str,
               "met": bool|None, "low": num, "high": num}],
  "blocks": [{"name": str, "detail": str, "goal": str, "link": str}]
}
```

with:

```
{
  "title": str, "subtitle": str, "diagnosis": str, "handedness": "RH"|"LH",
  "shots": [{"launchDirection": deg, "launchAngle": deg, "carry": m,
             "total": m, "totalSide": m, "curve": m, "maxHeight": m,
             "landingAngle": deg, "hangTime": s, "club": str}],  # one or many
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label": str, "value": num, "target": str,
               "met": bool|None, "low": num, "high": num}],
  "blocks": [{"name": str, "detail": str, "goal": str,
              "where": "range"|"home",             # default "range"
              "links": [{"label": str, "url": str}],  # 1..n vetted links
              "link": str}]                        # legacy single link
}
```

Also update the rendering summary at the top of the docstring: replace the three-item list with

```
  1. Flight side view — the real measured trajectory (launch/apex/landing),
     every shot faint + the average animated, roll after carry.
  2. Ball-flight top-down — per-shot curved tracers + the average animated.
  3. Swing path — animated clubhead on the actual path vs ideal, with the face
     angle, annotating *why* the ball curves.
  4. Target progress + Fix-it drills grouped range/home with multiple links.
```

- [ ] **Step 2: Update `_DEMO`**

Replace `_DEMO`'s `shots` and `blocks` entries:

```python
    "shots": [
        {"launchDirection": -2, "launchAngle": 11.8, "carry": 200, "total": 226,
         "totalSide": 25, "curve": 14, "maxHeight": 24, "landingAngle": 36,
         "hangTime": 5.6},
        {"launchDirection": -3, "launchAngle": 12.6, "carry": 205, "total": 228,
         "totalSide": 20, "curve": 11, "maxHeight": 27, "landingAngle": 38,
         "hangTime": 5.9},
        {"launchDirection": -1, "launchAngle": 10.9, "carry": 195, "total": 221,
         "totalSide": 30, "curve": 18, "maxHeight": 22, "landingAngle": 34,
         "hangTime": 5.4},
    ],
```

```python
    "blocks": [
        {"name": "Headcover drill", "where": "range",
         "detail": "Headcover outside the ball; swing inside it.",
         "links": [
             {"label": "video", "url": "https://hackmotion.com/headcover-drill/"},
             {"label": "more drills",
              "url": "https://www.youtube.com/results?search_query=headcover+slice+drill"},
         ]},
        {"name": "Gate aimed right", "where": "range",
         "detail": "Sticks pointing right of target; exit to right field."},
        {"name": "Wall drill", "where": "home",
         "detail": "Wall a clubhead off the trail shoulder; slow swings that miss it."},
    ],
```

(The YouTube link is a search URL — honest by construction; never invent a content URL, even in demo data.)

- [ ] **Step 3: Update the tool docstring**

In `src/trackman_mcp/server.py`, replace the `data` shape paragraph of `build_visualization`'s docstring with:

```python
    `data` shape (all optional; the viz adapts): {title, subtitle, diagnosis,
    handedness "RH"|"LH", shots:[{launchDirection,launchAngle,carry,total,
    totalSide,curve,maxHeight,landingAngle,hangTime}],
    swing:{clubPath,faceAngle,faceToPath}, targets:[{label,value,target,low,
    high,met}], blocks:[{name,detail,goal,where "range"|"home",
    links:[{label,url}]}]}. Renders the measured flight (side view + top-down,
    animated) and drills grouped range/home. See the trackman-visualizer prompt.
```

- [ ] **Step 4: Bump the render-check wait**

In `scripts/check-visualization.py`, replace:

```python
        await page.wait_for_timeout(2500)  # let the animations run
```

with:

```python
        await page.wait_for_timeout(4500)  # hangTime-scaled animations: up to 4.2s
```

- [ ] **Step 5: Run the suite and the headless gate**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: all PASS (including `test_demo_data_renders`).

Run: `uv run python scripts/check-visualization.py --demo /tmp/viz-check.png`
Expected: `RENDER OK — no console errors or page errors.` and canvases with non-zero dims. Eyeball the screenshot: hero side-view arc with apex label, faint per-shot arcs in both views, Fix-it section with "At the range" and "At home — no ball" groups.

- [ ] **Step 6: Commit**

```bash
git add src/trackman_mcp/visualize.py src/trackman_mcp/server.py scripts/check-visualization.py
git commit -m "Update demo, docstrings, and render-check for the trajectory page"
```

---

### Task 7: Rewire trackman-visualizer (SKILL.md + PROMPT.md)

**Files:**
- Modify: `skills/trackman-visualizer/SKILL.md` (full rewrite below)
- Modify: `skills/trackman-visualizer/PROMPT.md` (full rewrite below)
- Test: `uv run pytest tests/test_prompts.py tests/test_skill_content.py -v`

**Interfaces:**
- Consumes: the tool schema from Task 6.
- Produces: skill text other skills reference ("see `trackman-visualizer`") — keep the file names and skill name unchanged.

- [ ] **Step 1: Replace `skills/trackman-visualizer/SKILL.md` wholesale with:**

````markdown
---
name: trackman-visualizer
description: Use when the user wants to SEE a golf diagnosis — animate their real measured ball flight (side view + top-down), show why it curves, and link the drills that fix it. Turns golf-coaching output + real shot metrics into a self-contained animated HTML artifact. Triggers on "visualize", "show me the curve", "show my ball flight", "draw my slice", or after a coaching diagnosis.
---

# Trackman Visualizer

Turn a coaching diagnosis into a **self-contained animated HTML artifact** that
animates the golfer's **real measured flight**: a side-view height profile
(launch → apex → landing → roll), a top-down shape view with every shot's
tracer, the swing path that explains *why* it curves, progress vs targets, and
a **Fix it** section linking drills for both the range and home. Uses real shot
data — no invented shapes, no freehand diagrams.

## When to use

After `golf-coaching` produces a diagnosis (or when the user asks to "see" /
"draw" / "animate" their slice, flight, dispersion, or progress). It's a
presentation layer on top of the coach — it adds no new diagnosis.

**Be proactive.** Don't wait to be asked — build this page whenever you
diagnose a fault, show a shot pattern, or hand over drills. One page carries
the whole story: what the ball is doing, why, and the exercises that fix it.

## Inputs to gather

Reuse what the coach already pulled, or fetch via the MCP:

1. **Shots** — per-shot measurements for the club under discussion, from
   `get_session`: `launchDirection`, `launchAngle`, `carry`, `total`,
   `totalSide`, `curve`, `maxHeight`, `landingAngle`, `hangTime`. Pass every
   shot (that's what makes the dispersion visible); the page animates the
   average and draws the rest faint. Missing fields are fine — the page only
   labels what was measured.
2. **Swing** — `clubPath`, `faceAngle`, `faceToPath` (mean over those shots),
   where the session kind captures them.
3. **Targets** — from the saved plan (`training_plan(action="next")` /
   `training_plan(action="list")`) and/or `training_plan(action="verify")`:
   each as `{label, value, target, low, high, met}`.
4. **Blocks** — the prescribed drills, each tagged `where: "range"` or
   `where: "home"`, each with 1–3 **verified** links
   (`links: [{label, url}]`) from `drill-library` or live search. Never
   invent URLs.

Also note **handedness** (`profile.dexterity`) — it sets which way "right" is.

## Build the artifact

Assemble the data dict (schema below) and render it. Two ways:

- **MCP tool (preferred):** call `build_visualization(data)` → returns `{html}`.
- **Direct:** `uv run python scripts/visualize.py <data.json> <out.html>` or
  `from trackman_mcp.visualize import build_html`.

```
{
  "title": "...", "subtitle": "...", "diagnosis": "<one line>",
  "handedness": "RH" | "LH",
  "shots": [{"launchDirection": deg, "launchAngle": deg, "carry": m,
             "total": m, "totalSide": m, "curve": m, "maxHeight": m,
             "landingAngle": deg, "hangTime": s}],
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label","value","target","low","high","met"}],
  "blocks": [{"name","detail","goal","where":"range"|"home",
              "links":[{"label","url"}]}]
}
```

### Present per environment

- **Claude Desktop / claude.ai (artifacts):** emit the returned `html` as a
  **`text/html` artifact** — fully self-contained, renders in the sandbox.
- **Claude Code (terminal):** write the html OUTSIDE the repo (it contains the
  user's data), e.g. `~/.trackman-mcp/viz/<name>.html`, and offer to `open` it.
  Optionally `scripts/check-visualization.py <file>` headless-renders it for a
  sanity check.

## Present it

- Briefly narrate what the visual shows (e.g. "side view: you launch at 9° and
  peak at 18 m — low for driver; top-down: every shot bends right").
- Point at the Fix it section: range drills for the next session, home drills
  for today.

## What it renders

- **Flight — side view** (hero): every shot's measured arc faint, the average
  animated with the ball, apex label (only when `maxHeight` was measured),
  dotted roll after carry, launch/peak/landing/hang caption.
- **Ball flight — top-down**: per-shot curved tracers + landing spots, the
  average animated, target line, plain-language caption.
- **Swing path**: animated clubhead along the actual path (red) vs ideal
  (green), face at impact (yellow), caption tying path + face-to-path to curve.
- **Targets**: bars with the good zone shaded, met/not-yet pills, replay button.
- **Fix it — drills**: "At the range" and "At home — no ball" groups, each
  drill with its links.

Keep it honest: only plot metrics that exist in the data. If a field is
missing, the viz adapts (panel hides, label drops) rather than faking it.
````

- [ ] **Step 2: Replace `skills/trackman-visualizer/PROMPT.md` wholesale with:**

````markdown
# Trackman Visualizer

Turn a coaching diagnosis into a **self-contained animated HTML artifact** that
animates the golfer's **real measured flight**: side-view height profile
(launch → apex → landing → roll), top-down shape with every shot's tracer, the
swing path explaining *why* it curves, progress vs targets, and a **Fix it**
section linking drills for range and home. Real shot data only — never invent
shapes or URLs. This is a presentation layer; it adds no new diagnosis.

**Lead with it — don't wait to be asked.** Any time you diagnose a fault, show
a shot pattern, or prescribe drills, build this page. One artifact carries the
whole story: what the ball is actually doing, why, and the exercises that fix
it.

## Gather the inputs (reuse what the coach already pulled, or fetch via the MCP)

1. **Shots** — per-shot measurements for the club under discussion, from
   `get_session`: `launchDirection`, `launchAngle`, `carry`, `total`,
   `totalSide`, `curve`, `maxHeight`, `landingAngle`, `hangTime`. Pass every
   shot — the page animates the average and draws the rest faint. Missing
   fields are fine; the page only labels what was measured.
2. **Swing** — `clubPath`, `faceAngle`, `faceToPath` (mean over those shots),
   where the session kind captures them.
3. **Targets** — from the saved plan (`training_plan(action="next")` /
   `training_plan(action="list")`) and/or
   `training_plan(action="verify", plan_id=<id>)`: each as
   `{label, value, target, low, high, met}`.
4. **Blocks** — the prescribed drills, each tagged `where: "range"` or
   `where: "home"`, each with 1–3 **verified** links
   (`links: [{label, url}]`) from the `drill-library` prompt or live search.
5. **Handedness** — from `get_profile` (`profile.dexterity`).

## Build it

Assemble the data dict and call `build_visualization(data)` → returns `{html}`,
one standalone document (inline canvas/JS, no network).

```
{
  "title": "...", "subtitle": "...", "diagnosis": "<one line>",
  "handedness": "RH" | "LH",
  "shots": [{"launchDirection": deg, "launchAngle": deg, "carry": m,
             "total": m, "totalSide": m, "curve": m, "maxHeight": m,
             "landingAngle": deg, "hangTime": s}],
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label","value","target","low","high","met"}],
  "blocks": [{"name","detail","goal","where":"range"|"home",
              "links":[{"label","url"}]}]
}
```

## Present it

Emit the returned `html` as a **`text/html` artifact** — it renders directly in
the artifact panel. Narrate in one or two lines what the visual shows (e.g.
"side view: you launch at 9° and peak at 18 m — low for driver; top-down: every
shot bends right"), then point at the Fix it section: range drills for the next
session, home drills for today.

## What it renders

- **Flight — side view** (hero): every measured arc faint, the average animated,
  apex label only when `maxHeight` was measured, dotted roll after carry, and a
  launch/peak/landing/hang caption.
- **Ball flight — top-down**: per-shot curved tracers + landing spots, the
  average animated, target line, caption.
- **Swing path**: animated clubhead on the actual path (red) vs ideal (green),
  face at impact (yellow), caption tying path + face-to-path to the curve.
- **Targets**: bars with the good zone shaded, met/not-yet pills, replay.
- **Fix it — drills**: "At the range" and "At home — no ball" groups, each
  drill with its links.

Only plot metrics that exist in the data — if a field is missing, the viz
adapts (panel hides, label drops) rather than faking it.
````

- [ ] **Step 3: Run the guards**

Run: `uv run pytest tests/test_prompts.py tests/test_skill_content.py tests/test_setup.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/trackman-visualizer/SKILL.md skills/trackman-visualizer/PROMPT.md
git commit -m "Rewire trackman-visualizer to the trajectory-first page"
```

---

### Task 8: Rewire golf-coaching (SKILL.md + PROMPT.md)

**Files:**
- Modify: `skills/golf-coaching/SKILL.md`
- Modify: `skills/golf-coaching/PROMPT.md`
- Test: `uv run pytest tests/test_skill_content.py -v`

**Interfaces:**
- Consumes: visualizer wording from Task 7 (references stay `trackman-visualizer`).
- Produces: Prescribe-step contract other skills rely on: blocks tagged `where`, 2–3 `links` each. Guard words that must remain: "build_visualization", "verify", "animat", "video link", "never invent", "never give text-only".

- [ ] **Step 1: Edit `skills/golf-coaching/SKILL.md`**

(a) Replace the first proactive rule:

```
- **ALWAYS explain visually, every time.** Any reply that diagnoses, prescribes,
  shows data/progress, or explains a drill MUST include a visual:
  `build_visualization` for shot pattern / swing path / targets, **plus** the
  mechanics animated one drill at a time (red current → green target). See the
  `trackman-visualizer` skill. Never give text-only coaching. Animation + video
  is the standard.
```

with:

```
- **ALWAYS explain visually, every time.** Any reply that diagnoses, prescribes,
  shows data/progress, or explains a drill MUST include a visual:
  `build_visualization` renders the **real measured flight animated** — side
  view + top-down shape — plus swing path, targets, and the Fix-it drill links.
  See the `trackman-visualizer` skill. Never give text-only coaching. Animated
  flight + videos is the standard.
```

(b) Replace the second rule:

```
- **EVERY drill gets a video link.** Never hand over a drill without a verified
  YouTube link — pull from `drill-library`, or live-search and verify one (never
  invent URLs). A drill with no video is incomplete.
```

with:

```
- **EVERY drill gets a video link — ideally several.** Never hand over a drill
  without at least one verified YouTube link; prefer 2–3 per drill — pull from
  `drill-library`, or live-search and verify (never invent URLs). A drill with
  no video is incomplete.
```

(c) In **Step 3 — Prescribe**, replace:

```
- Each block: club, distances, targets, reps, a **measurable goal on Trackman**,
  a **YouTube drill link**, and the **strokes it saves**.
```

with:

```
- Each block: club, distances, targets, reps, a **measurable goal on Trackman**,
  **2–3 verified YouTube drill links**, a `where` tag (`range` or `home`), and
  the **strokes it saves**. Prescribe both flavors: range blocks for the next
  session, at least one `home` block for today.
```

(d) In the **Step 4** save example, replace the blocks line:

```
    {"name": "...", "club": "...", "reps": N, "detail": "...",
     "link": "https://...", "goal": "<measurable Trackman goal>"}
```

with:

```
    {"name": "...", "club": "...", "reps": N, "detail": "...",
     "where": "range" | "home",
     "links": [{"label": "video", "url": "https://..."}],
     "link": "https://...",   // first link repeated for older consumers
     "goal": "<measurable Trackman goal>"}
```

- [ ] **Step 2: Make the same four edits in `skills/golf-coaching/PROMPT.md`**

(a) Replace:

```
- **ALWAYS explain visually — every time.** Any reply that diagnoses, prescribes,
  shows data/progress, or explains a drill MUST include a visual. Call
  `build_visualization` for the shot pattern / swing path / target progress, and
  **animate the mechanics one drill at a time** (red current move → green target
  move). See the `trackman-visualizer` prompt. Never give text-only coaching —
  if you're saying it, show it. Animation + a video is the standard format.
```

with:

```
- **ALWAYS explain visually — every time.** Any reply that diagnoses, prescribes,
  shows data/progress, or explains a drill MUST include a visual. Call
  `build_visualization` — it renders the **real measured flight animated**
  (side view + top-down shape), the swing path, target progress, and the Fix-it
  drill links. See the `trackman-visualizer` prompt. Never give text-only
  coaching — if you're saying it, show it. Animated flight + videos is the
  standard format.
```

(b) Replace:

```
- **EVERY drill gets a video link.** Never hand over a drill without a YouTube
  link. Pull it from the `drill-library` prompt; if there's no curated link,
  live-search and verify a real one — never invent URLs. A drill with no video is
  incomplete.
```

with:

```
- **EVERY drill gets a video link — ideally several.** Never hand over a drill
  without at least one verified YouTube link; prefer 2–3 per drill. Pull from
  the `drill-library` prompt; if there's no curated link, live-search and
  verify real ones — never invent URLs. A drill with no video is incomplete.
```

(c) In **3. Prescribe**, replace:

```
For each block give: club, distances, targets, reps,
a **measurable Trackman goal**, a **drill** (with a YouTube link), and the
**strokes it saves**. Spend the most reps on the #1 leak.
```

with:

```
For each block give: club, distances, targets, reps,
a **measurable Trackman goal**, a **drill** with **2–3 verified YouTube links**
and a `where` tag (`range` or `home`), and the **strokes it saves**. Prescribe
both flavors — range blocks for the next session, at least one `home` block for
today. Spend the most reps on the #1 leak.
```

(d) In the **4. Save it** example, replace the blocks line:

```
    {"name": "...", "club": "...", "reps": N, "detail": "...",
     "link": "https://...", "goal": "<measurable Trackman goal>"}
```

with:

```
    {"name": "...", "club": "...", "reps": N, "detail": "...",
     "where": "range" | "home",
     "links": [{"label": "video", "url": "https://..."}],
     "link": "https://...",   // first link repeated for older consumers
     "goal": "<measurable Trackman goal>"}
```

- [ ] **Step 3: Run the guards**

Run: `uv run pytest tests/test_skill_content.py -v`
Expected: all PASS (check especially `test_golf_coaching_mandates_visual_and_video_every_time` — "animat" now matches "animated flight", "video link" still present).

- [ ] **Step 4: Commit**

```bash
git add skills/golf-coaching/SKILL.md skills/golf-coaching/PROMPT.md
git commit -m "Coach prescribes where-tagged blocks with multiple links"
```

---

### Task 9: Rewire drill-library (SKILL.md + PROMPT.md)

**Files:**
- Modify: `skills/drill-library/SKILL.md`
- Modify: `skills/drill-library/PROMPT.md`
- Test: `uv run pytest tests/test_skill_content.py -v`

**Interfaces:**
- Consumes: nothing.
- Produces: drill rows carry an explicit `where` value the coach copies into blocks. Guard words that must remain: "no exceptions", "never invent", "video link", and the drill names wall / pump-and-drop / trail-arm / split-hands / step-through.

- [ ] **Step 1: Edit `skills/drill-library/SKILL.md`**

(a) Replace the closing line of the at-home section:

```
Tell the user: go slow and over-correct (neutral will feel like a hook at
first); daily beats weekly; swing at a dandelion/tee for start-line feedback.
Best shown animated one drill at a time (see `trackman-visualizer`).
```

with:

```
Tell the user: go slow and over-correct (neutral will feel like a hook at
first); daily beats weekly; swing at a dandelion/tee for start-line feedback.
Hand these to the coach as `where: "home"` blocks (with links) so they appear
in the Fix-it section of the trajectory page (see `trackman-visualizer`).
```

(b) Replace the curated-table header and rows to add a `Where` column:

```
| Category | Drill | What to do | Video |
|----------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | 3 carry numbers (e.g. 50/70/90y), 5 balls each, log carry on Trackman; aim ±5y | _TODO: add vetted link_ |
| `dispersion-irons` | Gate / alignment-stick window | Set sticks as a start-line gate; 7-iron, must start every ball through the gate | _TODO: add vetted link_ |
| `strike-low-point` | Towel / line drill | Strike a line (or just past a towel) so divot starts after the ball; check smash factor | _TODO: add vetted link_ |
| `driver-launch` | Tee height + AoA ladder | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window | _TODO: add vetted link_ |
| `gapping` | Build-your-yardages session | Hit each club 5x, record avg carry, find overlaps/holes; pick one club to re-loft or swap | _TODO: add vetted link_ |
| `putting-speed` | Ladder lag drill | Putt to 20/30/40ft, finish within a 3ft zone past the hole; speed over line | _TODO: add vetted link_ |
```

with:

```
| Category | Drill | Where | What to do | Video |
|----------|-------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | range | 3 carry numbers (e.g. 50/70/90y), 5 balls each, log carry on Trackman; aim ±5y | _TODO: add vetted link_ |
| `dispersion-irons` | Gate / alignment-stick window | range | Set sticks as a start-line gate; 7-iron, must start every ball through the gate | _TODO: add vetted link_ |
| `strike-low-point` | Towel / line drill | range | Strike a line (or just past a towel) so divot starts after the ball; check smash factor | _TODO: add vetted link_ |
| `driver-launch` | Tee height + AoA ladder | range | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window | _TODO: add vetted link_ |
| `gapping` | Build-your-yardages session | range | Hit each club 5x, record avg carry, find overlaps/holes; pick one club to re-loft or swap | _TODO: add vetted link_ |
| `putting-speed` | Ladder lag drill | range | Putt to 20/30/40ft, finish within a 3ft zone past the hole; speed over line | _TODO: add vetted link_ |
```

(c) After the intro sentence "**Every drill handed to the user ships with a video link — no exceptions.**  If the table has no link, live-search and verify one first; never give a drill without a video, and never invent a URL." append:

```
Prefer **2–3 verified links per drill** when the library or a live search can
supply them — the Fix-it section renders them all. Every drill also carries a
`where` value (`range` needs balls/bay; `home` needs neither) so the coach can
tag its block. The whole at-home table below is `home`.
```

- [ ] **Step 2: Make the matching edits in `skills/drill-library/PROMPT.md`**

(a) Replace:

```
These are **best shown animated, one drill at a time** (red current move → green
target move) — see the `trackman-visualizer` prompt.
```

with:

```
Hand these to the coach as `where: "home"` blocks (with links) so they appear in
the Fix-it section of the trajectory page — see the `trackman-visualizer` prompt.
```

(b) Replace the curated-table header and rows (same `Where` column, all `range`):

```
| Category | Drill | What to do | Video |
|----------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | 3 carry numbers (e.g. 50/70/90 m), 5 balls each, log carry on Trackman; aim ±5 m | _find via Live search_ |
| `dispersion-irons` | Gate / alignment-stick window | Sticks as a start-line gate; 7-iron must start every ball through the gate | _find via Live search_ |
| `strike-low-point` | Towel / line drill | Strike a line so the divot starts after the ball; check smash factor | _find via Live search_ |
| `driver-launch` | Tee height + AoA ladder | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window | _find via Live search_ |
| `gapping` | Build-your-yardages session | Hit each club 5×, record avg carry, find overlaps/holes; pick one club to re-loft or swap | _find via Live search_ |
| `putting-speed` | Ladder lag drill | Putt to 6/9/12 m, finish within a 1 m zone past the hole; speed over line | _find via Live search_ |
```

with:

```
| Category | Drill | Where | What to do | Video |
|----------|-------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | range | 3 carry numbers (e.g. 50/70/90 m), 5 balls each, log carry on Trackman; aim ±5 m | _find via Live search_ |
| `dispersion-irons` | Gate / alignment-stick window | range | Sticks as a start-line gate; 7-iron must start every ball through the gate | _find via Live search_ |
| `strike-low-point` | Towel / line drill | range | Strike a line so the divot starts after the ball; check smash factor | _find via Live search_ |
| `driver-launch` | Tee height + AoA ladder | range | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window | _find via Live search_ |
| `gapping` | Build-your-yardages session | range | Hit each club 5×, record avg carry, find overlaps/holes; pick one club to re-loft or swap | _find via Live search_ |
| `putting-speed` | Ladder lag drill | range | Putt to 6/9/12 m, finish within a 1 m zone past the hole; speed over line | _find via Live search_ |
```

(c) After "**Every drill you hand the user ships with a video link — no exceptions.** If the table has no link for it, run Live search and verify one before giving it. Never hand over a drill without a video, and never invent a URL." append:

```
Prefer **2–3 verified links per drill** when available — the Fix-it section
renders them all. Every drill carries a `where` value (`range` or `home`); the
whole at-home table below is `home`.
```

- [ ] **Step 3: Run the guards**

Run: `uv run pytest tests/test_skill_content.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/drill-library/SKILL.md skills/drill-library/PROMPT.md
git commit -m "Tag drill-library entries with where and prefer multiple links"
```

---

### Task 10: Rewire golf-practice-at-home (SKILL.md + PROMPT.md)

**Files:**
- Modify: `skills/golf-practice-at-home/SKILL.md`
- Modify: `skills/golf-practice-at-home/PROMPT.md`
- Test: `uv run pytest tests/test_skill_content.py tests/test_prompts.py -v`

**Interfaces:**
- Consumes: drill-library `where`/links convention from Task 9.
- Produces: the routine presentation contract (feel cue + reps + multiple links; no per-drill animation). Guard words that must remain: "no ball"/"no-ball", "training_plan".

- [ ] **Step 1: Edit `skills/golf-practice-at-home/SKILL.md`**

(a) Replace the frontmatter description:

```
description: Use when the user wants to practice at home / in the yard / without a ball or range, or can't get to a range. Builds a short daily no-ball routine targeting their diagnosed swing fault, shows each drill animated one at a time, and saves it as a training plan to recall and grade later. Triggers on "practice at home", "no range", "without a ball", "in the yard", "drills I can do at home".
```

with:

```
description: Use when the user wants to practice at home / in the yard / without a ball or range, or can't get to a range. Builds a short daily no-ball routine targeting their diagnosed swing fault, gives every drill multiple verified video links, and saves it as a training plan to recall and grade later. Triggers on "practice at home", "no range", "without a ball", "in the yard", "drills I can do at home".
```

(b) Replace the intro paragraph:

```
Build the user a short **daily no-ball routine** for the yard or living room with
just a club, targeting their actual swing fault — and **show each drill
animated**, since this is usually asked by someone who learns by seeing. The MCP
tools supply the data; this skill turns it into a home routine.
```

with:

```
Build the user a short **daily no-ball routine** for the yard or living room with
just a club, targeting their actual swing fault — anchored in a visual of **what
their ball is actually doing** (the trajectory page), with **multiple verified
videos per drill** to follow. The MCP tools supply the data; this skill turns it
into a home routine.
```

(c) Replace step 4:

```
4. **Show it — one drill at a time, with a video.** Animate each drill (red
   current → green target) via the `trackman-visualizer` skill, one per exercise,
   **and give each a verified YouTube link** (from `drill-library`, or
   live-search + verify — never invent URLs). Animation + video for every drill.
```

with:

```
4. **Show the fault, then the fixes.** Render the diagnosis once via the
   `trackman-visualizer` skill — the animated trajectory page built from their
   real shots, with these drills as `where: "home"` blocks in its Fix-it
   section. Give **every drill 2–3 verified YouTube links** (from
   `drill-library`, or live-search + verify — never invent URLs) plus its feel
   cue and reps. The videos teach the motion; the page shows why it matters.
```

- [ ] **Step 2: Make the matching edits in `skills/golf-practice-at-home/PROMPT.md`**

(a) Replace the intro paragraph:

```
Build the user a short **daily no-ball routine** they can do in the yard or living
room with just a club, targeting their actual swing fault — and **show each drill
animated**, because this is usually asked by someone who learns by seeing, not
reading. Use when they say "what can I do at home / without a ball / no range,"
or can't get to a range.
```

with:

```
Build the user a short **daily no-ball routine** they can do in the yard or living
room with just a club, targeting their actual swing fault — anchored in a visual
of **what their ball is actually doing** (the trajectory page), with **multiple
verified videos per drill** to follow. Use when they say "what can I do at home /
without a ball / no range," or can't get to a range.
```

(b) Replace step 4:

```
4. **Show it — one drill at a time, with a video.** Animate each drill's intended
   motion (red current move → green target move) via the `trackman-visualizer`
   prompt, one per exercise, **and give each drill a verified YouTube link** (from
   the `drill-library` prompt, or live-search + verify one — never invent URLs).
   Animation + video for every drill; lead with the visual, don't make them ask.
```

with:

```
4. **Show the fault, then the fixes.** Render the diagnosis once via the
   `trackman-visualizer` prompt — the animated trajectory page built from their
   real shots, with these drills as `where: "home"` blocks in its Fix-it
   section. Give **every drill 2–3 verified YouTube links** (from the
   `drill-library` prompt, or live-search + verify — never invent URLs) plus its
   feel cue and reps. Lead with the visual, don't make them ask.
```

- [ ] **Step 3: Run the guards**

Run: `uv run pytest tests/test_skill_content.py tests/test_prompts.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/golf-practice-at-home/SKILL.md skills/golf-practice-at-home/PROMPT.md
git commit -m "At-home routine anchors on the trajectory page, not drill animations"
```

---

### Task 11: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `uv run pytest`
Expected: all PASS, zero warnings introduced.

- [ ] **Step 2: Headless render gate**

Run: `uv run python scripts/check-visualization.py --demo /tmp/viz-final.png`
Expected: `RENDER OK`. Inspect `/tmp/viz-final.png`: side-view hero with apex label + roll, per-shot faint tracers in both views, swing path unchanged, targets bars, Fix-it with both groups and the multi-link drill.

- [ ] **Step 3: Degradation render checks**

Create `/tmp/viz-noheight.json` with shots lacking height fields:

```json
{"title": "No height data", "shots": [{"launchDirection": -2, "carry": 200, "totalSide": 25, "curve": 14}], "swing": {"clubPath": -5.0, "faceAngle": -1.0}}
```

Run:

```bash
uv run python scripts/visualize.py /tmp/viz-noheight.json /tmp/viz-noheight.html
uv run python scripts/check-visualization.py /tmp/viz-noheight.html /tmp/viz-noheight.png
```

Expected: `RENDER OK`; screenshot shows NO side-view panel (hidden), top-down + swing path render normally.

- [ ] **Step 4: Live API check (only if a token is available)**

Run: `TRACKMAN_TOKEN=... uv run python scripts/validate.py`
Expected: exit 0 — confirms the Task 1 field additions resolve against the live schema. If no token is available, flag this to the user as the one unverified item.

- [ ] **Step 5: Manual Desktop pass (user-assisted, cannot be automated)**

The `trackman-golf-dev` entry in `~/Library/Application Support/Claude/claude_desktop_config.json` points at this checkout. Restart Claude Desktop and confirm:
1. `build_visualization` with a trajectory payload renders the new page as an interactive artifact (side view animates, Fix-it groups show).
2. The `trackman-visualizer` and `golf-practice-at-home` prompts appear in the prompt picker and read per Tasks 7/10.

Report the outcome to the user; this gates "done".
