'use strict';
/* Planet (game side of world3d.js, Daniel 2026-11-24): the little planet the fight runs on, its destructibles and the
   gravity numbers. Settings = characters/world3d.json (World Studio 3D), packed into data/world.gen.js.
   - WORLD_CFG / PLANET (core.js): with the planet on, the sim plane has no walls (W / H are huge) and the world
     bends onto the globe in the vertex shader; world3d.js rolls the planet under the fight (anchor = fight centre).
   - planetReset() builds a new world each fight (seed 0 = new look each time), planetFrame() turns the globe and
     runs its animations, planetTick() is the sim side: fighters bump / splat / smash through pillars, scenery and
     landmarks, shots are blocked, knockback slides carve trenches. planetHit / planetBlast / planetCrater are called
     from combat.js, fx.js, fighter.js and gravity.js.
   - GRAV: the gravity numbers (100 % = the old constants), used on the flat arena too. */
World3D.installBend();
const GRAV=World3D.gravityOf(WORLD_CFG);
let world=null;
if(PLANET)arenaG.visible=false;
const BODY_R=16;   // fighter body radius on the ground (px)
const pX=x=>(x-W/2)*K, pZ=y=>(y-H/2)*K;          // sim px -> scene units
const bendP=v=>PLANET?World3D.bendV(v):v;          // a flat scene point -> where it is drawn
// the inverse: a drawn (bent) point -> the flat scene point that bends onto it (camera framing in drawn space)
function unbendP(q){const B=World3D.BEND;if(!PLANET||!(B.w>0))return q.clone();const R=B.w,cx=q.x-B.x,cy=q.y+R,cz=q.z-B.z,r=Math.hypot(cx,cy,cz)||1e-6;
  const th=Math.acos(Math.max(-1,Math.min(1,cy/r))),h=Math.hypot(cx,cz);
  return h<1e-6?new THREE.Vector3(B.x,r-R,B.z):new THREE.Vector3(B.x+cx/h*th*R,r-R,B.z+cz/h*th*R);}
function planetReset(){if(!PLANET)return;if(world)world.dispose();
  world=new World3D.World(scene,WORLD_CFG,{});world.setAnchor(0,0,true);
  scene.background=new THREE.Color(world.pal.sky[1]);const fr=world.fogRange();
  scene.fog=new THREE.Fog(world.pal.fog,fr?fr[0]:1e5,fr?fr[1]:2e5);
  planetFog=[scene.fog.near,scene.fog.far];cam.far=Math.max(400,world.R*3.2+320);cam.updateProjectionMatrix();planetSolids=null;}
let planetFog=null;
// the spot the globe keeps on top (Daniel 2026-11-24): the knockback tracking shot's fighter while the camera rides with
// it (camera.js track), else the midpoint of the two on-field fighters measured the SHORT way round the planet.
const planetCirc=()=>2*Math.PI*world.R/K;   // once round the planet, sim px
function planetAnchor(){if(typeof track!=='undefined'&&track.f&&track.f.on&&(track.ph===1||track.ph===2))return [track.f.x,track.f.y,true];
  const [a,b]=onField();if(!a)return null;
  if(!b||b.phantom||b.ko||!b.on)return [a.x,a.y];
  let dx=b.x-a.x,dy=b.y-a.y;const d=Math.hypot(dx,dy),C=planetCirc();if(d>C/2){dx-=dx/d*C;dy-=dy/d*C;}
  return [a.x+dx/2,a.y+dy/2];}
function planetFrame(rdt,idle){if(!PLANET||!world)return;
  const c=planetAnchor();if(c&&!idle)world.setAnchor(pX(c[0]),pZ(c[1]),false,rdt*(c[2]?3:1));   // tighter while tracking
  // seen from orbit (title) the haze would hide the planet: push it out there
  if(planetFog&&scene.fog){scene.fog.near=idle?Math.max(planetFog[0],world.R*3):planetFog[0];scene.fog.far=idle?Math.max(planetFog[1],world.R*6):planetFog[1];}
  world.update(rdt,cam.position,it=>!allFighters().some(f=>{const p=world.flatOf(it.u);return Math.hypot(pX(f.x)-p.x,pZ(f.y)-p.z)<it.cols.reduce((m,c)=>Math.max(m,c.r),1)+1.5;}));}
// title screen: the little planet seen from orbit
function planetIdleCam(){const t=performance.now()/1000*.08,R=world.R,D=R*1.25+28,A=world.A;
  cam.position.set(A.x+Math.sin(t)*D,D*.5,A.z+Math.cos(t)*D);cam.lookAt(A.x,-R*.28,A.z);}
