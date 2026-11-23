'use strict';
/* Parry / deflect (Ctrl+Space). Every fighter: the player presses it, the AI parries by chance rolls.
   A parry opens a timing window:
     0 .. perfectMs        PERFECT: no damage, no knockback. A melee attacker is staggered (staggerMs) and a
                           counter window opens (counterMs): the parrier's hits on it deal counterDmgPct %. An AI
                           parrier counter-attacks at once. A shot is sent off at the source instead: back at
                           its shooter (reflect) or away (deflect). Player: WASD held = deflected that way, none
                           = reflected back. AI: fxResult (reflect / deflect / random).
     perfectMs .. windowMs NORMAL: damage x (100 - normalReducePct) %, knockback x normalKbPct %, no stagger.
   Then cooldownMs before the next parry (mashing whiffs). A staggered fighter can still parry the counter back
   (player: the key; AI: recoverPct), so parries chain.
   AI rolls: an incoming hit with no window open, once per tick: aiPerfectPct -> perfect, aiNormalPct -> normal.
   A shot heading in within reach is rolled once (aiFxPct) -> a perfect window.
   This sits beside the older reactions: the perfect snap (Space) and Ronin / Tough's own parry / block stay.
   Per-kit override: kit.parry = {any key below}. Settings > "AI parries" turns the AI rolls off. */
const PARRY_DEFAULTS={perfectMs:130,windowMs:330,cooldownMs:420,normalReducePct:60,normalKbPct:40,
  staggerMs:520,counterMs:900,counterDmgPct:150,reach:110,fxResult:'random',
  aiPerfectPct:10,aiNormalPct:14,aiFxPct:18,recoverPct:22};
function parryCfg(f){return f.k.parry?Object.assign({},PARRY_DEFAULTS,f.k.parry):PARRY_DEFAULTS;}
function pstate(f){return f.pw||(f.pw={start:-1e9,until:-1,cd:0,grade:null,player:false,rolled:-1,seen:new Set(),counterOn:null,counterUntil:-1,ring:null});}
function playerFig(f){return f.side===0&&level!=='watch';}

function parryOpen(f,grade,player){const c=parryCfg(f),st=pstate(f);st.start=tick;st.until=tick+ms2t(c.windowMs);st.cd=st.until+ms2t(c.cooldownMs);st.grade=grade||null;st.player=!!player;
  // the window: a thin ring round the body while it is open
  const g=new THREE.Mesh(new THREE.TorusGeometry(.62,.035,6,32),add(0xdbe9ff,.85));g.rotation.x=Math.PI/2;g.position.copy(VA(f.x,f.y,f.z,1));
  temp(g,c.windowMs/1000,u=>{g.position.copy(VA(f.x,f.y,f.z,1));g.scale.setScalar(1+u*.25);g.material.opacity=.85*(1-u)*(u<c.perfectMs/c.windowMs?1:.55);g.material.color.setHex(u<c.perfectMs/c.windowMs?0xfff0b0:0x9fc8ff);});}
function parryWindow(f){const st=f.pw;if(!st||tick>st.until)return null;if(st.grade)return st.grade;return tick-st.start<=ms2t(parryCfg(f).perfectMs)?'perfect':'normal';}
function parryReady(f){return !f.pw||tick>=f.pw.cd;}

// Player: Ctrl+Space.
function parryPress(f){if(!f||f.ko||f.gone>0)return false;if(!parryReady(f))return false;parryOpen(f,null,true);stats.pParries++;return true;}

// AI roll for a hit about to land on t.
function parryAiHit(t){if(!settings.aiParry||playerFig(t)||t.dummy&&t.dummy.beh==='stand')return;const st=pstate(t);if(st.rolled===tick||tick<=st.until||!parryReady(t))return;st.rolled=tick;
  const c=parryCfg(t),r=Math.random()*100;
  if(t.stun>0){if(r<c.recoverPct)parryOpen(t,'perfect');return;}
  if(r<c.aiPerfectPct)parryOpen(t,'perfect');else if(r<c.aiPerfectPct+c.aiNormalPct)parryOpen(t,'normal');}

