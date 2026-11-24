'use strict';
/* Fighters: creation (mkFighter), per-tick update (updFighter), altitude (jumps / flight, gravity.js), wall / ground splats. */
function mkFighter(key,side){const k=KITS[key];const m=buildBody(k,key);
  return Object.assign(m,{key,k,side,x:0,y:0,vx:0,vy:0,face:0,face3:0,hp:k.hp,max:k.hp,ko:false,on:false,
    act:null,stun:0,stunKind:'',armor:0,gone:0,snap:null,snapCd:0,iframe:0,parry:0,block:0,reactCd:0,
    ni:0,lastNormal:-999,gapUntil:0,cds:{special:0,special2:0,ult:600},
    lastEnd:-999,lastWhiff:false,landedThisAct:false,lastLanded:-999,lastHurt:-999,hurts:[],
    tp:{intent:'neutral',since:0,until:0,n:0,done:0,mom:0,orbit:Math.random()<.5?1:-1,swayPh:rnd(0,TAU),swayMs:rnd(900,2200),feintKind:'dash_in',feintBit:false,openSeen:false,resetAng:0,punishReady:0,lastStart:0},
    manualUntil:0,label:null,bench:0,leap:0,h:0,flashT:0,jitT:0,recoil:0,stepT:Math.random()*.24,antic:0,dmgMul:1,spdMul:1,form:0,counterAt:0,strafe:0,beam:null,lx:0,ly:0,lean:0,trig:{},thr:{},dmgLog:[],lastAct2d:'',lastActTick:-999,stateUntil:0,retreatCd:0,retreatT:0,takenMul:1,orbitSwap:0,orbitDir:1,formChannel:-1,z:0,vz:0,zPref:0,zPrefT:0,zWant:0,manualZ:null,jumps:0,jumpCd:0,ffall:false,landT:0,jumpAfterSnap:false,mvx:0,mvy:0,spdLv:1});}