// camera: the shot is framed on the flat plane, then bent like everything else
function planetCam(look){const p=bendP(cam.position),l=bendP(look);cam.position.copy(p);cam.lookAt(l);}
function allFighters(){const out=[];sides.forEach(s=>s.team.forEach(f=>{if(f&&f.on&&!f.ko&&!f.phantom)out.push(f);}));return out;}

/* ---------------- sim side */
let planetSolids=null;
// this tick's solids near the fight, in sim px: {c (collider), it (item), x, y, r (px), h (px)}
function nearSolids(){if(planetSolids&&planetSolids.t===tick)return planetSolids.l;const l=[];
  for(const c of world.solids){const it=c.item;if(it.dead)continue;const p=world.flatOf(c.u);if(p.th*world.R>140)continue;
    l.push({c,it,x:p.x/K+W/2,y:p.z/K+H/2,r:c.r/K,h:c.h/K});}
  planetSolids={t:tick,l};return l;}
function cfgOf(it){return it.group==='pillars'?WORLD_CFG.pillars:it.group==='scenery'?WORLD_CFG.scenery:WORLD_CFG.landmarks;}
/* Keep flying round (Daniel 2026-11-24): the sim plane is flat, the world is a globe. A point more than half way round
   from the anchor is the same globe spot as the point (once round) closer in from the other side, so it is moved there:
   a fighter thrown past the far side keeps going the same way and comes back round from behind, and the AI / distances
   use the short way. Before this the bend drew it past the far side and it looked like it reversed. */
let planetWrapped=false;   // camera.js: an on-field fighter was moved round this tick (re-frame the normal shot at once)
function planetWrap(){const C=planetCirc(),ax=world.A.x/K+W/2,ay=world.A.z/K+H/2;
  const wrap=o=>{const dx=o.x-ax,dy=o.y-ay,d=Math.hypot(dx,dy);if(d<=C/2)return null;const sx=-dx/d*C,sy=-dy/d*C;o.x+=sx;o.y+=sy;return [sx,sy];};
  const [a,b]=onField();
  sides.forEach(s=>s.team.forEach(f=>{if(!f||!f.on||f.phantom||f.mv3||f.leap>0)return;const m=wrap(f);if(!m)return;
    f.lx+=m[0];f.ly+=m[1];if(f.snap){f.snap.tx+=m[0];f.snap.ty+=m[1];f.snap.sx+=m[0];f.snap.sy+=m[1];}
    if(f===a||f===b)planetWrapped=true;}));
  shots.forEach(s=>wrap(s));}
function planetTick(){if(!PLANET||!world)return;planetWrap();const L=nearSolids();
  for(const f of allFighters()){
    for(const s of L){if(f.z>s.h)continue;const dx=f.x-s.x,dy=f.y-s.y,d=Math.hypot(dx,dy)||.001,rr=s.r+BODY_R;if(d>=rr)continue;
      const nx=dx/d,ny=dy/d,sp=Math.hypot(f.vx,f.vy),into=-(f.vx*nx+f.vy*ny);const C=cfgOf(s.it);
      if(s.it.breakable&&f.stun>0&&sp>=C.break_speed){   // smash straight through
        if(world.hitItem(s.it,0,sp,world.tangentAt(s.it.u,f.vx,f.vy))==='break'){f.vx*=.7;f.vy*=.7;shake=Math.max(shake,.5);hitstopMs=Math.max(hitstopMs,60);fx_dust(s.x,s.y,6);director.hits++;planetSolids=null;continue;}}
      f.x=s.x+nx*rr;f.y=s.y+ny*rr;
      if(into>0){f.vx+=nx*into*1.3;f.vy+=ny*into*1.3;
        if(f.stun>0&&into>700){if(s.it.breakable)world.hitItem(s.it,into/40,0,world.tangentAt(s.it.u,-nx,-ny));
          if(s.it.group!=='pillars'||C.splat){wallSplat(f,s.it.group==='scenery'?'TREE SPLAT':s.it.group==='landmarks'?'WALL SPLAT':'PILLAR SPLAT');}}}}
    // knockback slides carve trenches: square-cut pieces laid end to end from the last spot, rounded at both ends of the
    // slide (one seamless trench; digChain, world3d.js _bowl)
    const sp=Math.hypot(f.vx,f.vy);if(f.stun>0&&f.z<12&&sp>900&&tick-(f.trenchT||0)>=5){f.trenchT=tick;let L=f.trL;
      if(!L||tick-L.t>8){const b=sp*5*DT;L={x:f.x-f.vx/sp*b,y:f.y-f.vy/sp*b,w:.45+Math.min(.5,sp/6000),ch:null};}   // a new slide
      L.ch=digChain(L.ch,pX(L.x),pZ(L.y),pX(f.x),pZ(f.y),L.w,{});f.trL={x:f.x,y:f.y,t:tick,w:L.w,ch:L.ch};}}}
