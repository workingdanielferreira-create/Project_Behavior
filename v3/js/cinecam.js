'use strict';
/* Cinematic camera + clear sight lines (Daniel 2026-11-26: "fighting in very condensed areas like forests ... rework how
   the camera captures the battle to make it more cinematic, and avoid all instances of potentially blocking the view of
   the battle by environmental objects"). His picks: move the camera first, then fade what still blocks + an X-ray
   silhouette; a new "Cinematic" camera mode (C cycles to it); event shots, destruction shots, composed framing and a
   spring dolly rig; a forest layout in World Studio 3D (world3d.js "Forest groves").

   SIGHT LINES (every camera mode, planet on; settings group "Sight lines"):
   - Sight rays: from the camera to each on-field fighter's feet / chest / head, tested in DRAWN (bent) space against
     every standing pillar / boulder / tree / crystal / column / landmark near the fight (planet.js planetSight: upright
     cylinders measured from each mesh, world3d.js _sightShapes; a tree = trunk + crown) and against the globe itself.
   - Move first (sightAdjust): every 0.1 s the shot's camera spot is tried swung round the look point (up to Max swing),
     raised (up to Max rise) and pulled in toward the fighters; the clearest spot wins, with a small cost for leaving
     the shot as framed and for changing the pick (no flicker). The offset eases in, so the camera glides round trees.
   - Then fade (sightFade): whatever still cuts a sight ray (also two to the space between the fighters, where their FX
     meet) or stands within 3 m of the camera (foreground clutter) dithers out to See-through
     amount (world3d.js setFade: screen-door dither, no depth write), and comes back once clear.
   - X-ray (xrayRender, after the frame): a fighter still hidden by something solid (an item that is not faded, or the
     globe's horizon) is drawn again as a flat team-coloured silhouette where it is behind (depth test "greater").

   CINEMATIC MODE (settings group "Cinematic camera"):
   - Director: base shots chosen by distance and the fight director's phase (calm / build / burst), never the same twice
     in a row, held a seeded uneven time (Shortest .. Longest shot, shorter in a burst): two-shot 3/4, over the
     shoulder (either fighter), low hero angle, high crane, slow orbit, long-lens telephoto (squeezes the forest
     together), wide. The 180-degree rule: the camera stays on one side of the line between the fighters; it crosses
     only on a cut, now and then. Each shot drifts on its own (dolly / truck). A shot change is a hard cut (Cut chance)
     or a glide on the rig.
   - Event shots (Event shots on): ultimate = low hero shot on the caster pushing in with a dutch tilt; heavy hit = crash
     zoom (fov punch, Crash zoom); launch / spike = a crane on the thrown fighter; K.O. = slow low orbit on the fallen.
     Priority K.O. > ultimate > destruction > launch. The knockback tracking shot (camera.js) also runs in this mode.
   - Destruction shot (Destruction shots on, planet): a tree / pillar / scenery piece at least Least height tall breaking
     near the fight cuts to a shot of the break with the nearest fighter in frame, plus Break slow-mo of the sim;
     more breaks during it extend it a little (a chain through a grove reads as one shot). Cooldown between two.
   - Spring dolly rig: camera spot, look point and fov ride damped springs (Camera weight, Overshoot) instead of plain
     easing, and the look point leads the fighters' movement (Look ahead), like an operator anticipating the action.
   - Composed framing: the fighters sit off centre with lead room the way they move (rule of thirds, Composed framing %),
     and a dutch tilt (up to Dutch tilt) on intense moments.
   View only: nothing here touches the sim, except the destruction shot's slow-mo (the same slowmo the K.O. uses). */
const V3c=THREE.Vector3;
let sightFrame=0;
const SIGHT_H=[.35,1.0,1.65];