function setOn(f,on){f.on=on;f.g.visible=on;f.sh.visible=on;f.aline.visible=false;}
/* ================= per-fighter update ================= */
function updFighter(f){
  if(f.ko&&f.on&&f.z>0){f.vz-=JUMP.gravity*DT;f.z=Math.max(0,f.z+f.vz*DT);}
  if(!f.on||f.ko)return;const e=enemyOf(f);
  if(f.gone>0)f.gone--;if(f.iframe>0)f.iframe--;if(f.parry>0)f.parry--;if(f.block>0)f.block--;
  const started=f.startedNow||0;f.startedNow=0;const ended=f.justEnded;f.justEnded=false;
  const human=f.side===0&&level!=='watch';const handson=(f.side===0&&level==='handson')||!!e.phantom;   // no dummies: only your inputs
  if(!handson&&f.k.rhythm!==false)think(f,e,started,ended);
  if(f.stun>0){f.stun--;}
  if(f.key==='puck'&&f.form<2&&f.hp/f.max<(f.form===0?.6:.3)){f.form++;f.dmgMul=f.form===1?1.12:1.25;f.spdMul=f.form===1?1.15:1.3;f.aura.visible=true;
    f.aura.children.forEach(c=>c.material.color.setHex(f.form===2?0x9fe0ff:0xffd24a));fx_dome(f.x,f.y,0xffd24a,4);flash(.3);shake=Math.max(shake,.6);hitstopMs=Math.max(hitstopMs,120);
    if(f.on)callout(f.form===1?'TRANSFORM':'TRANSFORM II',f.k.name+' powers up',cssc(f.k.fx),.9);}
  if(f.k.berserk){const lost=1-f.hp/f.max,B=f.k.berserk;const x=clamp(lost/B.maxLost,0,1);const q=Math.floor((Math.exp(3*x)-1)/(Math.exp(3)-1)*B.steps)/B.steps;f.dmgMul=1+B.bonus*q;f.aura.visible=q>0;if(q>0)f.aura.children.forEach(c=>c.material.color.setHex(0x9a9a9a));}
  if(f.k.forms){const nx=f.k.forms[f.form||0];if(nx&&f.hp/f.max<nx.at&&f.formChannel<0&&!f.stun){if(f.act)endAct(f);f.formChannel=f.form||0;startAct(f,f.k.transform,'transform','transform');if(f.on)callout('TRANSFORM',f.k.name+' changes form','#'+nx.aura.toString(16).padStart(6,'0'),.9);}
    if(f.formChannel>=0&&!f.act){const F=f.k.forms[f.formChannel];f.form=f.formChannel+1;f.formChannel=-1;f.spdMul=F.spd;f.dmgMul=F.dmg;f.takenMul=F.taken;f.mat.color.setHex(F.col);f.aura.visible=true;f.aura.children.forEach(c=>c.material.color.setHex(F.aura));fx_dome(f.x,f.y,F.aura,5);flash(.35);shake=Math.max(shake,.8);hitstopMs=Math.max(hitstopMs,150);}}
  if(f.k.retreat&&f.retreatCd<=tick&&!f.act&&f.stun<=0){const R=f.k.retreat;const from=tick-ms2t(R.ms);if(f.dmgLog.filter(x=>x[0]>from).reduce((a,x)=>a+x[1],0)>=R.hp){f.dmgLog.length=0;f.retreatCd=tick+ms2t(R.cd+R.dur);
    const a=Math.atan2(f.y-e.y,f.x-e.x)+rnd(-.3,.3);f.snapCd=0;f.snap={tx:clamp(f.x+Math.cos(a)*520,30,W-30),ty:clamp(f.y+Math.sin(a)*520,30,H-30),v:3000*(f.spdMul||1),blink:false,sx:f.x,sy:f.y};stats.snaps[f.side]++;metr.snaps.push([tick,f.side]);
    for(let i=0;i<10;i++)later(i*48,()=>{if(!f.on||f.ko||e.ko)return;const b=Math.atan2(e.y-f.y,e.x-f.x)+rnd(-.2,.2);shoot(f,Math.cos(b)*1500,Math.sin(b)*1500,5,.11);});}}
  if(f.counterAt&&tick>=f.counterAt&&!f.act&&f.stun<=0&&!f.snap){f.counterAt=0;if(f.k.react&&f.k.react.counter==='normal2'){startAct(f,f.k.normals[1],'normal','N2');f.ni=2;f.lastNormal=tick;}
    else if(f.cds.special<=tick&&!(f.side===0&&level==='handson')){startAct(f,f.k.special,'special','special');f.cds.special=tick+ms2t(f.k.special.cd);stats.used[f.side].special++;}else{enter(f,'punish');f.gapUntil=0;}}
  if(f.strafe>0){f.strafe--;const a=Math.atan2(e.y-f.y,e.x-f.x)+Math.PI/2*f.strafeDir;f.x+=Math.cos(a)*420*DT;f.y+=Math.sin(a)*420*DT;}
  if(f.beam){f.beam.left--;const b=f.beam.m;const st=V(f.x+Math.cos(f.face)*35,f.y+Math.sin(f.face)*35,1.15);const dir=new THREE.Vector3(Math.cos(f.face),0,Math.sin(f.face));b.position.copy(st).addScaledVector(dir,11);
    b.scale.set(1+Math.sin(tick)*.12,22,1+Math.sin(tick)*.12);b.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir);shake=Math.max(shake,.2);if(f.beam.left<=0||!f.act||f.ko){scene.remove(b);f.beam=null;}}
  // leap (ult)
  if(f.leap>0){f.leap--;f.leapT=f.leapT||f.leap+1;const u=1-f.leap/f.leapT;if(f.leap<=0)f.leapT=0;f.x=f.leapFrom[0]+(f.leapTo[0]-f.leapFrom[0])*u;f.y=f.leapFrom[1]+(f.leapTo[1]-f.leapFrom[1])*u;f.h=Math.sin(u*Math.PI)*5;}else f.h=0;
  // action timeline
  if(f.act){const a=f.act;const tms=a.t*TICK;
    if(f.mv3)mv3Step(f,a);   // FX Studio 3D movement (fxlive.js)
    if(a.def.lunge&&!a.def.move3d)while(a.li<a.def.lunge.length&&a.def.lunge[a.li][0]<=tms){const L=a.def.lunge[a.li++];const d=Math.hypot(e.x-f.x,e.y-f.y);const want=Math.min(L[1],Math.max(0,d-f.k.reach*.55));if(want>15){const ang=Math.atan2(e.y-f.y,e.x-f.x);f.snapCd=0;snapTo(f,f.x+Math.cos(ang)*want,f.y+Math.sin(ang)*want,false,true,e.z);}}
    while(a.fi<a.def.fx.length&&a.def.fx[a.fi][0]<=tms){const F=a.def.fx[a.fi++];runFx(f,F[1],F[2]);if(!f.act)break;}
    if(f.act===a&&a.def.hits)while(a.hi<a.def.hits.length&&a.def.hits[a.hi][0]<=tms){const h=a.def.hits[a.hi++];if(training&&f.side===0&&h[3]>0)trainDummies().forEach(t=>hitResolve(f,t,h));else hitResolve(f,e,h);if(!f.act)break;}
    if(f.act===a){a.t++;if(a.t*TICK>=a.def.dur){endAct(f);}}}
  // movement: drift & snap, intent-driven
  const free=!f.act&&f.stun<=0&&!f.snap&&f.gone<=0&&f.leap<=0;
  let mx=0,my=0,drift=0,lv=1;
  if(f.side===0&&human&&inputDir&&playerDriven(f)){lv=playerLv(f);mx=inputDir[0];my=inputDir[1];drift=f.k.speed*1.25*lvMul(f,lv);f.manualUntil=tick+ms2t(600);}
  else if(!handson&&!(f.side===0&&tick<f.manualUntil)){const sty=styleTarget(f,e);const tgt=sty||moveTarget(f,e);if(tgt){const dx=tgt[0]-f.x,dy=tgt[1]-f.y,d=Math.hypot(dx,dy);
      const it=sty?'style':f.tp.intent;
      if(free&&(d>170||(f.k.blink>.5&&d>f.k.reach*1.3))&&['engage','punish','reset','feint','pressure'].includes(it)&&f.snapCd<=tick&&Math.random()<.35){const over=Math.min(d,rnd(260,520));snapTo(f,f.x+dx/d*over,f.y+dy/d*over,Math.random()<f.k.blink,false,['engage','punish','pressure'].includes(it)?e.z:f.zWant);}
      else if(d>4){lv=aiLv(f,it,d);mx=dx/d;my=dy/d;drift=f.k.speed*(sty?sty[2]:(SPEEDMUL[it]||1))*(burst()?1.15:1)*lvMul(f,lv)*Math.min(1,d/(['engage','pressure','punish'].includes(it)?30:90));}}
    // ranged kiting: too close -> snap away
    if(!f.k.melee&&free&&Math.hypot(e.x-f.x,e.y-f.y)<130&&f.snapCd<=tick&&Math.random()<.2){const a=Math.atan2(f.y-e.y,f.x-e.x)+rnd(-.7,.7);snapTo(f,f.x+Math.cos(a)*360,f.y+Math.sin(a)*360,Math.random()<f.k.blink);}}
  if(f.act&&f.act.kind!=='ult'){drift*=.25;lv=1;}if(f.stun>0||f.gone>0||f.mv3)drift=0;
  // continuous movement at three speed levels (sprint.js; Daniel 2026-11-24: no more step-and-plant stop-start)
  moveStep(f,drift>0?mx:0,drift>0?my:0,drift>0?drift*(f.spdMul||1):0,lv);
  stepSnap(f);
  updAltitude(f,e);
  // knockback slide (in the air it carries much further: fighters fly across the arena)
  f.x+=f.vx*DT;f.y+=f.vy*DT;const fr=Math.exp(-(f.z>25&&f.stun>0?GRAV.airFric:GRAV.groundFric)*DT);f.vx*=fr;f.vy*=fr;
  if(f.x<20||f.x>W-20){const sp=Math.abs(f.vx);f.x=clamp(f.x,20,W-20);if(sp>700&&f.stun>0){wallSplat(f);}f.vx*=-.3;}
  if(f.y<20||f.y>H-20){const sp=Math.abs(f.vy);f.y=clamp(f.y,20,H-20);if(sp>700&&f.stun>0){wallSplat(f);}f.vy*=-.3;}
  // facing
  if(!f.snap||f.act){const want=f.mv3&&f.mv3.plan.face==='travel'&&f.mv3.dir!=null?f.mv3.dir:e.phantom?(mx||my?Math.atan2(my,mx):f.face):Math.atan2(e.y-f.y,e.x-f.x);let d=((want-f.face+Math.PI)%TAU+TAU)%TAU-Math.PI;f.face+=d*.35;}
  // attacks
  if(!handson&&!(f.side===0&&f.manualNoAttack))tryAttack(f,e,false);
  autoReact(f,e);
  parryTick(f);}   // AI parry roll on incoming shots (parry.js)