// a shot this tick: true = blocked (the shot dies)
function planetShot(s){if(!PLANET||!world)return false;
  for(const o of nearSolids()){if((s.z||0)>o.h)continue;if(Math.hypot(s.x-o.x,s.y-o.y)>o.r+10)continue;const it=o.it;
    if(it.group==='pillars'&&!WORLD_CFG.pillars.block_shots)continue;
    const res=world.hitItem(it,s.dmg,0,world.tangentAt(it.u,s.vx,s.vy));
    if(res==='break'){planetSolids=null;fx_dust(o.x,o.y,5);continue;}
    fx_sparks(s.x,s.y,0xffc857,8,4,(s.z||0)*K+1.1);world.scorch(world.surfaceU(pX(o.x+(s.x-o.x)*.9),pZ(o.y+(s.y-o.y)*.9)),.5);return true;}
  return false;}
// a landed hit near scenery: the impact reaches whatever stands round the target
function planetHit(t,wv,dm){if(!PLANET||!world)return;planetBlast(t.x,t.y,t.z,40+wv*28,dm*(wv>=3?1.5:1));}
// blast at sim spot: radius px, damage; z = height (px) of the blast
function planetBlast(x,y,z,rPx,dmg){if(!PLANET||!world)return 0;let n=0;
  for(const o of nearSolids()){if((z||0)>o.h+40)continue;const d=Math.hypot(x-o.x,y-o.y)-o.r;if(d>rPx)continue;
    const k=1-.5*Math.max(0,d)/rPx;if(world.hitItem(o.it,dmg*k,0,world.tangentAt(o.it.u,o.x-x,o.y-y))==='break'){n++;fx_dust(o.x,o.y,4);}}
  if(n){planetSolids=null;shake=Math.max(shake,.35);}return n;}
/* FX and the world (Daniel 2026-11-25; World Studio 3D section "FX and the world"). Each tick fxlive.js hands over a
   fighter's live FX (fx3d.js Runner.worldFx: head / tail in scene metres on the flat plane, radius, damage):
   - moving FX (travelling ones + beams) hit the pillars / boulders / trees / crystals they pass through, once per effect
     per item, with the world's break / chip rules, and keep going (landmarks never break: a spark only);
   - a beam whose head runs low (or dives into the ground) digs a trench under it as it sweeps / travels;
   - other travelling FX skimming the ground leave a thinner, shallower furrow;
   - impact bursts (pulse) near the ground leave a crater where they burst (damage or size).
   The FX themselves are drawn bent onto the globe (fx3d.js TOON_VS + segmented cards), so they keep their height over
   the ground as they travel. */
const FX_STEP=8;   // a furrow jump longer than this (m) = a new start (teleport / new pass), not a piece
function fxSegDist(px,py,ax,ay,bx,by){const dx=bx-ax,dy=by-ay,L=dx*dx+dy*dy,t=L>1e-9?Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/L)):0;
  return [Math.hypot(ax+dx*t-px,ay+dy*t-py),t];}
function planetFx(list){if(!PLANET||!world||!list||!list.length)return;const C=WORLD_CFG.fxworld;if(!C||!C.enabled)return;
  for(const e of list){const I=e.inst;
    if(C.props&&e.moving&&e.dmg>0&&e.dmg>=C.props_min_damage)fxProps(e,I);
    if(e.prim==='beam'){if(C.beam_trench&&e.dmg>=C.beam_min_damage)fxFurrow(e,I,C.beam_low_m,Math.max(.25,Math.min(2.5,e.r*1.3*C.beam_width_pct/100)),{kind:'trench',depth:1,lip:1,debris:2});}
    else if(e.prim==='pulse'){
      if(C.impacts&&!I._wCr&&e.H.y<=C.impact_low_m&&((e.dmg>0&&e.dmg>=C.impact_min_damage)||(C.impact_min_px>0&&e.rEnd>=C.impact_min_px))){I._wCr=1;
        const rr=Math.max(.6,Math.min(4.5,e.rEnd*FX3D.U*.3))*C.impact_size_pct/100,u=world.surfaceU(e.H.x,e.H.z);
        world.crater(u,rr);world.scorch(u,rr*1.25);shake=Math.max(shake,Math.min(.6,rr*.12));}}
    else if(e.moving&&C.streaks&&e.dmg>0&&e.dmg>=C.streak_min_damage)fxFurrow(e,I,C.streak_low_m,Math.max(.15,Math.min(1.2,e.r*1.2*C.streak_width_pct/100)),{kind:'streak',depth:.55,lip:.5,debris:1});
    I._wPrev=e.H.clone();}}
