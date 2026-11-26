'use strict';
/* Live FX + 3D action movement in the fight (replaces fx2d.js, Daniel 2026-11-24 "FX Studio 3D").
   FX: each real-kit fighter runs one FX3D.Runner (fx3d.js): FX Studio's own 2D FX runtime, every effect laid on a
   card placed in 3D the way its `fx3d` block says (FX Studio 3D), anchors read from the .glb body's bones. Hits:
   every enemy the effect touches (training: every dummy), with FX Studio's damage / knockback / re-hit rules.
   Movement: an action with `action_settings[a].move3d` moves the body itself (start spot round the target, then a
   path to the end spot); root motion, lunges, drift and gravity stand aside while it runs. Solo + Battle. */
function fxRunner(f){if(f.fx3)return f.fx3;if(!f.k.fx2d||!window.FX3D||!window.FXK)return null;
  const src=f.k.src||{};const own=f.glb&&f.glb.body;
  const run=new FX3D.Runner({fx:src.fxkit||{},palette:src.palette||{},anchors3d:(own&&own.anchors3d)||null,scene,
    onHit:(e,dmg,kb,inst)=>fxHit(f,e,dmg,kb,inst),
    onHitstop:n=>{hitstopMs=Math.max(hitstopMs,n*TICK);},onShake:px=>{shake=Math.max(shake,Math.min(1.2,px*.05));}});
  const bones={};const bone=n=>{if(!f.glb)return null;if(!(n in bones))bones[n]=f.glb.model.getObjectByName(n)||null;return bones[n];};
  f.fx3={run,bone};return f.fx3;}
function fxHit(f,e,dmg,kb,inst){if(!e||e.ko||!e.on)return;const fx=inst.fx||{};
  // a transformation burst with no damage (hyperfx.js, Daniel 2026-11-26 "knockback, no damage"): a pure push
  if(!(dmg>0)&&window.HYPERFX&&HYPERFX.isTransform((fx.params||{}).style)){fxShove(f,e,kb);return;}
  const w=kb>=20?'B':kb>=13?'H':kb>=7?'M':'L';const shot=fx.motion&&fx.motion.kind!=='attached'&&fx.motion.kind!=='orbit';
  const w0=fxDefendTicks(e),dodging=e.iframe>0;
  if(damage(f,e,dmg,w,shot,null,kb>0?kb*PX2D*.35:0,false,true)!==false)return;
  // Defended (dodge i-frames, a parry window, a blink): the effect keeps its hit (fx3d.js tryHit) and may land once the
  // defence is over (Daniel 2026-11-26: FX phasing through the body). The dodge shows, so it never reads as a miss.
  if(e.ko||!e.on)return;
  if(dodging&&e.gone<=0){fx_ghost(e,e.x,e.y);fx_ring(e.x,e.y,0xffffff,1.3,.16,1);}
  return Math.max(1,w0,fxDefendTicks(e));}
// How many more ticks a target's defences last: dodge i-frames, an old-style parry, the parry window (parry.js), a blink.
function fxDefendTicks(t){const pw=t.pw;return Math.max(Math.ceil(t.iframe||0),Math.ceil(t.parry||0),t.gone>0?Math.ceil(t.gone):0,pw&&pw.until>=tick?pw.until-tick+1:0);}
// Pushed away from the fighter (kb = FX Studio knockback px): no damage, no hit flash, a short stagger so it reads.
function fxShove(f,e,kb){if(!(kb>0)||e.gone>0)return;const dx=e.x-f.x,dy=e.y-f.y,d=Math.hypot(dx,dy)||1,v=kb*PX2D*6;
  const kvx=e.vx,kvy=e.vy;e.vx+=dx/d*v;e.vy+=dy/d*v;if(!e.dummy||e.dummy.beh!=='stand')stun(e,280,'stag');
  fx_dust(e.x,e.y,4);if(typeof camKnock==='function')camKnock(e,e.vx-kvx,e.vy-kvy);}
