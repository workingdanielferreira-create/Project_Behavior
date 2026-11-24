'use strict';
/* Combat: actions, triggered actions, attacks, skills, hit resolve, damage + hit feel, stun, K.O., projectiles, auto reactions, tagging. */
/* ================= combat ================= */
function onField(){return [sides[0].team[sides[0].on],sides[1].team[sides[1].on]];}
function enemyOf(f){return sides[1-f.side].team[sides[1-f.side].on];}
function startAct(f,def,kind,name){if(kind==='ult')camEvent('ult');const a={def,kind,name,t:0,hi:0,fi:0,li:0};if(def.n2d){f.lastAct2d=def.n2d;f.lastActTick=tick;}
  if(f.stateUntil>tick&&['normal','special','special2'].includes(kind)){const e=enemyOf(f);[0,180,360].forEach(ms=>later(ms,()=>{if(f.on&&!f.ko&&!e.ko)heavenBlade(f,e);}));}f.act=a;mv3Start(f,def);f.armor=def.armor||0;f.landedThisAct=false;stats.starts[f.side]++;metr.starts.push(tick);
  if(f.on&&f.side===0)stats.actions++;return a;}
function endAct(f){if(!f.act)return;f.mv3=null;f.lastEnd=tick;f.lastWhiff=!f.landedThisAct&&f.act.kind!=='react';f.act=null;f.armor=0;f.justEnded=true;}
const fieldBlades=[];
function condTrue(f,e,c,trig){const d=Math.hypot(f.x-e.x,f.y-e.y);
  switch(c[0]){
  case'every_ms':return tick-(trig.last||0)>=ms2t(c[1]);
  case'hp_below':return f.hp/f.max*100<c[1]&&!f.thr[c[1]];
  case'self_act':return f.lastAct2d===c[1]&&tick-f.lastActTick<=ms2t(c[2]+(f.act?0:0))+ms2t(f.k.normals.concat([f.k.special,f.k.special2,f.k.ult]).find(x=>x&&x.n2d===c[1])?.dur||0);
  case'target_act':return !!(e.act&&e.act.kind===c[1]&&e.act.t*TICK<=c[2]);
  case'damage_taken':{const from=tick-ms2t(c[2]);return f.dmgLog.filter(x=>x[0]>from).reduce((a,x)=>a+x[1],0)>=c[1];}
  case'blade_near':return fieldBlades.some(b=>b.side===f.side&&Math.hypot(b.x-f.x,b.y-f.y)<=c[1]+60);
  case'target_beyond':return d>c[1];
  case'proj_count':return shots.filter(s=>s.side===f.side).length>=c[1];}
  return false;}
function fireTrigger(f,tr,e){const slot=tr.slot;const def=f.k[slot];if(!def)return false;
  tr.conds.forEach(c=>{if(c[0]==='hp_below'&&f.hp/f.max*100<c[1])f.thr[c[1]]=1;});
  if(slot==='defend'){if(f.act)endAct(f);f.block=ms2t(def.dur);startAct(f,def,'react','defend');return true;}
  startAct(f,def,slot,slot);stats.used[f.side][slot==='ult'?'ult':slot]++;if(slot==='ult'&&f.on)callout(def.name,f.k.name,cssc(f.k.fx),.9);return true;}
function realTriggers(f,e){// 2D: a triggered action fires the tick its conditions hold (logic any); gate_triggered gates it by intent
  if(f.k.gate&&!allows(f))return false;
  const mine=f.side===0&&level==='commander';
  for(const tr of f.k.triggers){const st=f.trig[tr.slot]||(f.trig[tr.slot]={last:tick});
    if(tr.cd&&tick-st.fired<ms2t(tr.cd))continue;
    if(mine&&tr.slot!=='defend'&&tick-(st.fired||0)<ms2t(6000))continue; // Commander: AI only uses one you left unused for 6 s
    if(tr.slot!=='defend'&&(f.act||f.stun>0||f.snap||f.gone>0))continue;
    if(tr.slot==='defend'&&(f.block>0||f.stun>0))continue;
    // real kits: FX Studio conditions (realkits.js realCond), logic any / all; with no conditions = never on its own
    const ok=f.k.fx2d?(tr.conds.length&&(tr.logic==='all'?tr.conds.every(c=>realCond(f,e,c,st)):tr.conds.some(c=>realCond(f,e,c,st)))):tr.conds.some(c=>condTrue(f,e,c,st));
    if(ok){if(f.k.fx2d&&f.k[tr.slot]&&f.k[tr.slot].mcd&&tick<(st.cdUntil||0))continue;st.last=tick;st.fired=tick;if(f.k.fx2d&&f.k[tr.slot])st.cdUntil=tick+ms2t(f.k[tr.slot].mcd||0);return fireTrigger(f,tr,e);}}
  return false;}
