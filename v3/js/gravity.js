'use strict';
/* Speed gravity: movement speed sets how high a fighter may fly (a ceiling).
   At or below groundSpeed (2D px/s, measured from the fighter's own movement: drift, snaps, knockback; blinks /
   teleports ignored) the ceiling is the ground. Faster raises it, up to ZMAX at topSpeed (curve 1 = linear).
   Above its ceiling a fighter falls under gravity (px/s^2, accelerating) until it meets it, so a burst of speed
   lifts it and slowing down brings it back down. Below the ceiling the old altitude control still picks the
   height (AI intent heights, R / F), only capped. A snap may climb as high as its own speed allows. Launches /
   spikes (stunned, thrown) are not capped: they fly and fall as before. Settings > "Speed gravity" turns it off
   (= the old free flight). Per-kit override: kit.gravity = {any key below}. */
const GRAVITY={groundSpeed:650,topSpeed:3000,curve:1,gravity:2600,rise:.5,fall:.12,warpPx:150};
function gcfg(f){return f.k.gravity?Object.assign({},GRAVITY,f.k.gravity):GRAVITY;}
function ceilFor(f,spd){const c=gcfg(f);if(spd<=c.groundSpeed)return 0;const u=Math.min(1,(spd-c.groundSpeed)/Math.max(1,c.topSpeed-c.groundSpeed));return ZMAX*(c.curve===1?u:Math.pow(u,c.curve));}
// Once per tick (top of updAltitude): smoothed speed and the ceiling.
function gravityStep(f){const c=gcfg(f);
  if(f.gpx==null){f.gpx=f.x;f.gpy=f.y;f.gpz=f.z;f.gspd=0;}
  const dz=f.z-f.gpz,d=Math.hypot(f.x-f.gpx,f.y-f.gpy,dz>0?dz:0);f.gpx=f.x;f.gpy=f.y;f.gpz=f.z;
  if(d<=c.warpPx){const s=d/DT;f.gspd+=(s-f.gspd)*(s>f.gspd?c.rise:c.fall);}
  f.gceil=settings.gravity?ceilFor(f,f.gspd):ZMAX;return f.gceil;}
// Above the ceiling (not launched / stunned): fall. True while it falls (the caller skips its own height control).
function gravityFall(f){if(!settings.gravity||f.stun>0||f.vz>900)return false;const ceil=f.gceil==null?ZMAX:f.gceil;if(f.z<=ceil+.5)return false;
  f.vz=Math.min(f.vz,0)-gcfg(f).gravity*DT;f.z+=f.vz*DT;
  if(f.z<=ceil){const hard=f.vz<-1100;f.z=Math.max(0,ceil);f.vz=0;if(f.z<=0&&hard){fx_dust(f.x,f.y,5);fx_ring(f.x,f.y,0x7a80a8,1.6,.25,.05);}}
  return true;}
// A snap climbs no higher than its own speed allows (blinks count as top speed). Going down is always allowed.
function gravitySnapZ(f,tz,spd){if(!settings.gravity)return tz;return Math.min(tz,Math.max(f.z,ceilFor(f,spd)));}