/* ---------------------------------------------------------------- sight lines */
function sightFighters(){const [a,b]=onField();const out=[];for(const f of [a,b])if(f&&f.on&&!f.phantom&&out.indexOf(f)<0)out.push(f);return out;}
function sightPoints(fs){const out=[];for(const f of fs)for(const h of SIGHT_H)out.push({f,p:bendP(VA(f.x,f.y,f.z,h))});
  // the space between two fighters (where their FX clash) counts too
  if(fs.length===2){const a=fs[0],b=fs[1];for(const h of [1.0,2.2])out.push({f:null,p:bendP(VA((a.x+b.x)/2,(a.y+b.y)/2,(a.z+b.z)/2,h))});}
  return out;}
const SIGHT_NEAR_M=3;   // anything this close to the camera fades too (foreground clutter)
// segment c -> t (drawn space) against one item's sight shapes: true = blocked
function sightRayItem(c,t,S){const B=S.B,n=S.n,e1=S.e1,e2=S.e2,s=S.s;
  const ax=c.x-B.x,ay=c.y-B.y,az=c.z-B.z,bx=t.x-B.x,by=t.y-B.y,bz=t.z-B.z;
  const cx=ax*e1.x+ay*e1.y+az*e1.z,cy=ax*n.x+ay*n.y+az*n.z,cz=ax*e2.x+ay*e2.y+az*e2.z;
  const tx=bx*e1.x+by*e1.y+bz*e1.z,ty=bx*n.x+by*n.y+bz*n.z,tz=bx*e2.x+by*e2.y+bz*e2.z;
  for(const sh of S.it.sight){const r=sh.r*s,y0=sh.y0*s,y1=sh.y1*s;const dx=tx-cx,dz=tz-cz,A=dx*dx+dz*dz;let t0,t1;
    if(A<1e-9){if(cx*cx+cz*cz>=r*r)continue;t0=0;t1=1;}
    else{const Bq=2*(cx*dx+cz*dz),C=cx*cx+cz*cz-r*r,D=Bq*Bq-4*A*C;if(D<=0)continue;const q=Math.sqrt(D);t0=(-Bq-q)/(2*A);t1=(-Bq+q)/(2*A);}
    t0=Math.max(0,t0);t1=Math.min(1,t1);if(t0>=t1)continue;
    const ya=cy+(ty-cy)*t0,yb=cy+(ty-cy)*t1;if(Math.max(ya,yb)<y0||Math.min(ya,yb)>y1)continue;return true;}
  return false;}
// is drawn point c inside (or within m of) an item's shapes (the camera standing in a tree's crown)?
function sightInside(c,S,m){const B=S.B,s=S.s,ax=c.x-B.x,ay=c.y-B.y,az=c.z-B.z;
  const x=ax*S.e1.x+ay*S.e1.y+az*S.e1.z,y=ax*S.n.x+ay*S.n.y+az*S.n.z,z=ax*S.e2.x+ay*S.e2.y+az*S.e2.z;
  for(const sh of S.it.sight){const r=sh.r*s+m;if(x*x+z*z<r*r&&y>sh.y0*s-m&&y<sh.y1*s+m)return true;}return false;}
// the globe hides t from c (the horizon): the segment dips under the ground
function sightRayGlobe(c,t){if(!PLANET||!world)return false;const R=world.R,ox=world.A.x,oy=-R,oz=world.A.z;
  const dx=t.x-c.x,dy=t.y-c.y,dz=t.z-c.z,L=dx*dx+dy*dy+dz*dz;if(L<1e-9)return false;
  const u=Math.max(0,Math.min(1,((ox-c.x)*dx+(oy-c.y)*dy+(oz-c.z)*dz)/L));
  return Math.hypot(c.x+dx*u-ox,c.y+dy*u-oy,c.z+dz*u-oz)<R-.25;}