function tryAttack(f,e,forced){
  if(f.k.real&&!forced&&realTriggers(f,e))return true;
  if(f.formChannel>=0)return false;
  const free=!f.act&&f.stun<=0&&!f.snap&&f.gone<=0;if(!free)return false;
  const d=Math.hypot(f.x-e.x,f.y-e.y);
  const bu=burst();
  // 2D: triggered actions (specials, ultimate) are not gated by intent (gate_triggered defaults off)
  // Commander: specials / ultimate are yours; the AI only uses one left ready and unused for 6 s (ultimate 8 s)
  const mine=f.side===0&&level==='commander';const aiOk=(k,ms)=>!mine||tick-f.cds[k]>ms2t(ms);
  if(!forced&&tick>=f.gapUntil&&!f.k.real){
  if(f.cds.ult<=tick&&aiOk('ult',8000)&&(bu||f.hp/f.max<.4)&&Math.random()<.35&&d<=Math.max(f.k.reach*2.2,240)){startAct(f,f.k.ult,'ult','ult');f.cds.ult=tick+ms2t(f.k.ult.cd);stats.used[f.side].ult++;if(f.on)callout(f.k.ult.name,f.k.name,cssc(f.k.fx),.9);return true;}
  if(f.cds.special<=tick&&aiOk('special',6000)&&Math.random()<.22&&d<=(f.k.melee?260:f.k.reach)){startAct(f,f.k.special,'special','special');f.cds.special=tick+ms2t(f.k.special.cd);stats.used[f.side].special++;return true;}
  if(f.cds.special2<=tick&&aiOk('special2',6000)&&Math.random()<.16&&d<=(f.k.melee?320:f.k.reach*1.2)){startAct(f,f.k.special2,'special2','special2');f.cds.special2=tick+ms2t(f.k.special2.cd);stats.used[f.side].special2++;return true;}
  }
  if(!forced&&(!allows(f)||tick<f.gapUntil))return false;
  if(f.k.rhythm===false&&!forced)f.gapUntil=tick+ms2t(rnd(150,450));
  if(d>f.k.reach*(forced?1.9:(f.k.melee?1.7:1)))return false;
  if(f.k.melee&&Math.abs(f.z-e.z)>f.k.reach*(forced?1.9:1.3)+60)return false;
  if(tick-f.lastNormal>ms2t(900))f.ni=0;
  const def=f.k.normals[f.ni%f.k.normals.length];f.ni++;f.lastNormal=tick;startAct(f,def,'normal','N'+f.ni);stats.used[f.side].normal++;return true;}
function useSkill(f,which){if(!f||f.ko||f.stun>0||f.gone>0||!f.k[which]||f.k[which].none)return false;const e=enemyOf(f);
  if(f.act&&f.act.kind!=='normal')return false;const cdk=which;if(f.cds[cdk]>tick){return false;}
  if(f.k.real){if(f.act)endAct(f);const def=f.k[which];startAct(f,def,which,which);f.cds[cdk]=tick+ms2t(def.mcd||2500);const st=f.trig[which]||(f.trig[which]={});st.last=tick;st.fired=tick;stats.used[f.side][which]++;if(which==='ult')callout(def.name,f.k.name,cssc(f.k.fx),.9);return true;}
  if(f.act)endAct(f);const def=f.k[which];startAct(f,def,which,which);f.cds[cdk]=tick+ms2t(def.cd);stats.used[f.side][which==='ult'?'ult':which]++;
  if(which==='ult')callout(def.name,f.k.name,cssc(f.k.fx),.9);return true;}
