'use strict';
/* Knockback combos + lock-on (Daniel 2026-11-26; Battle + Training, you and the AI).
   Combos: a fighter still in the stun a landed hit left is "juggled" (f.cmbN = hits in the combo so far). While juggled:
     - every hit REDIRECTS the flight: the old knockback is dropped and the new hit's push (direction + strength) replaces
       it, so a light hit holds the target near you and a heavy one throws it the new way (combat.js damage());
     - every hit re-stuns it (light hits too) and an airborne target gets a juggle lift (settings.comboLift);
     - decay: each hit already in the combo cuts damage and stun by settings.comboDecayPct %;
     - cap: the settings.comboCap-th hit still lands, then the target breaks free: invulnerable until its stun ends
       + settings.comboBreakMs;
     - reach: melee hits / the attack reach check reach settings.comboReachPct % further on a juggled target.
   Auto chase (settings.comboChase, default OFF): after a hit that knocks the target back, a melee attacker snaps after it
   (to the spot in front of where it will be). With it off, your Space snap (no WASD) catches a flying target in front.
   Lock-on (T or middle mouse, your fighter only): locks onto the on-field enemy (Training: the dummy nearest when you
   press it, kept until you release / it goes); WASD is relative to the line to it (W in, S out, A / D circle it), the
   camera holds the over-the-shoulder shot on it (no dynamic cuts / wide; tracking shot only if settings.lockTrack), and
   attacks home in: J (and K / L / I for melee kits) snap to it first when it is out of reach (up to settings.lockHomePx). */

/* ---- combos ---- */
function comboJuggled(t){return !!(settings.comboOn&&t&&!t.ko&&t.stun>0&&t.cmbN>0);}
function comboReach(t){return comboJuggled(t)?1+settings.comboReachPct/100:1;}
// damage / stun kept after n hits already in the combo
function comboKeep(t){return Math.max(.1,1-settings.comboDecayPct/100*(t.cmbN||0));}
// the spot in front of where the flying target will be in lead s, on the attacker's side, at about half its reach
function comboFront(a,t,lead){const px=t.x+t.vx*lead,py=t.y+t.vy*lead;let dx=a.x-px,dy=a.y-py;const d=Math.hypot(dx,dy)||1;dx/=d;dy/=d;
  const r=Math.min(d,(a.k.reach||120)*.55);return [px+dx*r,py+dy*r];}
// damage(), before the hit is applied: start a fresh count once the old stun is over. Returns whether it is a combo hit.
function comboBefore(t){if(!(t.stun>0))t.cmbN=0;const jug=comboJuggled(t);if(jug){t.vx=0;t.vy=0;}return jug;}   // redirect: the old flight is dropped
// damage(), after the knockback: re-stun / lift / decay / cap on a combo hit, count it, auto chase.
// st0 / vz0 = the target's stun / vz just before this hit's knockback, wv = hit weight 1..4.
function comboAfter(a,t,jug,wv,st0,vz0){if(!settings.comboOn||t.ko)return;
  if(jug){const keep=comboKeep(t);
    if(t.stun===st0)stun(t,[0,260,320,600,850][wv]||260,t.z>25?'air':'stag');   // light / armoured hits re-stun a juggled target
    t.stun=Math.max(ms2t(90),Math.round(t.stun*keep));
    if(t.z>25&&t.vz===vz0){t.vz=settings.comboLift*keep;if(t.stunKind==='stag')t.stunKind='air';}   // air juggle: a small lift, less each hit
    t.cmbN++;
    if((a.side===0||t.side===0)&&!training&&t.cmbN>=3)callout(t.cmbN+' HIT','combo','#ffc857',.35,true);
    if(t.cmbN>=settings.comboCap){t.cmbN=0;t.iframe=Math.max(t.iframe,t.stun+ms2t(settings.comboBreakMs));fx_ring(t.x,t.y,0xffffff,2.2,.3,1);
      if(a.side===0||t.side===0)callout('BREAK FREE',t.k.name+' escapes the combo','#8fd3ff',.5,true);return;}}
  else if(t.stun>0)t.cmbN=1;   // the opener
  if(settings.comboChase&&t.stun>0&&a.k.melee&&!(a.side===0&&level==='handson')&&Math.hypot(t.vx,t.vy)>300)
    later(settings.comboChaseMs,()=>{if(a.ko||!a.on||a.stun>0||!comboJuggled(t))return;
      if(Math.hypot(a.x-t.x,a.y-t.y)<=(a.k.reach||120)*.9)return;
      const p=comboFront(a,t,.1);a.snapCd=0;if(snapTo(a,p[0],p[1],Math.random()<a.k.blink,true,t.z)){a.gapUntil=0;if(a.k.rhythm!==false)enter(a,'punish');}});}