function sightExtent(S){let e=0;for(const sh of S.it.sight)e=Math.max(e,sh.r+sh.y1);return e*S.s;}
// the items that could stand between c and the points (rough sphere test first)
function sightNear(L,c,pts){if(!pts.length)return [];let mx=0,my=0,mz=0;pts.forEach(o=>{mx+=o.p.x;my+=o.p.y;mz+=o.p.z;});mx/=pts.length;my/=pts.length;mz/=pts.length;
  const cx=(c.x+mx)/2,cy=(c.y+my)/2,cz=(c.z+mz)/2;let rad=Math.hypot(c.x-mx,c.y-my,c.z-mz)/2;pts.forEach(o=>{rad=Math.max(rad,Math.hypot(o.p.x-cx,o.p.y-cy,o.p.z-cz));});
  return L.filter(S=>{if(S.ext==null)S.ext=sightExtent(S);return Math.hypot(S.B.x-cx,S.B.y-cy,S.B.z-cz)<rad+S.ext+1;});}
// share of sight rays from drawn spot c that something blocks (items + the globe)
function sightBlocked(c,pts,L){if(!pts.length)return 0;const near=sightNear(L,c,pts);let n=0;
  for(const o of pts){if(sightRayGlobe(c,o.p)){n++;continue;}for(const S of near)if(sightRayItem(c,o.p,S)||sightInside(c,S,.3)){n++;break;}}
  return n/pts.length;}

const sight={y:0,r:0,p:0,cy:0,cr:0,cp:0,next:0,faded:new Set(),xr:[false,false]};
// the camera spot tgt (flat) turned yaw round the look point, raised, pulled in toward it
function sightOff(tgt,look,yaw,raise,pull){const dx=tgt.x-look.x,dz=tgt.z-look.z,c=Math.cos(yaw),s=Math.sin(yaw),k=1-pull;
  const o=new V3c(look.x+(dx*c-dz*s)*k,look.y+(tgt.y+raise-look.y)*k,look.z+(dx*s+dz*c)*k);if(o.y<.4)o.y=.4;return o;}
const SIGHT_YAWS=[0,.2,-.2,.4,-.4,.6,-.6,.85,-.85,1.1,-1.1,1.4,-1.4],SIGHT_PULLS=[0,.3,.55];
function sightAdjust(tgt,look,rdt,snap){
  if(!PLANET||!world||!settings.sightMove){sight.y=sight.r=sight.p=0;const k=1-Math.exp(-4*rdt);sight.cy+=(0-sight.cy)*k;sight.cr+=(0-sight.cr)*k;sight.cp+=(0-sight.cp)*k;
    return (Math.abs(sight.cy)+Math.abs(sight.cr)+Math.abs(sight.cp))>1e-3?sightOff(tgt,look,sight.cy,sight.cr,sight.cp):tgt;}
  const now=performance.now()/1000;
  if(snap||now>=sight.next){sight.next=now+.1;
    const pts=sightPoints(sightFighters()),L=planetSight(90,sightFrame);
    const maxY=Math.max(0,settings.sightMaxDeg)*Math.PI/180,maxR=Math.max(0,settings.sightRaise);
    const base=sightBlocked(bendP(tgt),pts,L);
    if(base===0&&!sight.y&&!sight.r&&!sight.p){}   // clear as framed: stay
    else{let best=null,bs=1e9;const raises=maxR>0?[0,maxR*.5,maxR]:[0];
      for(const yaw of SIGHT_YAWS){if(Math.abs(yaw)>maxY+1e-6)continue;
        for(const raise of raises)for(const pull of SIGHT_PULLS){
          const c=sightOff(tgt,look,yaw,raise,pull);const k=yaw===0&&raise===0&&pull===0?base:sightBlocked(bendP(c),pts,L);
          const sc=k*10+(maxY>0?Math.abs(yaw)/maxY:0)*1.2+(maxR>0?raise/maxR:0)+pull*1.6
            +(Math.abs(yaw-sight.y)+(maxR>0?Math.abs(raise-sight.r)/maxR:0)+Math.abs(pull-sight.p))*.6;
          if(sc<bs){bs=sc;best=[yaw,raise,pull];}}}
      if(best){sight.y=best[0];sight.r=best[1];sight.p=best[2];}}}
  const k=snap?1:1-Math.exp(-3.2*rdt);sight.cy+=(sight.y-sight.cy)*k;sight.cr+=(sight.r-sight.cr)*k;sight.cp+=(sight.p-sight.cp)*k;
  return sightOff(tgt,look,sight.cy,sight.cr,sight.cp);}