function hitResolve(a,t,h){ // h=[at,dmg,w,reach]
  if(t.ko||!t.on||t.gone>0)return false;
  const d=Math.hypot(a.x-t.x,a.y-t.y);if(h[3]>0&&d>h[3])return false;if(h[3]>0&&Math.abs(a.z-t.z)>h[3]*.9+50)return false;
  // Most 2D attacks whiff (about 1 in 5 actions lands): a free target slips normals with a sidestep.
  if(a.act&&a.act.kind!=='ult'&&t.stun<=0&&t.parry<=0&&t.block<=0&&!(t.dummy&&t.dummy.beh!=='fight')){const nm=a.act.kind==='normal';const pLand=t.snap?0:t.act?(nm?.36:.6):(nm?.2:.45);if(Math.random()>pLand){
    const ang=Math.atan2(t.y-a.y,t.x-a.x)+(Math.random()<.5?1.6:-1.6);const sx=t.x,sy=t.y;t.x=clamp(t.x+Math.cos(ang)*34,20,W-20);t.y=clamp(t.y+Math.sin(ang)*34,20,H-20);fx_ghost(t,sx,sy);return false;}}
  return damage(a,t,h[1],h[2],false,null,h[4]);}
function damage(a,t,dmg,w,isShot,shot,kbpx,unblock){
  if(t.ko||!t.on||t.gone>0)return false;
  if(!shot&&Math.abs(a.z-t.z)>(isShot?520:420)&&t.stun<=0)return false; // too far above / below
  if(t.iframe>0){if(t.side===0&&t.perfectReady){t.perfectReady=false;perfect(t,a);}return false;}
  if(t.parry>0&&!isShot&&!unblock){t.parry=0;stun(a,450,'stag');a.lastWhiff=true;fx_ring(t.x,t.y,0xffffff,2.6,.3,1.1);fx_sparks(t.x,t.y,0xffffff,24,8);hitstopMs=Math.max(hitstopMs,(70));shake=Math.max(shake,.4);director.cnt++;
    if(t.side===0||a.side===0)callout('PARRY',t.k.name+' turns it aside',cssc(t.k.fx),.6,true);stats.parries[t.side]++;return false;}
  if(t.parry>0&&isShot&&!unblock){t.parry=0;if(shot){shot.side=t.side;shot.vx*=-1.2;shot.vy*=-1.2;shot.dmg*=1.2;}fx_ring(t.x,t.y,0xffffff,2,.25,1.1);director.cnt++;return false;}
  // Parry / deflect (parry.js): a perfect parry takes the hit, a normal one cuts damage and knockback.
  let pk=1,pkb=1;if(!unblock){const pr=parryOnHit(a,t,isShot,shot);if(!pr)return false;pk=pr.k;pkb=pr.kb;}
  let k=pk;if(t.block>0&&!unblock){k=Math.min(k,.3);fx_ring(t.x,t.y,t.k.fx,1.8,.25,1);director.cnt++;}
  dmg*=(a.dmgMul||1)*(t.takenMul||1)*parryCounterMult(a,t)*(a.dummy?TRAIN.fightDmg:1);const dm=dmg*k;t.dmgLog.push([tick,dm]);if(t.dmgLog.length>40)t.dmgLog.shift();t.hp=Math.max(0,t.hp-dm);t.hurts.push(tick);t.lastHurt=tick;if(t.hurts.length>8)t.hurts.shift();t.tp.mom=Math.max(-1,t.tp.mom-.2);
  trainNoteHit(a,t,dm);a.landedThisAct=true;a.lastLanded=tick;a.tp.mom=Math.min(1,a.tp.mom+.15);
  director.hits++;director.dmg+=dm;director.taken+=dm;director.lastHitTick=tick;metr.hits.push(tick);stats.dealt[a.side]+=dm;
  const wv={L:1,M:2,H:3,B:4}[w]||1;
  // HIT FEEL: freeze on every hit (by weight), target flashes / shakes / recoils, directional shake, camera punch, impact star, numbers
  FXF=t;const HS=[0,55,95,145,190][wv];hitstopMs=Math.max(hitstopMs,HS*(k<1?.6:1));t.flashT=.11;t.jitT=HS/1000+.05;t.recoil=Math.min(1.2,t.recoil+.22*wv);
  fx_sparks(t.x,t.y,a.k.fx,10+wv*9,6+wv*2.5);fx_sparks(t.x,t.y,0xffffff,6+wv*3,9+wv*2);fx_ring(t.x,t.y,a.k.core,1.4+wv*.9,.26,1);fx_star(t,a,wv);
  if(wv>=3&&k===1){flash(.1*wv);fx_crack(t.x,t.y,wv);}
  {const ddx=t.x-a.x,ddy=t.y-a.y,l=Math.hypot(ddx,ddy)||1;shakeDir=[ddx/l,ddy/l];}shake=Math.max(shake,.16*wv+.08);camPunch=Math.max(camPunch,.035*wv);
  dmgNum(t,Math.round(dm),a.k.fx,wv);a.vx+=Math.cos(a.face)*40;a.vy+=Math.sin(a.face)*40;
  // 2D-style trading: light hits never interrupt, medium only an idle target, heavy / blowback always (unless armoured)
  const dx=t.x-a.x,dy=t.y-a.y,dd=Math.hypot(dx,dy)||1;
  if(k===1&&wv>t.armor&&(wv>=3||(wv===2&&!t.act))){if(t.act)endAct(t);const kb=[0,160,420,800,1600][wv];t.vx+=dx/dd*kb;t.vy+=dy/dd*kb;
    stun(t,[0,150,260,600,850][wv],wv>=3?'down':'stag');if(wv>=3&&t.z<10)fx_dust(t.x,t.y,6);
    if(wv>=3&&a.z>t.z+60&&t.z>90){t.vz=-2900;t.stunKind='air';callout('SPIKE','','#ffc857',.5,true);camEvent('launch');}
    else if(wv===4){t.vz=(t.z-a.z)*1.4+rnd(350,800);t.stunKind='air';t.vx*=GRAV.launchPower;t.vy*=GRAV.launchPower;}
    else if(wv===3&&(t.z<40?Math.random()<.4:Math.random()<.25)){t.vz=rnd(1250,1650);t.stunKind='air';t.stun=Math.max(t.stun,ms2t(1000));t.vx*=GRAV.launchPower;t.vy*=GRAV.launchPower;callout('LAUNCH','','#8fd3ff',.5,true);camEvent('launch');
      if(a.k.melee&&!(a.side===0&&level==='handson'))later(200,()=>{if(a.ko||!a.on||t.ko)return;a.snapCd=0;a.gapUntil=0;snapTo(a,t.x-Math.cos(a.face)*60,t.y-Math.sin(a.face)*60,Math.random()<a.k.blink,true,t.z+40);if(!canFly(a))a.jumpAfterSnap=true;if(a.k.rhythm!==false)enter(a,'punish');});}}
  if(kbpx&&k===1){t.vx+=dx/dd*kbpx*2.2;t.vy+=dy/dd*kbpx*2.2;}
  else{t.vx+=dx/dd*(wv>=2?220:110)*pkb;t.vy+=dy/dd*(wv>=2?220:110)*pkb;}
  planetHit(t,wv,dm);   // planet.js: the impact reaches scenery / pillars round the target
  if(t.hp<=0)ko(t);return true;}