/* ---- lock-on ---- */
let lockOn=false,lockT=null;
function lockPlayer(){return sides[0].team[sides[0].on];}
// the locked fighter, or null (released when it is gone)
function lockTarget(){if(!lockOn)return null;const p=lockPlayer();if(!p||p.ko){lockRelease();return null;}
  if(training){if(!lockT||lockT.phantom||!sides[1].team.includes(lockT)){lockRelease();return null;}return lockT;}
  const e=enemyOf(p);return e&&!e.ko&&e.on?e:null;}   // Battle: whoever is on the field (follows tag-ins)
function lockToggle(){if(lockOn){lockRelease();callout('LOCK OFF','','#9aa1bd',.35,true);return;}
  const p=lockPlayer();if(!p||p.ko)return;
  if(training){let bd=1e18;lockT=null;for(const d of sides[1].team){if(d.phantom)continue;const dd=Math.hypot(d.x-p.x,d.y-p.y,d.z-p.z);if(dd<bd){bd=dd;lockT=d;}}if(!lockT){deny('KeyT');return;}}
  else lockT=enemyOf(p);
  lockOn=true;callout('LOCK ON',lockT.k.name,'#ffc857',.4,true);}
function lockRelease(){lockOn=false;lockT=null;if(lockRing)lockRing.visible=false;}
// training.js trainPickTarget: the locked dummy stays your target
function lockPinTraining(){if(!lockOn||!lockT)return false;const i=sides[1].team.indexOf(lockT);if(i<0||lockT.phantom){lockRelease();return false;}sides[1].on=i;return true;}
// input.js readDir: WASD relative to the line to the locked target (forward, right)
function lockAxes(){const t=lockTarget(),p=lockPlayer();if(!t||!p)return null;const dx=t.x-p.x,dy=t.y-p.y,l=Math.hypot(dx,dy);if(l<1)return null;const F=[dx/l,dy/l];return [F,[-F[1],F[0]]];}
// input.js, an attack key (not a retry): out of reach -> snap in to it first; true = a snap started (the key is buffered)
function lockHome(f,e,melee){const t=lockTarget();if(!t||t!==e||!melee||f.stun>0||f.gone>0||f.snap)return false;
  const d=Math.hypot(e.x-f.x,e.y-f.y);if(d<=(f.k.reach||120)*.9||d>settings.lockHomePx)return false;
  const p=comboJuggled(e)?comboFront(f,e,.1):(()=>{const a=Math.atan2(f.y-e.y,f.x-e.x),r=(f.k.reach||120)*.5;return [e.x+Math.cos(a)*r,e.y+Math.sin(a)*r];})();
  if(f.act&&f.act.kind!=='normal')return false;if(f.act)endAct(f);
  f.snapCd=0;return snapTo(f,p[0],p[1],Math.random()<Math.max(.3,f.k.blink),true,e.z);}
// camera.js: the shot mode / whether the tracking shot may run
function lockCamMode(mode){return lockTarget()?'shoulder':mode;}
function lockBlocksTrack(){return !!(lockOn&&!settings.lockTrack);}
// render frame (main.js): a ring under the locked target
let lockRing=null;
function lockDraw(){const t=running&&!ended?lockTarget():null;
  if(!t||t.gone>0){if(lockRing)lockRing.visible=false;return;}
  if(!lockRing){lockRing=new THREE.Mesh(new THREE.RingGeometry(.62,.78,40),add(0xffc857,.85));lockRing.rotation.x=-Math.PI/2;lockRing.renderOrder=5;scene.add(lockRing);}
  const p=VA(t.x,t.y,t.z,0);lockRing.position.set(p.x,.04,p.z);lockRing.scale.setScalar(1+.08*Math.sin(performance.now()/140));lockRing.visible=true;}