function groundSplat(f){f.stun=Math.max(f.stun,ms2t(800));f.hp=Math.max(0,f.hp-50);fx_crack(f.x,f.y,5);planetCrater(f.x,f.y,2.2);planetBlast(f.x,f.y,0,120,40);fx_dome(f.x,f.y,0xffc857,4);fx_dust(f.x,f.y,16);shake=Math.max(shake,1);hitstopMs=Math.max(hitstopMs,110);callout('GROUND SPLAT','','#ffc857',.6,true);director.hits++;if(f.hp<=0)ko(f);}
// Altitude. Ground fighters (everyone for now): jumps, double jumps and gravity (gravity.js groundAltitude).
// Flight fighters (kit.flight): attack intents close the height gap to the target; neutral / reset spread out
// vertically; big height changes are 3D snaps; R / F (held) climb / descend and the height stays where you let go;
// when stunned in the air a flyer falls (launch / spike / splat).
function updAltitude(f,e){
  if(!canFly(f)){groundAltitude(f,e);return;}
  const ceil=ZMAX;
  if(tick>=f.zPrefT){f.zPrefT=tick+ms2t(rnd(1200,3500));const r=Math.random();f.zPref=r<.22?0:r<.55?rnd(150,500):rnd(500,ZMAX*(burst()?1:.8));}
  const it=f.tp.intent,d=Math.hypot(f.x-e.x,f.y-e.y);let want;
  if(f.side===0&&f.manualZ!=null)want=f.manualZ;
  else if(f.side===0&&level==='handson')want=f.z;
  else if(f.k.rhythm===false)want=d>=500?e.z+240*Math.sin(tick*DT*1.3):e.z;
  else if(['engage','pressure','punish'].includes(it))want=e.z;
  else if(it==='neutral')want=e.z*.5+f.zPref*.5+70*Math.sin(tick*DT*1.7+f.tp.swayPh);
  else want=f.zPref;
  if(!f.k.melee&&it!=='punish')want=Math.max(want,e.z+180);
  want=clamp(want,0,ZMAX);const rawWant=want;want=Math.min(want,ceil);f.zWant=want;f.zWantRaw=rawWant;
  if(f.snap||f.leap>0||f.mv3)return;
  if(f.stun>0||f.vz>900||f.vz<-900){f.vz-=JUMP.gravity*DT;f.z+=f.vz*DT;if(f.z<=0){if(f.vz<-GRAV.splat&&f.stun>0)groundSplat(f);f.z=0;f.vz=f.vz<-700?-f.vz*GRAV.bounce:0;}if(f.z>ZMAX+200){f.z=ZMAX+200;f.vz=Math.min(0,f.vz);}return;}
  const dz=want-f.z;const manual=f.side===0&&f.manualZ!=null;
  // big height change = a 3D snap
  if(!manual&&Math.abs(rawWant-f.z)>280&&!f.act&&f.snapCd<=tick&&Math.random()<.25){snapTo(f,f.x+rnd(-80,80),f.y+rnd(-80,80),Math.random()<f.k.blink,false,rawWant);return;}
  const vmax=f.k.speed*(manual?2.2:1.7)*(f.spdMul||1);f.vz=clamp(dz*7,-vmax,vmax);f.z=clamp(f.z+f.vz*DT,0,Math.max(ceil,0));}
function wallSplat(f,name){f.vx=f.vy=0;f.stun=Math.max(f.stun,ms2t(700));f.hp=Math.max(0,f.hp-40);fx_ring(f.x,f.y,0xffc857,3,.35,1);fx_sparks(f.x,f.y,0xffc857,26,8);fx_dust(f.x,f.y,8);shake=Math.max(shake,.7);hitstopMs=Math.max(hitstopMs,(90));callout(name||'WALL SPLAT','','#ffc857',.6,true);director.hits++;if(f.hp<=0)ko(f);}
