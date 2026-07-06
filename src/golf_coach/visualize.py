"""Generate a self-contained animated HTML visualization of a coaching diagnosis.

Renders four things from real Trackman data, no external dependencies (pure
canvas/JS in one HTML file):
  1. Flight side view — the real measured trajectory (launch/apex/landing),
     every shot faint + the average animated, roll after carry.
  2. Ball-flight top-down — per-shot curved tracers + the average animated.
  3. Swing path — animated clubhead on the actual path vs ideal, with the face
     angle, annotating *why* the ball curves.
  4. Target progress + Fix-it drills grouped range/home with multiple links.

Usage (library):
    from scripts.visualize import build_html
    html = build_html(data)            # data: see DATA SCHEMA below
    open("viz.html", "w").write(html)

Usage (CLI):
    uv run python scripts/visualize.py <data.json> <out.html>
    uv run python scripts/visualize.py --demo out.html

DATA SCHEMA (all fields optional; the viz adapts):
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
"""

from __future__ import annotations

import html as _html
import json
import re
import sys

_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{--bg:#0b1220;--panel:#121c2e;--ink:#e7eef7;--mut:#8aa0bd;--good:#27c08a;--bad:#ff6b6b;--acc:#4ea1ff;--fair:#1f8a4c;}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:24px}
  h1{font-size:24px;margin:0 0 2px} .sub{color:var(--mut);margin:0 0 18px}
  .diag{background:var(--panel);border-left:3px solid var(--acc);padding:12px 16px;
    border-radius:8px;margin:0 0 20px;color:#cfe0f5}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:840px){.grid{grid-template-columns:1fr}}
  .card{background:var(--panel);border-radius:12px;padding:16px}
  .hero{margin:0 0 18px}
  .card h2{font-size:15px;margin:0 0 10px;color:#bcd2f0;letter-spacing:.3px;text-transform:uppercase}
  canvas{width:100%;height:auto;display:block;background:#0e1626;border-radius:8px}
  .legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--mut);font-size:12px;margin-top:8px}
  .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
  .why{margin-top:10px;color:#cfe0f5;font-size:13px}
  .bars{display:flex;flex-direction:column;gap:12px}
  .bar h3{margin:0 0 4px;font-size:13px;font-weight:600;display:flex;justify-content:space-between}
  .track{position:relative;height:14px;background:#0e1626;border-radius:7px;overflow:hidden}
  .zone{position:absolute;top:0;bottom:0;background:rgba(39,192,138,.25)}
  .val{position:absolute;top:-3px;width:3px;height:20px;background:var(--ink);border-radius:2px}
  .pill{font-size:11px;padding:1px 8px;border-radius:10px}
  .pill.ok{background:rgba(39,192,138,.2);color:var(--good)}
  .pill.no{background:rgba(255,107,107,.2);color:var(--bad)}
  .pill.na{background:#22304a;color:var(--mut)}
  .fixhead{margin:10px 0 4px;font-size:13px;color:#bcd2f0;letter-spacing:.3px;text-transform:uppercase}
  .fixlist{margin:0 0 6px;padding-left:20px} .fixlist li{margin:6px 0;color:#cfe0f5}
  .fixlist a{color:var(--acc)} .full{grid-column:1/-1}
  button{background:#1c2c47;color:var(--ink);border:1px solid #2b4068;border-radius:8px;
    padding:6px 12px;cursor:pointer;font-size:13px} button:hover{background:#22365a}
</style></head>
<body><div class="wrap">
  <h1>__TITLE__</h1><p class="sub">__SUBTITLE__</p>
  <div class="diag">__DIAGNOSIS__</div>
  <div class="card hero" id="sideCard"><h2>Ball flight — side view</h2>
    <canvas id="side" width="1040" height="330"></canvas>
    <div class="legend">
      <span><i class="dot" style="background:#4ea1ff"></i>average flight</span>
      <span><i class="dot" style="background:rgba(78,161,255,.4)"></i>each shot</span>
      <span><i class="dot" style="background:#ffd166"></i>roll after carry</span>
    </div>
    <div class="why" id="sideWhy"></div>
  </div>
  <div class="grid">
    <div class="card"><h2>Ball flight</h2>
      <canvas id="flight" width="500" height="520"></canvas>
      <div class="legend">
        <span><i class="dot" style="background:#4ea1ff"></i>your shot</span>
        <span><i class="dot" style="background:#6b7a93"></i>target line</span>
        <span><i class="dot" style="background:#ffd166"></i>landing spots</span>
      </div>
      <div class="why" id="flightWhy"></div>
    </div>
    <div class="card"><h2>Swing path — why it curves</h2>
      <canvas id="swing" width="500" height="520"></canvas>
      <div class="legend">
        <span><i class="dot" style="background:#ff6b6b"></i>your path</span>
        <span><i class="dot" style="background:#27c08a"></i>ideal path</span>
        <span><i class="dot" style="background:#ffd166"></i>club face</span>
      </div>
      <div class="why" id="swingWhy"></div>
    </div>
    <div class="card full"><h2>Progress vs targets</h2>
      <div class="bars" id="bars"></div>
      <button onclick="replay()">↻ Replay animation</button>
    </div>
    <div class="card full"><h2>Fix it — drills</h2>
      <div id="fixit"></div>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;
const RH = (DATA.handedness||"RH")!=="LH";   // sign of "right" for the golfer
// ---------- helpers ----------
const $=s=>document.querySelector(s);
// Safe DOM builders — never assign data to innerHTML (avoids HTML/JS injection
// from Trackman field values or model-supplied coaching text).
function el(tag,cls,text){const e=document.createElement(tag);
  if(cls)e.className=cls; if(text!=null)e.textContent=String(text); return e;}
function safeHref(u){ if(typeof u!=='string') return null;
  try{const url=new URL(u,location.href);
    return (url.protocol==='http:'||url.protocol==='https:')?url.href:null;}
  catch(e){return null;} }
function fit(c){const ctx=c.getContext('2d');const s=window.devicePixelRatio||1;
  const w=c.clientWidth;const h=c.height* (w/c.width); c.width=w*s;c.height=h*s;ctx.scale(s,s);
  return {ctx,w,h};}
function lerp(a,b,t){return a+(b-a)*t}
function bez(p0,p1,p2,t){const u=1-t;return{
  x:u*u*p0.x+2*u*t*p1.x+t*t*p2.x, y:u*u*p0.y+2*u*t*p1.y+t*t*p2.y};}

// aggregate shot shape
const shots = (DATA.shots&&DATA.shots.length)?DATA.shots:[{launchDirection:0,carry:200,totalSide:0,curve:0}];
const avg=k=>shots.reduce((a,s)=>a+(typeof s[k]==='number'?s[k]:0),0)/shots.length;
const A={launch:avg('launchDirection'),carry:avg('carry')||avg('total')||200,
  side:avg('totalSide'),curve:avg('curve')};

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

// ---------- ball flight ----------
function drawFlight(t){
  const c=$('#flight'); const {ctx,w,h}=fit(c);
  ctx.clearRect(0,0,w,h);
  const maxCarry=Math.max(120, ...shots.map(s=>(s.carry||s.total||0)))*1.1;
  const maxSide=Math.max(20, ...shots.map(s=>Math.abs(s.totalSide||0)+8))*1.15;
  const x0=w/2, padT=20, padB=24, H=h-padT-padB;
  const sx=v=> x0 + (RH? v: -v)/maxSide*(w/2-18);   // meters lateral -> px
  const sy=d=> padT + (1-d/maxCarry)*H;             // meters downrange -> px (up)
  // grid: distance rings
  ctx.strokeStyle="#1b2740";ctx.fillStyle="#6b7a93";ctx.font="11px sans-serif";
  for(let d=0; d<=maxCarry; d+=Math.ceil(maxCarry/5/10)*10){
    ctx.strokeStyle="#16213a";ctx.beginPath();ctx.moveTo(14,sy(d));ctx.lineTo(w-6,sy(d));ctx.stroke();
    ctx.fillStyle="#5b6a85";ctx.fillText(d+"m",16,sy(d)-3);
  }
  // target line
  ctx.strokeStyle="#6b7a93";ctx.setLineDash([6,6]);ctx.beginPath();
  ctx.moveTo(x0,sy(0));ctx.lineTo(x0,sy(maxCarry));ctx.stroke();ctx.setLineDash([]);
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
  // animated ball + trail
  ctx.strokeStyle="#4ea1ff";ctx.lineWidth=3;ctx.beginPath();
  for(let u=0;u<=t;u+=0.02){const p=bez(p0,ctrl,end,u);u==0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y);}
  ctx.stroke();
  const b=bez(p0,ctrl,end,t);
  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(b.x,b.y,5,0,7);ctx.fill();
  // tee marker
  ctx.fillStyle="#9fb4d4";ctx.beginPath();ctx.arc(p0.x,p0.y,4,0,7);ctx.fill();
}
const sideTxt = Math.abs(A.side)<3?"roughly straight":
  ((A.side>0)===RH?`${Math.abs(A.side).toFixed(0)} m right`:`${Math.abs(A.side).toFixed(0)} m left`);
$('#flightWhy').innerHTML = `Average shot starts ${A.launch>0===RH?'right':A.launch<0?'left':'on line'} `+
  `and finishes <b>${sideTxt}</b> of target (curve ${A.curve>=0?'+':''}${A.curve.toFixed(1)} m).`;

// ---------- swing path ----------
const sw=DATA.swing||{}; const path=sw.clubPath||0, face=sw.faceAngle||0,
  f2p=(sw.faceToPath!=null)?sw.faceToPath:(face-path);
function drawSwing(t){
  const c=$('#swing'); const {ctx,w,h}=fit(c);
  ctx.clearRect(0,0,w,h);
  const cx=w/2, cy=h*0.62, L=Math.min(w,h)*0.42;
  // target line (up)
  ctx.strokeStyle="#3a4a66";ctx.setLineDash([5,5]);
  ctx.beginPath();ctx.moveTo(cx,cy+L*0.5);ctx.lineTo(cx,cy-L);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle="#5b6a85";ctx.font="11px sans-serif";ctx.fillText("target",cx+6,cy-L+12);
  // ideal path (green) slight in-to-out
  // +deg = in-to-out: to the RIGHT of target for RH (matches the ball-flight
  // panel's sx convention), to the LEFT for LH. (Was mirrored for RH.)
  function ang(a){return (RH?a:-a)*Math.PI/180;}
  function line(angDeg,color,wid,dash){
    const a=ang(angDeg)-Math.PI/2; // measured from vertical
    ctx.strokeStyle=color;ctx.lineWidth=wid;ctx.setLineDash(dash||[]);
    ctx.beginPath();
    ctx.moveTo(cx-Math.cos(a)*L,cy-Math.sin(a)*L);
    ctx.lineTo(cx+Math.cos(a)*L,cy+Math.sin(a)*L);ctx.stroke();ctx.setLineDash([]);
  }
  line(1.0,"#27c08a",2,[6,5]);         // ideal ~+1°
  line(path,"#ff6b6b",3);              // actual path
  // ball
  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(cx,cy,7,0,7);ctx.fill();
  // animated clubhead travelling up the actual path
  const a=ang(path)-Math.PI/2;
  const tt=(t*2-1); // -1..1
  const hx=cx+Math.cos(a)*L*tt, hy=cy+Math.sin(a)*L*tt;
  ctx.fillStyle="#ff9aa2";ctx.beginPath();ctx.arc(hx,hy,6,0,7);ctx.fill();
  // face line at impact (rotate by faceAngle)
  if(t>0.5){
    const fa=ang(face); const fl=L*0.5;
    ctx.strokeStyle="#ffd166";ctx.lineWidth=4;ctx.beginPath();
    ctx.moveTo(cx-Math.cos(fa)*fl, cy-Math.sin(fa)*fl);
    ctx.lineTo(cx+Math.cos(fa)*fl, cy+Math.sin(fa)*fl);ctx.stroke();
  }
  // arrowhead on actual path
  ctx.fillStyle="#ff6b6b";
  const ahx=cx+Math.cos(a)*L, ahy=cy+Math.sin(a)*L;
  ctx.beginPath();ctx.arc(ahx,ahy,4,0,7);ctx.fill();
  // degree labels for legibility (top-down angles are small)
  ctx.font="12px sans-serif";
  ctx.fillStyle="#ff9aa2";ctx.fillText(`path ${path>=0?'+':''}${path.toFixed(1)}°`, ahx+8, ahy+4);
  const ga=ang(1.0)-Math.PI/2;
  ctx.fillStyle="#5fd0a0";ctx.fillText("ideal", cx+Math.cos(ga)*L+8, cy+Math.sin(ga)*L+14);
  if(t>0.5){ctx.fillStyle="#ffd166";
    ctx.fillText(`face ${face>=0?'+':''}${face.toFixed(1)}°`, cx+L*0.5+8, cy-6);}
}
const dir = path<0 ? (RH?"out-to-in (over the top)":"in-to-out") : (RH?"in-to-out":"out-to-in");
const startSide = path<0?(RH?"left":"right"):(RH?"right":"left");
const curveSide = f2p>0?(RH?"right":"left"):(RH?"left":"right");
$('#swingWhy').innerHTML =
  `Club path <b>${path>=0?'+':''}${path.toFixed(1)}°</b> (${dir}) — the ball starts ${startSide}. `+
  `Face is <b>${f2p>=0?'+':''}${f2p.toFixed(1)}°</b> ${f2p>=0?'open':'closed'} to that path, so it curves ${curveSide}. `+
  (path<0?`Goal: bring the red line toward the green (path to neutral) and the curve straightens.`:``);

// ---------- target bars ----------
function renderBars(){
  const host=$('#bars');host.textContent="";
  (DATA.targets||[]).forEach(t=>{
    const met=t.met;
    const div=el('div','bar');
    const h3=el('h3');
    const left=el('span');
    left.appendChild(document.createTextNode((t.label!=null?t.label:'')+' '));
    left.appendChild(el('span','pill '+(met===true?'ok':met===false?'no':'na'),
      met===true?'met':met===false?'not yet':'no data'));
    const right=el('span'); right.style.color='var(--mut)';
    right.textContent='you '+(t.value??'—')+' · target '+(t.target||'');
    h3.appendChild(left); h3.appendChild(right); div.appendChild(h3);
    // scale: pad around value and zone
    const lo=t.low, hi=t.high;
    const track=el('div','track');
    const nums=[t.value,lo,hi].filter(v=>typeof v==='number');
    if(nums.length){
      const mn=Math.min(...nums), mx=Math.max(...nums); const pad=(mx-mn||1)*0.4;
      const lo2=mn-pad, hi2=mx+pad, span=hi2-lo2;
      const pct=v=>((v-lo2)/span*100);
      if(typeof lo==='number'&&typeof hi==='number'){
        const z=el('div','zone'); z.style.left=pct(lo)+'%'; z.style.width=(pct(hi)-pct(lo))+'%';
        track.appendChild(z);}
      if(typeof t.value==='number'){
        const v=el('div','val'); v.style.left=pct(t.value)+'%'; track.appendChild(v);}
    }
    div.appendChild(track);
    host.appendChild(div);
  });
}

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

function replay(){ if(rafId)cancelAnimationFrame(rafId); t0=null;
  rafId=requestAnimationFrame(tick); }
renderBars();renderBlocks();sideCaption();replay();
window.addEventListener('resize',()=>{drawSide(clockT);drawFlight(clockT);drawSwing(clockT);});
</script></body></html>
"""


def _json_for_script(data: dict) -> str:
    """Serialize `data` so it is safe to embed inside an inline <script> block.

    Neutralizes the characters that could break out of the HTML script context
    (`<`, `>`, `&`) and the two line terminators JS treats as newlines. These
    become valid JS string escapes, so the parsed value is unchanged — but no
    field value (even one containing `</script>`) can close the element.
    """
    payload = json.dumps(data)
    return (
        payload.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


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


def build_html(data: dict) -> str:
    """Render the visualization HTML, escaping all data against injection.

    `title`/`subtitle`/`diagnosis` are HTML-escaped (they land in the document
    body); the rest of `data` is embedded as breakout-safe JSON and rendered
    client-side via textContent (see the template's safe DOM helpers).
    """
    _validate_blocks(data)
    replacements = {
        "__DATA__": _json_for_script(data),
        "__TITLE__": _html.escape(str(data.get("title", "Trackman Coach"))),
        "__SUBTITLE__": _html.escape(str(data.get("subtitle", ""))),
        "__DIAGNOSIS__": _html.escape(str(data.get("diagnosis", ""))),
    }
    # Single left-to-right pass: replacement text is never re-scanned, so a data
    # value that happens to equal a placeholder can't corrupt the output.
    return re.sub(
        r"__DATA__|__TITLE__|__SUBTITLE__|__DIAGNOSIS__",
        lambda m: replacements[m.group(0)],
        _TEMPLATE,
    )


# Fictional sample data (not any real golfer) — for `--demo` only.
_DEMO = {
    "title": "Driver — slice fix (sample)",
    "subtitle": "Out-to-in path • face open to path",
    "diagnosis": "Path-driven pull-slice: club swings out-to-in, face open to path "
                 "→ ball starts left and curves right.",
    "handedness": "RH",
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
    "swing": {"clubPath": -5.0, "faceAngle": -1.0, "faceToPath": 4.0},
    "targets": [
        {"label": "club path", "value": -5.0, "target": "-1..+2", "low": -1, "high": 2, "met": False},
        {"label": "spin axis", "value": 6.0, "target": "|x| < 3", "low": -3, "high": 3, "met": False},
        {"label": "curve", "value": 14.0, "target": "|x| < 4", "low": -4, "high": 4, "met": False},
    ],
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
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--demo":
        out = argv[1] if len(argv) > 1 else "viz.html"
        data = _DEMO
    else:
        data = json.loads(open(argv[0]).read())
        out = argv[1] if len(argv) > 1 else "viz.html"
    open(out, "w").write(build_html(data))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