// after the camera is placed (drawn space): fade what still blocks, decide who needs the X-ray
function sightFade(rdt){sight.xr[0]=sight.xr[1]=false;if(!PLANET||!world){return;}
  const c=cam.position,fs=sightFighters(),pts=sightPoints(fs),L=planetSight(90,sightFrame),near=sightNear(L,c,pts);
  const want=new Map(),fadeOn=settings.sightFade,lo=Math.max(0,Math.min(1,settings.sightFadePct/100));
  for(const S of near){let hit=sightInside(c,S,SIGHT_NEAR_M);if(!hit)for(const o of pts)if(sightRayItem(c,o.p,S)){hit=true;break;}if(hit&&fadeOn)want.set(S.it,lo);}
  for(const [it] of want)sight.faded.add(it);
  for(const it of Array.from(sight.faded)){const tg=want.has(it)?want.get(it):1;if(it._fk==null)it._fk=1;
    it._fk=tg<it._fk?Math.max(tg,it._fk-rdt*12):Math.min(tg,it._fk+rdt*5);
    if(it.dead){it._fk=1;sight.faded.delete(it);continue;}
    world.setFade(it,it._fk);if(it._fk>=.999&&!want.has(it))sight.faded.delete(it);}
  // X-ray: a fighter still hidden by something solid (not faded) or the horizon
  if(!settings.xrayOn)return;
  for(const o of pts){if(!o.f||sight.xr[o.f.side])continue;if(sightRayGlobe(c,o.p)){sight.xr[o.f.side]=true;continue;}
    for(const S of near)if((S.it._fk==null||S.it._fk>.6)&&sightRayItem(c,o.p,S)){sight.xr[o.f.side]=true;break;}}}
function sightClear(){for(const it of sight.faded){it._fk=1;if(world)world.setFade(it,1);}sight.faded.clear();sight.y=sight.r=sight.p=sight.cy=sight.cr=sight.cp=0;sight.xr[0]=sight.xr[1]=false;}

/* ---------------------------------------------------------------- X-ray silhouettes */
const XRAY_COL=[0x6fd8ff,0xff5a6e];
const xrayMat=new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:.55,depthWrite:false,depthFunc:THREE.GreaterDepth,skinning:true,fog:false});
function xrayTag(f){if(f._xrG===f.g)return;f._xrG=f.g;const L=1+f.side;
  f.g.traverse(o=>{const m=o.material;if(!o.isMesh||!m||Array.isArray(m))return;if(m.side===THREE.BackSide||m.transparent||m.blending!==THREE.NormalBlending)return;o.layers.enable(L);});}
function xrayRender(){if(!running||ended||!settings.xrayOn||!(sight.xr[0]||sight.xr[1]))return;
  const fs=sightFighters();fs.forEach(xrayTag);
  const ac=renderer.autoClear,bg=scene.background;renderer.autoClear=false;scene.background=null;scene.overrideMaterial=xrayMat;xrayMat.opacity=Math.max(.05,Math.min(1,settings.xrayPct/100));
  try{for(let s=0;s<2;s++){if(!sight.xr[s])continue;xrayMat.color.setHex(XRAY_COL[s]);cam.layers.set(1+s);renderer.render(scene,cam);}}
  finally{cam.layers.set(0);scene.overrideMaterial=null;scene.background=bg;renderer.autoClear=ac;}}