// scenery the effect's path crossed this tick: beam = tail -> head, else last spot -> now (sim px)
function fxProps(e,I){const A=e.T||I._wPrev||e.H,B=e.H,ax=A.x/K+W/2,ay=A.z/K+H/2,bx=B.x/K+W/2,by=B.z/K+H/2,rp=e.r/K;
  const seen=I._wHit||(I._wHit=new Set());
  for(const o of nearSolids()){if(o.it.dead||seen.has(o.it))continue;const [d,t]=fxSegDist(o.x,o.y,ax,ay,bx,by);if(d>o.r+rp)continue;
    const z=(A.y+(B.y-A.y)*t)/K;if(z-rp>o.h)continue;seen.add(o.it);
    const hx=ax+(bx-ax)*t,hy=ay+(by-ay)*t,res=world.hitItem(o.it,e.dmg,0,world.tangentAt(o.it.u,bx-ax||o.x-ax,by-ay||o.y-ay));
    if(res==='break'){planetSolids=null;fx_dust(o.x,o.y,5);shake=Math.max(shake,.3);}
    else fx_sparks(hx,hy,0xffc857,6,4,Math.max(0,z)*K+.2);}}
// lay a trench / furrow under the effect's head while it is low: one piece from the last laid spot to here
// A beam's head can run 10+ m a tick (Puck's charged laser): the whole stretch from the last laid spot is dug, in pieces
// of at most FX_PIECE m. Pieces are square-cut and laid end to end (one seamless trench, world3d.js _bowl); the chain's
// first piece gets a rounded start cap, the newest one a rounded end cap (the old end cap is hidden as it grows on).
const FX_PIECE=4;
// lay the stretch (sx, sz) -> (ex, ez) (scene m) as pieces of a chain ch = {last (mark)} | null (= a new chain); returns ch
function digChain(ch,sx,sz,ex,ez,w,opts){const dx=ex-sx,dz=ez-sz,d=Math.hypot(dx,dz);if(d<.05)return ch;
  const n=Math.min(24,Math.ceil(d/FX_PIECE)),ux=dx/d,uz=dz/d,pl=d/n;ch=ch||{last:null,first:true};
  for(let i=0;i<n;i++){const u=world.surfaceU(sx+ux*pl*(i+.5),sz+uz*pl*(i+.5)),caps=[];if(ch.first)caps.push('start');if(i===n-1)caps.push('end');
    const mk=world.trench(u,world.tangentAt(u,dx,dz),pl,w,Object.assign({},opts,{cut:true,caps,debris:i%2?0:opts.debris}));
    if(!mk)return ch;if(ch.last&&ch.last.caps&&ch.last.caps.end)ch.last.caps.end.visible=false;ch.last=mk;ch.first=false;}
  return ch;}
function fxFurrow(e,I,low,w,opts){let G=e.H;const beam=e.prim==='beam';
  if(e.T&&e.T.y>0&&e.H.y<0)G=e.T.clone().lerp(e.H,e.T.y/(e.T.y-e.H.y));   // a beam diving into the ground: where it meets it
  if(G.y>low){I._wF=null;I._wCh=null;return;}
  let L=I._wF;
  if(!L){const S=beam&&e.T&&e.T.y<=low?e.T:G;L=I._wF={x:S.x,z:S.z};I._wCh=null;
    if(beam&&e.H.y<0)world.crater(world.surfaceU(G.x,G.z),Math.max(.6,w*1.4));}   // diving straight into the ground
  const dx=G.x-L.x,dz=G.z-L.z,d=Math.hypot(dx,dz);
  if(!beam&&d>FX_STEP){I._wF={x:G.x,z:G.z};I._wCh=null;return;}   // a jump (blink / new pass), not a furrow
  if(d<Math.max(.6,w*1.2))return;
  I._wCh=digChain(I._wCh,L.x,L.z,G.x,G.z,w,opts);
  fx_dust(G.x/K+W/2,G.z/K+H/2,beam?3:1);I._wF={x:G.x,z:G.z};}
function planetCrater(x,y,size){if(!PLANET||!world)return;world.crater(world.surfaceU(pX(x),pZ(y)),size);}
function planetScorch(x,y,size){if(!PLANET||!world)return;world.scorch(world.surfaceU(pX(x),pZ(y)),size);}