function stun(f,ms,kind){f.stun=Math.max(f.stun,ms2t(ms));f.stunKind=kind;f.stunId=(f.stunId||0)+1;f.snap=null;if(f.act)endAct(f);}
function perfect(t,a){slowmo=ms2t(320);stats.perfect++;callout('PERFECT SNAP','Dodged on the frame · counter ready','#ffc857',.7);flash(.25);t.tp.mom=1;t.gapUntil=0;stun(a,300,'stag');a.lastWhiff=true;director.cnt++;}
function ko(f){if(training){f.hp=0;return;}   // training.js: nobody is K.O.'d, HP refills
  f.ko=true;camEvent('ko');if(f.act)endAct(f);director.ko++;const s=sides[f.side];stats.kos[f.side]++;
  callout('K.O.',f.k.name,'#ff3b55',.9);fx_dome(f.x,f.y,0xffffff,5);planetCrater(f.x,f.y,2.6);planetBlast(f.x,f.y,f.z,220,80);flash(.3);shake=1;slowmo=ms2t(400);
  later(450,()=>{const alive=s.team.map((g,i)=>i).filter(i=>!s.team[i].ko);if(!alive.length){endGame(f.side===1);return;}tagIn(f.side,alive[0],'rescue');});}

function distSeg(px,py,ax,ay,bx,by){const abx=bx-ax,aby=by-ay,L=abx*abx+aby*aby;const t=L?clamp(((px-ax)*abx+(py-ay)*aby)/L,0,1):0;return Math.hypot(px-ax-abx*t,py-ay-aby*t);}
function shoot(f,vx,vy,dmg,r){const m=new THREE.Mesh(new THREE.SphereGeometry(r,10,8),new THREE.MeshBasicMaterial({color:f.k.core}));const gl=new THREE.Mesh(new THREE.SphereGeometry(r*2.4,10,8),add(f.k.fx,.35));m.add(gl);
  const x=f.x+Math.cos(f.face)*40,y=f.y+Math.sin(f.face)*40;const e=enemyOf(f);const tt=Math.max(.05,Math.hypot(e.x-x,e.y-y)/(Math.hypot(vx,vy)||1));const vz=clamp((e.z-f.z)/tt,-2500,2500);
  m.position.copy(VA(x,y,f.z,1.1));scene.add(m);shots.push({m,x,y,z:f.z,vx,vy,vz,dmg,side:f.side,life:ms2t(1400),owner:f});}