/* ---------------------------------------------------------------- cinematic director + rig */
const cine={on:false,shot:null,ev:null,side:1,last:'',p:new V3c(),v:new V3c(),l:new V3c(),lv:new V3c(),fov:50,fv:0,roll:0,zoom:0,zoomHold:0,kick:0,nx:0,ny:0,
  mid:null,mv:new V3c(),breakNext:0,want:{p:new V3c(),l:new V3c(),fov:50,roll:0}};
const EV_PRI={ko:4,ult:3,break:2,launch:1};
function cineReset(){cine.on=false;cine.shot=null;cine.ev=null;cine.zoom=0;cine.kick=0;cine.mid=null;}
function cineNow(){return performance.now()/1000;}
// pick the next base shot
function cineShot(sep,first){const ph=director.phase,burst=ph==='burst',I=director.I||0;
  const W=sep>22?{wide:3,tele:2,high:2,two:1.2,orbit:.6}:{two:3,ots:2.4,low:1.4+(burst?1.4:0),high:1.1,orbit:1.1+(burst?2:0),tele:1.3,wide:.4};
  delete W[cine.last];let tot=0;for(const k in W)tot+=W[k];let r=Math.random()*tot,kind='two';for(const k in W){r-=W[k];if(r<=0){kind=k;break;}}
  const lo=Math.max(.5,settings.cineShotMin),hi=Math.max(lo,settings.cineShotMax),dur=rnd(lo,hi)*(burst?.55:ph==='build'?.8:1);
  const cutK=first||Math.random()*100<settings.cineCutPct;
  if(cutK&&Math.random()<.15)cine.side*=-1;   // cross the line only on a cut, now and then (180-degree rule)
  const dz=settings.cineDutch*Math.PI/180;
  cine.last=kind;
  return {kind,t0:cineNow(),until:cineNow()+dur,cut:cutK,fb:Math.random()<.5?1:-1,subj:Math.random()<.5?0:1,dk:rnd(.85,1.2),hk:rnd(.7,1.4),
    dolly:rnd(-.025,.06),truck:rnd(-.06,.06),orbitW:rnd(.18,.42)*(Math.random()<.5?1:-1),th0:rnd(-.6,.6),
    roll:(kind==='low'||kind==='orbit'||burst)?(Math.random()<.5?-1:1)*dz*rnd(.35,1)*(.4+.6*I):0};}
