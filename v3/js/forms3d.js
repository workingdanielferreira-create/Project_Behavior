'use strict';
/* Transformations (Daniel 2026-11-27): real kits with FX Studio 3D Transformations (`transform3d.forms`, realkits.js ->
   k.forms3d + k.tform1..N). Forms step UP one at a time: base (0) -> Form 1 -> Form 2 ... The change into form i plays its
   own action (transform for Form 1, transform_i for Form i, else transform) and the form takes over when that action ends
   (cut short too, unless K.O.'d). Triggers: the action's own conditions (AI, combat.js realTriggers -> fireTrigger) or the
   G key (your fighter; ignores conditions, keeps the action's cooldown). At the last form nothing steps up any more.
   A form with lasts_ms > 0 drops back ONE form when it runs out (that lower form's own timer then starts).
   In a form: speed / damage / damage taken x the form's %, actions with `in_forms` not listing it can't start, and the
   body plays `<clip>@<form>` (e.g. idle@1) where the character has one (glbody.js). */
function formReady(f){const K=f.k.forms3d;if(!K||f.ko)return 0;const i=(f.form3||0)+1;if(i>K.length||f.tfPending)return 0;
  const d=f.k['tform'+i];if(!d)return 0;if((f.cds['tform'+i]||0)>tick)return 0;return i;}
function formStart(f,i,byKey){const d=f.k['tform'+i];if(!d)return false;if(f.act)endAct(f);
  startAct(f,d,'transform','transform');f.tfPending=i;f.cds['tform'+i]=tick+ms2t(d.mcd||0);
  const st=f.trig['tform'+i]||(f.trig['tform'+i]={});st.last=tick;st.fired=tick;if(byKey)stats.pSkills++;
  if(f.on)callout('TRANSFORM',f.k.name+' → '+d.name,cssc(f.k.fx),.8);return true;}
// your G key: the next form if it is ready and the fighter is free (or only in a normal attack)
function formPress(f){const i=formReady(f);if(!i||f.stun>0||f.gone>0||f.snap||(f.act&&f.act.kind!=='normal'))return false;return formStart(f,i,true);}
function formApply(f,n,drop){const K=f.k.forms3d||[];n=clamp(n,0,K.length);const F=n?K[n-1]:null;f.form3=n;
  f.spdMul=F?F.spd:1;f.dmgMul=F?F.dmg:1;f.takenMul=F?F.taken:1;f.form3Until=F&&F.lasts>0?tick+ms2t(F.lasts):0;
  if(!f.on)return;
  if(drop){fx_ring(f.x,f.y,0x9aa1bd,2,.3,1);callout(F?F.name:'Base form',f.k.name+' drops back','#9aa1bd',.5,true);return;}
  fx_dome(f.x,f.y,f.k.fx,5);fx_ring(f.x,f.y,0xffffff,3,.3,1.1);flash(.3);shake=Math.max(shake,.7);hitstopMs=Math.max(hitstopMs,140);}
// updFighter, every tick: the pending change lands when its action ends; timed forms drop back one
function formTick(f){if(!f.k.forms3d)return;
  if(f.tfPending&&!(f.act&&f.act.kind==='transform')){const i=f.tfPending;f.tfPending=0;if(!f.ko)formApply(f,i,false);}
  if(f.form3>0&&f.form3Until&&tick>=f.form3Until&&!f.tfPending)formApply(f,f.form3-1,true);}
// may this action def be used in the fighter's current form (action_settings[a].in_forms)?
function formAllows(f,def){return !def||!def.inForms||def.inForms.includes(f.form3||0);}