// Called first in damage() for a blockable hit. Returns {k, kb} (damage / knockback kept) or null when the hit is
// parried outright (perfect).
function parryOnHit(a,t,isShot,shot){parryAiHit(t);const w=parryWindow(t);if(!w)return {k:1,kb:1};const c=parryCfg(t);
  if(w==='normal'){fx_ring(t.x,t.y,0x9fc8ff,1.8,.22,1);fx_sparks(t.x,t.y,0x9fc8ff,8,5);director.cnt++;if(t.side===0&&level!=='watch')callout('PARRY','','#9fc8ff',.4,true);
    return {k:Math.max(0,1-c.normalReducePct/100),kb:Math.max(0,c.normalKbPct/100)};}
  // perfect
  const st=pstate(t);stats.parries[t.side]++;if(t.side===0)stats.perfectParries++;director.cnt++;
  FXF=t;fx_ring(t.x,t.y,0xffc857,3.2,.3,1.1);fx_ring(t.x,t.y,0xffffff,2.2,.2,1.1);fx_sparks(t.x,t.y,0xffe7a0,26,9);fx_star(t,t,3);
  hitstopMs=Math.max(hitstopMs,95);shake=Math.max(shake,.45);camPunch=Math.max(camPunch,.06);flash(.12);
  if(isShot&&shot){parryShot(t,shot,c);}
  else if(!isShot&&a&&a!==t&&!a.ko){stun(a,c.staggerMs,'stag');a.lastWhiff=true;a.recoil=Math.min(1.2,a.recoil+.6);
    const dx=a.x-t.x,dy=a.y-t.y,d=Math.hypot(dx,dy)||1;a.vx+=dx/d*260;a.vy+=dy/d*260;
    st.counterOn=a;st.counterUntil=tick+ms2t(c.counterMs);t.tp.mom=1;t.gapUntil=0;
    if(!playerFig(t))later(70,()=>{if(t.on&&!t.ko&&!a.ko&&!t.act){if(t.k.rhythm!==false)enter(t,'punish');tryAttack(t,a,true);}});}
  if(t.side===0||a&&a.side===0)callout(t.side===0?'PERFECT PARRY':'PARRIED',isShot?(shot?'Sent back':'Turned aside'):t.k.name+' opens a counter',t.side===0?'#ffc857':'#ff8a9a',.6,true);
  return null;}

// A perfect-parried shot leaves at its source, now owned by the parrier.
function parryShot(t,s,c){const sp=Math.max(900,Math.hypot(s.vx,s.vy))*1.15;let ux,uy;
  let res=c.fxResult;if(playerFig(t)){res=inputDir?'deflect':'reflect';}else if(res==='random')res=Math.random()<.5?'reflect':'deflect';
  if(res==='reflect'){const o=s.owner&&!s.owner.ko&&s.owner.on?s.owner:enemyOf(t);const dx=o.x-s.x,dy=o.y-s.y,d=Math.hypot(dx,dy)||1;ux=dx/d;uy=dy/d;
    const tt=Math.max(.05,d/sp);s.vz=clamp((o.z-(s.z||0))/tt,-2500,2500);}
  else if(playerFig(t)&&inputDir){ux=inputDir[0];uy=inputDir[1];s.vz=0;}
  else{const a=Math.atan2(-s.vy,-s.vx)+(Math.random()<.5?1:-1)*rnd(.9,1.6);ux=Math.cos(a);uy=Math.sin(a);s.vz=rnd(-200,500);}
  s.vx=ux*sp;s.vy=uy*sp;s.side=t.side;s.owner=t;s.life=ms2t(1400);s.redirected=true;
  fx_streak(VA(s.x,s.y,s.z||0,1.1),VA(s.x+ux*160,s.y+uy*160,s.z||0,1.1),0xffe7a0,.05);}

// Counter bonus on hits by the parrier on the fighter it staggered.
function parryCounterMult(a,t){const st=a&&a.pw;if(!st||st.counterOn!==t||tick>st.counterUntil)return 1;return parryCfg(a).counterDmgPct/100;}

// Per tick, every fielded fighter: the AI's shot roll.
function parryTick(f){if(!settings.aiParry||playerFig(f)||f.ko||!f.on||f.dummy&&f.dummy.beh==='stand')return;const st=pstate(f);
  if(st.seen.size>64)st.seen.clear();
  if(tick<=st.until||!parryReady(f))return;const c=parryCfg(f);
  for(const s of shots){if(s.side===f.side||st.seen.has(s))continue;if(Math.abs((s.z||0)-f.z)>160)continue;
    const dx=f.x-s.x,dy=f.y-s.y,sp=Math.hypot(s.vx,s.vy)||1;const along=(dx*s.vx+dy*s.vy)/sp;if(along<0||along>c.reach+sp*DT*3)continue;
    if(Math.abs(dx*s.vy-dy*s.vx)/sp>60)continue;st.seen.add(s);if(Math.random()*100<c.aiFxPct){parryOpen(f,'perfect');break;}}}