// where the current shot wants the camera: writes cine.want
function cinePose(S,ctx,age){const {pa,pb,mid,dir,right,sep}=ctx,W=cine.want,side=cine.side,up=new V3c(0,1,0);let p,l,fov=50;
  const k=S.kind;
  if(k==='two'){const d=(4.2+sep*.55)*S.dk;p=mid.clone().addScaledVector(right,side*d*.87).addScaledVector(dir,-S.fb*d*.42);p.y=mid.y+1.1+sep*.08*S.hk;l=mid.clone().addScaledVector(up,.75);fov=50;}
  else if(k==='ots'){const A=S.subj?pb:pa,B=S.subj?pa:pb,dd=B.clone().sub(A);dd.y=0;if(dd.lengthSq()<1e-4)dd.copy(dir);dd.normalize();
    const back=3.2+sep*.22;p=A.clone().addScaledVector(dd,-back).addScaledVector(right,side*(1.25+sep*.05));p.y=A.y+.9+sep*.08;l=A.clone().lerp(B,.62).addScaledVector(up,.3);fov=46;}
  else if(k==='low'){p=mid.clone().addScaledVector(right,side*(3.2+sep*.42)*S.dk).addScaledVector(dir,-S.fb*1.6);p.y=Math.max(.75,Math.min(pa.y,pb.y)-.45);l=mid.clone().addScaledVector(up,1.25);fov=60;}   // low, but above crater lips
  else if(k==='high'){p=mid.clone().addScaledVector(right,side*(5+sep*.4)).addScaledVector(dir,-S.fb*3);p.y=mid.y+(7+sep*.35)*S.hk;l=mid.clone();fov=52;}
  else if(k==='orbit'){const th=S.th0+S.orbitW*age,c=Math.cos(th),s=Math.sin(th),r=(5+sep*.55)*S.dk;
    const off=new V3c(right.x*c-right.z*s,0,right.x*s+right.z*c).multiplyScalar(side*r);p=mid.clone().add(off);p.y=mid.y+1.4+sep*.1;l=mid.clone().addScaledVector(up,.7);fov=50;}
  else if(k==='tele'){const d=(16+sep*1.1)*S.dk;p=mid.clone().addScaledVector(right,side*d).addScaledVector(dir,-S.fb*d*.25);p.y=mid.y+2.2*S.hk;l=mid.clone().addScaledVector(up,.7);
    fov=Math.max(14,Math.min(40,2*Math.atan((sep*.62+2.4)/d)*180/Math.PI));}
  else{p=mid.clone().addScaledVector(right,side*(9+sep*.5)).addScaledVector(dir,-S.fb*(6+sep*.3));p.y=mid.y+8+sep*.3;l=mid.clone();fov=54;}   // wide
  // the shot's own drift: dolly in / out, truck round the look point
  const dl=Math.max(.6,1-S.dolly*age),tr=S.truck*age,dx=p.x-l.x,dz=p.z-l.z,c=Math.cos(tr),s=Math.sin(tr);
  p.set(l.x+(dx*c-dz*s)*dl,l.y+(p.y-l.y)*dl,l.z+(dx*s+dz*c)*dl);
  W.p.copy(p);W.l.copy(l);W.fov=fov;W.roll=S.roll;}
// event shot poses (fighter-based)
function cineEvPose(E,ctx,age){const W=cine.want,side=cine.side,up=new V3c(0,1,0),u=Math.min(1,age/Math.max(.1,E.until-E.t0));
  if(E.kind==='ult'||E.kind==='launch'||E.kind==='ko'){const f=E.f;const P=VA(f.x,f.y,f.z,0);
    if(E.kind==='ult'){const fd=new V3c(Math.cos(f.face),0,Math.sin(f.face)),pr=new V3c(-fd.z,0,fd.x);const d=2.9*(1-.2*u);
      W.p.copy(P).addScaledVector(fd,d).addScaledVector(pr,side*1.4);W.p.y=P.y+.75;W.l.copy(P).addScaledVector(up,1.45).addScaledVector(fd,.2);W.fov=52;W.roll=side*settings.cineDutch*.8*Math.PI/180;}
    else if(E.kind==='launch'){const o=ctx.pa.distanceToSquared(P)<ctx.pb.distanceToSquared(P)?ctx.pb:ctx.pa;const ln=P.clone().sub(o);ln.y=0;if(ln.lengthSq()<1e-4)ln.copy(ctx.dir);ln.normalize();
      const pr=new V3c(-ln.z,0,ln.x);W.p.copy(P).addScaledVector(pr,side*(6.5+P.y*.4)).addScaledVector(ln,-2);W.p.y=Math.max(.6,P.y*.45+.8);W.l.copy(P).addScaledVector(up,1);W.fov=54;W.roll=0;}
    else{const th=E.th0+.35*age,r=4.2;W.p.set(P.x+Math.cos(th)*r,P.y+.9,P.z+Math.sin(th)*r);W.l.copy(P).addScaledVector(up,.6);W.fov=48;W.roll=side*settings.cineDutch*.5*Math.PI/180;}
    return;}
  if(E.kind==='break'){const P=E.at,F=ctx.pa.distanceToSquared(P)<ctx.pb.distanceToSquared(P)?ctx.pa:ctx.pb;const ln=F.clone().sub(P);ln.y=0;const dl=Math.max(.5,ln.length());ln.divideScalar(dl);
    const pr=new V3c(-ln.z,0,ln.x).multiplyScalar(side),look=P.clone().lerp(F,.35);look.y=Math.max(.6,E.h*.4);const d=(6+E.h*.8+dl*.4)*(1-.1*u);
    W.p.copy(look).addScaledVector(pr,d*.9).addScaledVector(ln,-d*.35);W.p.y=look.y+1.2;W.l.copy(look);W.fov=54;W.roll=0;}}