function stepShots(){for(let i=shots.length-1;i>=0;i--){const s=shots[i];const px=s.x,py=s.y;s.x+=s.vx*DT;s.y+=s.vy*DT;s.z=clamp((s.z||0)+(s.vz||0)*DT,0,ZMAX+200);s.life--;s.m.position.copy(VA(s.x,s.y,s.z,1.1));
  let dead=s.life<=0||s.x<0||s.x>W||s.y<0||s.y>H;
  if(!dead&&planetShot(s))dead=true;   // planet.js: pillars / landmarks block shots
  if(!dead)for(const t of foesOf(s.side)){   // training: every dummy
    if(t&&!t.ko&&t.on&&!t.phantom&&distSeg(t.x,t.y,px,py,s.x,s.y)<42&&Math.abs((s.z||0)-t.z)<90){const owner=s.owner;if(t.parry>0){damage(owner,t,s.dmg,'L',true,s);}else{damage(owner,t,s.dmg,s.dmg>50?'M':'L',true,s);if(s.redirected)s.redirected=false;else dead=true;}break;}}
  if(dead){scene.remove(s.m);shots.splice(i,1);}}}

/* ---- auto reactions (2D: rare) ---- */
function incomingShot(f,trig){for(const s of shots){if(s.side===f.side)continue;if(Math.abs((s.z||0)-f.z)>160)continue;const dx=f.x-s.x,dy=f.y-s.y,sp=Math.hypot(s.vx,s.vy)||1;const along=(dx*s.vx+dy*s.vy)/sp;if(along<0||along>(trig||300))continue;const perp=Math.abs(dx*s.vy-dy*s.vx)/sp;if(perp<60)return along/sp*1000;}return null;}
function incoming(f,e){// real kits: an attack action starting within reach counts as incoming for its first 150 ms
  if(e.act&&e.act.def.fx2d&&e.act.kind!=='react'){const tm=e.act.t*TICK,d=Math.hypot(f.x-e.x,f.y-e.y);return tm<150&&d<=e.k.reach+80?150-tm:null;}
  if(!e.act||!e.act.def.hits)return null;const a=e.act;for(const h of a.def.hits){const dt=h[0]-a.t*TICK;if(dt>0&&dt<=150){const d=Math.hypot(f.x-e.x,f.y-e.y);if(h[3]===0||d<=h[3]+40)return dt;}}return null;}
