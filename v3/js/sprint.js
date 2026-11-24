'use strict';
/* Sprint + continuous movement (Daniel 2026-11-24). Replaces the step-and-plant footwork: every fighter now moves
   continuously, its speed eased toward the wanted one (no stop-start). Three speed levels:
     Lv1 = the character's base speed.
     Lv2 = sprint, SPRINT.lv2Pct % of base (per character: fxkit `sprint.lv2_pct`).
     Lv3 = beyond sprint, only for characters with FX Studio 3D's "Lv3 speed" on (fxkit `sprint: {lv3: true, lv3_pct}`).
   Player: hold Shift = Lv2; double-tap and hold Shift = Lv3 (Lv2 for a character without Lv3); let go = Lv1.
   AI (enemies, your fighter while the AI drives it, Fight-back dummies): sprints when its move target is far while it
   closes in / chases (engage, pressure, punish, feint, reset, movement styles): Lv2 past aiLv2Px, Lv3 (if it has it)
   past aiLv3Px or when punishing. Lv2 kicks up dust, Lv3 leaves afterimages and light streaks. */
const SPRINT={lv2Pct:185,lv3Pct:300,accel:10,decel:14,tapMs:280,aiLv2Px:380,aiLv3Px:820};
function hasLv3(f){return !!(f.k.sprint&&f.k.sprint.lv3);}
function lvMul(f,lv){const s=f.k.sprint||{};if(lv>=3&&hasLv3(f))return (+s.lv3Pct||SPRINT.lv3Pct)/100;if(lv>=2)return (+s.lv2Pct||SPRINT.lv2Pct)/100;return 1;}
// Shift: held = Lv2, a second press within tapMs of letting go = Lv3 (input.js)
let shiftDown=false,shiftLast=-1e9,shiftLv=1;
function sprintKeyDown(){shiftLv=performance.now()-shiftLast<=SPRINT.tapMs?3:2;shiftDown=true;}
function sprintKeyUp(){if(shiftDown)shiftLast=performance.now();shiftDown=false;shiftLv=1;}
function playerLv(f){return shiftDown?(shiftLv>=3&&hasLv3(f)?3:2):1;}
// AI: the level for a move toward a target d px away with intent it
function aiLv(f,it,d){if(!['engage','pressure','punish','feint','reset','style'].includes(it))return 1;
  if(hasLv3(f)&&(d>SPRINT.aiLv3Px||(it==='punish'&&d>SPRINT.aiLv2Px)))return 3;return d>SPRINT.aiLv2Px?2:1;}
/* One tick of continuous movement: (mx, my) = unit direction (0, 0 = stop), speed px/s (level already applied),
   lv = speed level (effects + clip). The velocity eases toward the wanted one, so starts / stops / turns are smooth. */
function moveStep(f,mx,my,speed,lv){
  if(f.snap||f.stun>0||f.gone>0||f.mv3||f.leap>0){f.mvx=0;f.mvy=0;f.spdLv=1;return;}
  const tx=mx*speed,ty=my*speed,k=1-Math.exp(-(speed>0?SPRINT.accel:SPRINT.decel)*(lv>=3?1.6:1)*DT);
  f.mvx=(f.mvx||0)+(tx-(f.mvx||0))*k;f.mvy=(f.mvy||0)+(ty-(f.mvy||0))*k;
  if(Math.abs(f.mvx)<1&&Math.abs(f.mvy)<1&&speed<=0){f.mvx=f.mvy=0;}
  const px=f.x,py=f.y;f.x+=f.mvx*DT;f.y+=f.mvy*DT;
  const v=Math.hypot(f.mvx,f.mvy);f.spdLv=v>1?lv:1;
  f.stepT=(f.stepT+DT*Math.min(2.2,.5+v/Math.max(60,f.k.speed*1.6)))%.24;   // stand-in bodies' leg swing
  if(v<f.k.speed*1.3||f.z>10)return;
  if(lv>=3){if(tick%3===0)fx_ghost(f,px,py);if(Math.random()<.35)fx_streak(VA(px,py,f.z,1),VA(f.x,f.y,f.z,1),f.k.fx,.03);if(tick%9===0)fx_dust(f.x,f.y,2);}
  else if(lv>=2&&tick%11===0)fx_dust(f.x,f.y,1);}