// combat.js / camera.js events in this mode
function cineEvent(kind,f,by){if(!running||ended)return;
  if(kind==='heavy'){cine.zoom=Math.max(cine.zoom,Math.max(0,settings.cineCrash)/100);cine.zoomHold=cineNow()+.07;cine.kick=(Math.random()<.5?-1:1)*Math.min(4,settings.cineDutch*.4)*Math.PI/180;return;}
  if(!settings.cineEvents||!f||!EV_PRI[kind])return;cineStartEv({kind,f,th0:Math.random()*TAU},kind==='ult'?1.9:kind==='ko'?2.6:1.4);}
function cineStartEv(E,dur){const now=cineNow(),cur=cine.ev;
  if(cur&&now<cur.until&&EV_PRI[cur.kind]>EV_PRI[E.kind])return false;
  E.t0=now;E.until=now+dur;E.cut=E.kind!=='launch';cine.ev=E;if(E.cut)cine.cutNow=true;return true;}
// world3d.js breakItem -> planet.js: a tree / pillar / scenery piece broke
function camBreak(it){if(!running||ended||camMode!=='cinematic'||lockTarget()||!settings.cineBreakOn||!world)return;
  const h=(it.height||0)*(it.mesh.scale.y||1);if(h<settings.cineBreakMinM)return;
  const p=world.flatOf(it.u);let dn=1e9;for(const f of sightFighters())dn=Math.min(dn,Math.hypot(p.x-pX(f.x),p.z-pZ(f.y)));
  if(dn>12)return;   // not next to a fighter: not worth a cut
  const now=cineNow(),cur=cine.ev;
  if(cur&&cur.kind==='break'&&now<cur.until){cur.until=Math.min(cur.t0+Math.max(settings.cineBreakS,.3)*1.9,cur.until+.35);return;}   // a chain through a grove: one shot
  if(now<cine.breakNext)return;
  if(cineStartEv({kind:'break',at:new V3c(p.x,0,p.z),h},Math.max(.3,settings.cineBreakS))){cine.breakNext=now+settings.cineBreakCdS;
    if(settings.cineBreakSlowMs>0)slowmo=Math.max(slowmo,ms2t(settings.cineBreakSlowMs));}}
// damped spring (semi-implicit), w = stiffness (rad/s), z = damping ratio
function cineSpring(p,v,t,w,z,dt){const n=Math.max(1,Math.ceil(dt/.0167));const h=dt/n;
  for(let i=0;i<n;i++){v.x+=(w*w*(t.x-p.x)-2*z*w*v.x)*h;v.y+=(w*w*(t.y-p.y)-2*z*w*v.y)*h;v.z+=(w*w*(t.z-p.z)-2*z*w*v.z)*h;p.addScaledVector(v,h);}}
