'use strict';
/* Movement styles: FX Studio movement_style phases per character; the rhythm takes over in engage / pressure / punish. Intent speed table. */
// Movement styles (FX Studio movement_style phases, from each character file). Battle rule: with a style the
// style does the footwork; the rhythm intent takes over in engage / pressure / punish (COMMIT_INTENTS).
function styleTarget(f,e){const st=f.k.style;if(!st)return null;if(f.k.rhythm!==false&&['engage','pressure','punish'].includes(f.tp.intent))return null;
  const d=Math.hypot(f.x-e.x,f.y-e.y);let dx=f.x-e.x,dy=f.y-e.y;if(d<1){dx=1;dy=0;}const ux=dx/(d||1),uy=dy/(d||1);
  if(tick>=f.orbitSwap){f.orbitSwap=tick+ms2t(rnd(1500,3500));f.orbitDir=-f.orbitDir;}
  const ring=(r,lead,dir)=>{const a=Math.atan2(uy,ux)+lead*dir;return [e.x+Math.cos(a)*r,e.y+Math.sin(a)*r];};
  // real kits (realkits.js): orbit at the file's radius when close, else chase at its speed
  if(typeof st==='object'){if(st.orbit&&d<=st.orbit*1.6){const p=ring(st.orbit,.52,f.orbitDir);return [p[0],p[1],st.orbitSpd];}return [e.x+ux*Math.min(60,f.k.reach*.4),e.y+uy*Math.min(60,f.k.reach*.4),st.chaseSpd];}
  if(st==='blades'){if(d<=200){const p=ring(130,.52,f.orbitDir);return [p[0],p[1],1];}return [e.x+ux*40,e.y+uy*40,3];}
  if(st==='sueko'){if(f.hp/f.max<=.3){return [e.x+ux*860,e.y+uy*860,1.5];}if(d>=500){const p=ring(400,.52,1);return [p[0],p[1],1.5];}return [e.x+ux*38,e.y+uy*38,2];}
  return null;}
const SPEEDMUL={engage:1.75,pressure:1.15,punish:2.3,feint:1.6,reset:1.2,neutral:.55,wait:.8};
