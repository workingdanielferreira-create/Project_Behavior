'use strict';
/* Jump & flight (Daniel 2026-11-23; replaces "speed gravity", where speed set how high a fighter could fly).
   Ground fighters (every character for now):
     - R = jump. R again in the air = double jump (JUMP.maxJumps). Then gravity brings them back down.
     - F in the air = fast fall (stronger gravity, a dust ring on landing). F on the ground does nothing.
     - The AI jumps too: to reach a target in the air (double jump near the top of the first one), now and then
       to hop over an incoming attack, and after launching someone (it chases them up).
     - Snaps never lift them (a snap may go down or stay level). Launches / spikes still throw fighters up.
   Flight fighters (kit.flight, from the character's fxkit `flight: {enabled: true}`; the toggle will live in the
   future FX Studio 3D): R / F climb / descend while held, let go = stay at that height. The AI picks heights
   freely (no speed ceiling any more). Per-kit override of the numbers below: kit.jump = {any key}. */
const JUMP={h1:300,h2:240,gravity:2600,maxJumps:2,fastFall:3.2,fastVz:900,landDustVz:1100,aiCdMs:450};
function jcfg(f){return f.k.jump?Object.assign({},JUMP,f.k.jump):JUMP;}
function canFly(f){return !!f.k.flight;}
// The fighter the keyboard drives (your on-field fighter, unless watching).
function playerDriven(f){return f.side===0&&level!=='watch'&&sides[0].team[sides[0].on]===f;}
function onGround(f){return f.z<=.5&&f.vz<=0;}
function canJump(f){return !canFly(f)&&(onGround(f)||(f.jumps||0)<jcfg(f).maxJumps);}
// R pressed (or the AI decides): first jump from the ground, the second one in the air. False = not possible now.
function jumpPress(f){if(canFly(f)||f.ko||f.stun>0||f.gone>0||f.snap||f.leap>0)return false;const c=jcfg(f);
  if(onGround(f))f.jumps=0;
  if((f.jumps||0)>=c.maxJumps)return false;
  const second=(f.jumps||0)>0;f.vz=Math.sqrt(2*c.gravity*(second?c.h2:c.h1));f.jumps=(f.jumps||0)+1;f.ffall=false;f.z=Math.max(f.z,1);
  if(second){FXF=f;fx_ring(f.x,f.y,f.k.fx,1.6,.22,.4);fx_sparks(f.x,f.y,f.k.fx,8,4,.6);}else fx_dust(f.x,f.y,3);
  return true;}
// Altitude of a ground fighter (fighter.js updAltitude calls this instead of the flight code).
function groundAltitude(f,e){f.zWant=f.zWantRaw=f.z;
  if(f.snap||f.leap>0)return;
  const c=jcfg(f);
  if(f.z<=0&&f.vz<=0){f.z=0;f.vz=0;f.jumps=0;f.ffall=false;if(f.jumpAfterSnap){f.jumpAfterSnap=false;jumpPress(f);}else aiJump(f,e);return;}
  if(f.jumpAfterSnap){f.jumpAfterSnap=false;}
  aiJump(f,e);
  const ff=f.stun<=0&&(f.ffall||(playerDriven(f)&&keys.KeyF));
  if(ff&&f.vz>-c.fastVz)f.vz=-c.fastVz;
  f.vz-=c.gravity*(ff?c.fastFall:1)*DT;f.z+=f.vz*DT;
  if(f.z>ZMAX+200){f.z=ZMAX+200;f.vz=Math.min(0,f.vz);}
  if(f.z<=0){const vz=f.vz;f.z=0;
    if(vz<-1500&&f.stun>0)groundSplat(f);
    if(f.stun>0&&vz<-700){f.vz=-vz*.22;return;}   // a thrown fighter bounces once
    f.vz=0;f.jumps=0;f.ffall=false;f.landT=tick+ms2t(160);
    if(vz<-c.landDustVz){fx_dust(f.x,f.y,6);fx_ring(f.x,f.y,0x7a80a8,1.6,.25,.05);}else fx_dust(f.x,f.y,2);}}
// AI jumps (not while you drive your fighter, not for dummies that only stand / guard, not with no target).
function aiJump(f,e){
  if(playerDriven(f)&&(level==='handson'||tick<f.manualUntil))return;   // you jump yourself (Commander: the AI may, while you leave it be)
  if(f.dummy&&f.dummy.beh!=='fight'||!e||e.phantom||e.ko)return;
  if(f.stun>0||f.gone>0||f.snap||(f.act&&f.act.kind!=='normal'))return;
  const c=jcfg(f);if(tick<(f.jumpCd||0))return;
  const d=Math.hypot(f.x-e.x,f.y-e.y),it=f.tp.intent,hunt=f.k.rhythm===false||['engage','pressure','punish'].includes(it);
  const near=d<=f.k.reach*2.2+220;
  let go=false;
  if(onGround(f)){
    if(hunt&&near&&e.z>140&&!f.act)go=true;                                     // reach a target in the air
    else if(incoming(f,e)!=null&&Math.random()<.035)go=true;                     // hop over an attack
    else if(it==='neutral'&&!f.act&&Math.random()<.0015)go=true;                 // a hop now and then
  }else if((f.jumps||0)<c.maxJumps&&f.vz<220&&e.z>f.z+60&&hunt&&near)go=true;   // double jump near the top
  if(go&&jumpPress(f))f.jumpCd=tick+ms2t(c.aiCdMs);}
// A snap never lifts a ground fighter (it may go down or stay level); a flyer goes where it aims.
function snapZ(f,tz){return canFly(f)?tz:Math.min(tz,f.z);}