function cineStep(rdt,a,b,pa,pb,sep){const now=cineNow();
  const mid=pa.clone().lerp(pb,.5),dir=pb.clone().sub(pa);dir.y=0;if(dir.lengthSq()<1e-4)dir.set(0,0,-1);dir.normalize();const right=new V3c(-dir.z,0,dir.x);
  // the fighters' movement (smoothed), for the lead room and the look ahead
  if(cine.mid&&rdt>0){const mv=mid.clone().sub(cine.mid).divideScalar(rdt);if(mv.length()<40)cine.mv.lerp(mv,1-Math.exp(-5*rdt));}cine.mid=mid.clone();
  const ctx={pa,pb,mid,dir,right,sep};let first=false;
  if(!cine.on){cine.on=true;first=true;cine.side=Math.random()<.5?1:-1;cine.shot=null;cine.ev=null;}
  if(cine.ev&&now>=cine.ev.until){cine.ev=null;cine.shot=cineShot(sep,false);cine.shot.cut=false;}   // glide out of an event shot
  if(!cine.shot||now>=cine.shot.until){cine.shot=cineShot(sep,first);if(cine.shot.cut)cine.cutNow=true;}
  const E=cine.ev;if(E&&E.f&&(!E.f.on||E.f.phantom))cine.ev=null;
  if(cine.ev)cineEvPose(cine.ev,ctx,now-cine.ev.t0);else cinePose(cine.shot,ctx,now-cine.shot.t0);
  const W=cine.want;
  // look ahead along the fighters' movement
  const lead=Math.max(0,settings.cineLeadMs)/1000,la=cine.mv.clone().multiplyScalar(lead);la.y=0;if(la.length()>2.2)la.setLength(2.2);W.l.add(la);
  const cutNow=!!cine.cutNow||(PLANET&&planetWrapped);if(PLANET&&planetWrapped)planetWrapped=false;cine.cutNow=false;
  if(W.p.y<.3)W.p.y=.3;
  const tgt=sightAdjust(W.p,W.l,rdt,cutNow);
  if(cutNow||first){cine.p.copy(tgt);cine.v.set(0,0,0);cine.l.copy(W.l);cine.lv.set(0,0,0);cine.fov=W.fov;cine.fv=0;cine.roll=W.roll;}
  else{const fe=cine.ev&&cine.ev.f?1.8:1;   // a shot on one fighter (ultimate / launch / K.O.) keeps up with it
    const w=(1.5+Math.max(0,Math.min(100,settings.cineWeight))/100*6)*fe,z=Math.max(.3,Math.min(1.2,settings.cineDamp/100));
    cineSpring(cine.p,cine.v,tgt,w,z,rdt);cineSpring(cine.l,cine.lv,W.l,w*1.8,Math.max(z,.75),rdt);
    cine.fv+=(w*w*(W.fov-cine.fov)-2*z*w*cine.fv)*rdt;cine.fov+=cine.fv*rdt;cine.roll+=(W.roll-cine.roll)*(1-Math.exp(-3*rdt));}
  camPos.copy(cine.p);camLook.copy(cine.l);camBaseFov=Math.max(10,Math.min(80,cine.fov));}
// after the camera looks at its point (and the planet bend): fov, crash zoom, composed framing, dutch tilt
function cineFinish(rdt,sep){const now=cineNow();
  if(now>cine.zoomHold)cine.zoom*=Math.exp(-3.2*rdt);cine.kick*=Math.exp(-4*rdt);
  const fov=camBaseFov*(1-Math.min(.6,cine.zoom));if(Math.abs(cam.fov-fov)>1e-3){cam.fov=fov;cam.updateProjectionMatrix();}
  // lead room: the fighters sit behind centre, the space opens the way they move (rule of thirds), a touch above centre
  const R=new V3c(1,0,0).applyQuaternion(cam.quaternion),vr=cine.mv.dot(R),str=Math.max(0,settings.cineFrame)/100;
  const ev=cine.ev&&(cine.ev.kind==='ult'||cine.ev.kind==='ko');
  const nxT=ev?0:-Math.sign(vr)*Math.min(1,Math.abs(vr)/4)*.3*str*Math.max(0,1-sep/24),nyT=ev?0:.07*str;
  const k=1-Math.exp(-2.5*rdt);cine.nx+=(nxT-cine.nx)*k;cine.ny+=(nyT-cine.ny)*k;
  const tv=Math.tan(cam.fov*Math.PI/360),th=tv*cam.aspect;
  cam.rotateY(Math.atan(cine.nx*th));cam.rotateX(-Math.atan(cine.ny*tv));cam.rotateZ(cine.roll+cine.kick);}