// Sim tick (main.js / training.js), each fielded fighter: advance its FX one 16 ms tick.
function fxTick(f){const S=fxRunner(f);if(!S)return;
  if(!f.on||f.ko){S.run.reset();fxHeldBlades(f,null);return;}
  const foes=foesOf(f.side).filter(t=>t&&t.on&&!t.ko&&t.gone<=0&&!t.phantom);
  let tg=enemyOf(f);if(!tg||!foes.includes(tg))tg=foes[0]||null;
  const a=f.act&&f.act.def&&f.act.def.fx2d?f.act:null;
  S.run.tick({centre:VA(f.x,f.y,f.z,.9+(f.h||0)),feet:VA(f.x,f.y,f.z,f.h||0),facing:new THREE.Vector3(Math.cos(f.face),0,Math.sin(f.face)),
    bone:S.bone,target:tg?{centre:VA(tg.x,tg.y,tg.z,.9+(tg.h||0))}:null,
    enemies:foes.map(t=>({centre:VA(t.x,t.y,t.z,.9+(t.h||0)),r:.45,ref:t})),
    action:a?{key:a,name:a.def.n2d,frames:a.def.frames,frameMs:a.def.frameMs}:null,
    moving:!!(f.snap||f.lean>.2),gone:f.gone>0,frame:a?Math.floor(a.t*TICK/a.def.frameMs):0,groundY:0});
  // the planet: moving FX hit scenery, low beams / flyers dig the ground, big impacts crater (planet.js planetFx)
  if(PLANET&&typeof planetFx==='function')planetFx(S.run.worldFx());
  fxHeldBlades(f,S);}
// one of each blade: the 3D weapon hides while its own weapon FX is out (weapons3d.js pbwFxHeld)
function fxHeldBlades(f,S){if(f.glb&&typeof pbwFxHeld==='function')pbwFxHeld(f.glb.model,S&&f.on&&!f.ko?S.run.lanes:null,f);}
// Render frame (main.js): paint and place every fighter's live FX cards.
function fxDraw(){const H=renderer.domElement.height;
  for(const s of sides)for(const f of s.team){const S=f.fx3;if(!S)continue;
    if(!f.on||f.ko){S.run.reset();continue;}S.run.draw(cam,H,{hidden:f.gone>0});}}
function fxClear(f){if(f.fx3){f.fx3.run.clear();f.fx3=null;}f.mv3=null;}

/* ---- per-action 3D movement (move3d) ---- */
// startAct (combat.js): plan the move from where the fighter and its target stand now (metres, y up).
function mv3Start(f,def){f.mv3=null;const M=def&&def.move3d;if(!M||!window.FX3D)return;
  const e=enemyOf(f);if(!e||!e.on||e.ko)return;
  const plan=FX3D.movePlan(M,new THREE.Vector3(f.x*K,f.z*K,f.y*K),new THREE.Vector3(e.x*K,e.z*K,e.y*K),def.frames||1,def.frameMs||16);
  f.mv3={plan,act:f.act,last:null,dir:null};
  if(plan.blink){fx_ghost(f,f.x,f.y);mv3Place(f,plan.P0);fx_ring(f.x,f.y,f.k.fx,1.6,.2,1);}}
function mv3Place(f,p){const nx=clamp(p.x/K,30,W-30),ny=clamp(p.z/K,30,H-30);
  if(f.mv3&&f.mv3.last){const dx=nx-f.x,dy=ny-f.y;if(Math.hypot(dx,dy)>.5)f.mv3.dir=Math.atan2(dy,dx);}
  f.x=nx;f.y=ny;f.z=clamp(p.y/K,0,ZMAX);f.vx=f.vy=0;f.vz=0;if(f.mv3)f.mv3.last=p;}
// updFighter, each tick of the action it belongs to.
function mv3Step(f,a){const m=f.mv3;if(!m)return;if(m.act!==a){f.mv3=null;return;}
  mv3Place(f,m.plan.at(a.t*TICK,new THREE.Vector3()));}