function autoReact(f,e){const r=f.k.react;const side=r.kind==='sidestep';if(f.reactCd>tick||(f.act&&!(side&&f.act.kind==='normal'))||f.stun>0||f.snap||f.ko)return;let inc=r.shotsOnly?null:incoming(f,e);if(inc==null&&(side||r.kind==='dodge'))inc=incomingShot(f,r.trig);if(inc==null)return;
  if(f.side===0&&level==='handson')return;
  if(Math.random()>r.p)return;f.reactCd=tick+ms2t(r.cd||1400);
  if(side){if(f.act)endAct(f);const a=Math.atan2(f.y-e.y,f.x-e.x)+(Math.random()<.5?1.5:-1.5);const dd=r.dist||320;if(!f.k.real)f.iframe=ms2t(230);f.snapCd=0;snapTo(f,f.x+Math.cos(a)*dd,f.y+Math.sin(a)*dd,false,true,f.z+rnd(-140,140));fx_ring(f.x,f.y,0xffffff,2,.2,1);if(r.counter||!f.k.real)f.counterAt=tick+ms2t(140);director.cnt++;return;}
  if(r.kind==='parry'){f.parry=ms2t(300);startAct(f,{dur:300,hits:[],fx:[]},'react','parry');}
  else if(r.kind==='block'){f.block=ms2t(420);startAct(f,{dur:420,hits:[],fx:[]},'react','block');}
  else{const a=Math.atan2(f.y-e.y,f.x-e.x)+(Math.random()<.5?1.2:-1.2);f.iframe=ms2t(220);snapTo(f,f.x+Math.cos(a)*200,f.y+Math.sin(a)*200,Math.random()<f.k.blink);}}

/* ---- tagging ---- */
function tagIn(side,idx,kind){if(training)return;const s=sides[side];const out=s.team[s.on];const e=enemyOf(out);if(!out.ko){if(out.act)endAct(out);fx_ghost(out,out.x,out.y);out.bench=tick;}setOn(out,false);
  s.on=idx;const f=s.team[idx];setOn(f,true);f.pose.rotation.set(0,0,0);f.stun=0;f.vx=f.vy=0;f.act=null;f.snap=null;f.gone=0;
  const a=rnd(0,TAU);f.x=clamp(e.x+Math.cos(a)*420,60,W-60);f.y=clamp(e.y+Math.sin(a)*420,60,H-60);f.z=clamp(e.z+300,0,ZMAX);f.vz=0;f.face=Math.atan2(e.y-f.y,e.x-f.x);
  enter(f,'engage');f.snapCd=0;const tx=e.x-Math.cos(f.face)*70,ty=e.y-Math.sin(f.face)*70;
  if(f.k.entrance==='axe'){f.leap=ms2t(300);f.leapFrom=[f.x,f.y];f.leapTo=[tx,ty];later(300,()=>{if(f.ko||!f.on)return;fx_dome(f.x,f.y,f.k.fx,4.5);fx_crack(f.x,f.y,4);fx_dust(f.x,f.y,14);shake=Math.max(shake,.9);flash(.25);if(!e.ko&&Math.hypot(e.x-f.x,e.y-f.y)<170)damage(f,e,f.k.entranceDmg||(kind==='rescue'?70:110),f.k.key==='sueko'?'B':'H');});}
  else snapTo(f,tx,ty,f.k.blink>.3,true,e.z);
  if(f.k.entrance==='oath')later(150,()=>{if(f.ko||!f.on)return;runFx(f,'oath',4.2);if(!e.ko&&Math.hypot(e.x-f.x,e.y-f.y)<190){damage(f,e,f.k.entranceDmg,'M');later(60,()=>damage(f,e,f.k.entranceDmg,'M'));}});
  // real kits: the character's own switch_in action (its FX play through fxlive.js)
  if(f.k.switchIn)later(60,()=>{if(f.ko||!f.on)return;startAct(f,f.k.switchIn,'special','switch_in');});
  else if(!f.k.entrance)later(140,()=>{if(f.ko||!f.on)return;fx_slash(f,4.6,f.k.fx,true);fx_ring(f.x,f.y,f.k.fx,3.5,.35);if(!e.ko&&Math.hypot(e.x-f.x,e.y-f.y)<160)damage(f,e,kind==='rescue'?60:90,'M');});
  s.tagCd=tick+ms2t(side===0?3000:7000);stats.tags[side]++;if(side===0||kind==='rescue')callout(kind==='rescue'?'RESCUE':'TAG',f.k.name+' cuts in',cssc(f.k.fx),.7,true);
  if(f.side===0)hudFor=-1;}
