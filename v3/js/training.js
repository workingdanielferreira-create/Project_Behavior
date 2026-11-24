'use strict';
/* Training mode (Daniel 2026-11-23): your one fighter alone on the field with practice dummies, no opponent team.
   Dummies are placed on a top-down map (Training screen, menus.js) and kept in settings.training:
     {fighter: your character, dummies: [{x, y, z (height, 2D px), beh, kit}]}
   Behaviour per dummy: 'stand' = never moves or acts (no parries), 'guard' = blocks every hit and parries by chance
   (AI parry roll), 'fight' = a light AI of its character (normal AI, deals half damage) that fights you.
   Nobody can be K.O.'d: HP refills after REFILL_MS without being hit (you too). A knocked-back stand / guard dummy
   drifts back to its spot after HOME_MS. Your target = the nearest dummy (sides[1].on, picked every tick): that is
   the one your FX hit (FX Studio's runtime has one hurt box); shots and the stand-in kits' melee hits reach every
   dummy. No dummies = an invisible stand-in target (phantom): your fighter only acts on your inputs then. */
const TRAIN={maxDummies:8,refillMs:1500,refillPerS:1.2,homeMs:1000,comboGapMs:1100,fightDmg:.5};
const TRAIN_BEH=[['stand','Stand'],['guard','Guard'],['fight','Fight back']];
const TRAIN_START=[MX0+MAPW*.46,MY0+MAPH*.5];   // sim px (dummy entries are saved in map px: 0..MAPW x 0..MAPH)
let training=false;
const trainLog={combo:0,comboDmg:0,last:-1e9,lastDmg:0,best:0,bestDmg:0,recent:[]};

function trainDefaults(){return {fighter:'',dummies:[{x:MAPW*.58,y:MAPH*.5,z:0,beh:'stand',kit:''}]};}
function trainCfg(){let T=settings.training;if(!T||typeof T!=='object'||!Array.isArray(T.dummies)){T=settings.training=trainDefaults();}
  return T;}
function trainFighterKey(){const T=trainCfg();return KITS[T.fighter]?T.fighter:validTeam(settings.teams[0],DEFAULT_SETTINGS.teams[0])[0];}
function trainDummyKit(d){return KITS[d.kit]?d.kit:validTeam(settings.teams[1],DEFAULT_SETTINGS.teams[1])[0];}
function trainDummyList(){return trainCfg().dummies.filter(d=>d&&isFinite(d.x)&&isFinite(d.y)).slice(0,TRAIN.maxDummies);}

// A dummy fighter from its saved entry (index n = its number on the map / HUD).
function mkDummy(d,n){const f=mkFighter(trainDummyKit(d),1);const beh=TRAIN_BEH.some(b=>b[0]===d.beh)?d.beh:'stand';
  f.dummy={beh,n,home:[MX0+clamp(d.x,60,MAPW-60),MY0+clamp(d.y,60,MAPH-60),clamp(+d.z||0,0,ZMAX)]};
  f.x=f.dummy.home[0];f.y=f.dummy.home[1];f.z=f.dummy.home[2];
  // stand / guard dummies wear a greyed version of their colour, so they read as dummies
  if(beh!=='fight'&&f.mat){const c=f.k.col,g=0x8a90a6,mix=(s)=>Math.round((((c>>s)&255)*.35+((g>>s)&255)*.65))<<s;f.mat.color.setHex(mix(16)|mix(8)|mix(0));}
  setOn(f,true);return f;}
function mkPhantom(key){const f=mkFighter(key,1);f.phantom=true;f.dummy={beh:'stand',n:0,home:[0,0,0]};setOn(f,true);f.gone=1e9;f.g.visible=false;f.sh.visible=false;return f;}
function trainDummies(){return sides[1].team.filter(d=>!d.phantom);}
function trainPlayer(){return sides[0].team[0];}

function newTraining(){clearAll();planetReset();trackReset();training=true;
  const pk=trainFighterKey();sides[0].team=[mkFighter(pk,0)];
  buildDummies(pk);
  const p=trainPlayer();setOn(p,true);p.x=TRAIN_START[0];p.y=TRAIN_START[1];p.face=0;enter(p,'neutral');
  sides.forEach(s=>s.tagCd=0);sides[0].on=0;
  tick=0;hitstopMs=0;slowmo=0;shake=0;ended=false;Object.assign(director,{I:0,phase:'calm',left:0,at:.8,quiet:0,hits:0,dmg:0,cnt:0,taken:0,ko:0});
  for(const k in metr)metr[k]=[];
  stats={starts:[0,0],used:[{normal:0,special:0,special2:0,ult:0},{normal:0,special:0,special2:0,ult:0}],snaps:[0,0],dealt:[0,0],kos:[0,0],tags:[0,0],parries:[0,0],perfect:0,inputs:0,pSnaps:0,pChains:0,pSkills:0,pIntents:0,pTags:0,actions:0,t0:0,pParries:0,perfectParries:0};
  Object.assign(trainLog,{combo:0,comboDmg:0,last:-1e9,lastDmg:0,best:0,bestDmg:0,recent:[]});
  sides.forEach(s=>s.team.forEach(f=>{f._ls=0;}));hudFor=-1;trainPickTarget();
  sides.forEach(s=>s.team.forEach(f=>sync(f,0)));}
function buildDummies(pk){const list=trainDummyList();sides[1].team=list.map((d,i)=>mkDummy(d,i+1));
  if(!sides[1].team.length)sides[1].team=[mkPhantom(pk||trainFighterKey())];
  sides[1].on=0;const p=trainPlayer();sides[1].team.forEach(d=>{if(p)d.face=Math.atan2(p.y-d.y,p.x-d.x);enter(d,'neutral');});}
// Training screen closed while training runs: the dummies are rebuilt from the map, your fighter keeps its state
// (a different fighter picked = a fresh start).
function trainApply(){if(!training||!running)return;
  if(trainPlayer().key!==trainFighterKey()){newTraining();return;}
  for(const d of sides[1].team){fxClear(d);if(d.aline)scene.remove(d.aline);if(d.beam){scene.remove(d.beam.m);d.beam=null;}scene.remove(d.g);scene.remove(d.sh);}
  for(let i=shots.length-1;i>=0;i--)if(shots[i].side===1){scene.remove(shots[i].m);shots.splice(i,1);}
  labels.forEach(l=>l&&l.remove());labels.length=0;
  buildDummies();trainPickTarget();sides[1].team.forEach(f=>sync(f,0));hudFor=-1;}

// Your target: the nearest dummy (3D distance).
function trainPickTarget(){const p=trainPlayer();if(!p)return;let bi=0,bd=1e18;
  sides[1].team.forEach((d,i)=>{if(d.phantom)return;const dd=Math.hypot(d.x-p.x,d.y-p.y,d.z-p.z);if(dd<bd){bd=dd;bi=i;}});sides[1].on=bi;}
// Who a side's shots / melee hits can reach this tick.
function foesOf(side){if(training&&side===0)return trainDummies();const s=sides[1-side];const t=s.team[s.on];return t?[t]:[];}

// Stand / guard dummy tick (fight-back dummies run the normal updFighter). The phantom only sits in front of you.
function updDummy(f){const D=f.dummy,p=trainPlayer();
  if(f.phantom){f.x=clamp(p.x+900,20,W+2000);f.y=p.y;f.z=p.z;return;}
  if(f.iframe>0)f.iframe--;if(f.parry>0)f.parry--;
  if(f.stun>0)f.stun--;
  f.act=null;f.snap=null;
  // knockback slide (as updFighter), walls
  f.x+=f.vx*DT;f.y+=f.vy*DT;const fr=Math.exp(-(f.z>25&&f.stun>0?GRAV.airFric:GRAV.groundFric)*DT);f.vx*=fr;f.vy*=fr;
  if(f.x<20||f.x>W-20){const sp=Math.abs(f.vx);f.x=clamp(f.x,20,W-20);if(sp>700&&f.stun>0)wallSplat(f);f.vx*=-.3;}
  if(f.y<20||f.y>H-20){const sp=Math.abs(f.vy);f.y=clamp(f.y,20,H-20);if(sp>700&&f.stun>0)wallSplat(f);f.vy*=-.3;}
  // height: thrown / stunned = gravity; otherwise it hangs where it is, then floats back to its placed HEIGHT only:
  // it stays where a knockback left it on the ground (Daniel 2026-11-24; Restart training puts it back on its map spot)
  if(f.stun>0||f.vz>1){f.vz-=JUMP.gravity*DT;f.z+=f.vz*DT;if(f.z<=0){const vz=f.vz;f.z=0;if(vz<-GRAV.splat&&f.stun>0)groundSplat(f);f.vz=f.stun>0&&vz<-700?-vz*GRAV.bounce:0;}if(f.z>ZMAX+200){f.z=ZMAX+200;f.vz=Math.min(0,f.vz);}}
  else{f.vz=0;if(tick-f.lastHurt>ms2t(TRAIN.homeMs)){const u=1-Math.exp(-3*DT);f.z+=(D.home[2]-f.z)*u;}}
  // guard: blocks every hit while it stands (AI parry rolls on top, parry.js)
  f.block=D.beh==='guard'&&f.stun<=0?ms2t(120):0;
  const want=Math.atan2(p.y-f.y,p.x-f.x);let d=((want-f.face+Math.PI)%TAU+TAU)%TAU-Math.PI;f.face+=d*.2;
  if(D.beh==='guard')parryTick(f);}

// HP refill after a pause without being hit (no K.O.s in training).
function trainRefill(){for(const s of sides)for(const f of s.team){if(f.phantom||!f.on)continue;
  if(f.hp<f.max&&tick-f.lastHurt>ms2t(TRAIN.refillMs))f.hp=Math.min(f.max,f.hp+f.max*TRAIN.refillPerS*DT);}}

// Your hits on dummies: combo (hits no more than comboGapMs apart), its damage, best, last hit, damage per second (5 s).
function trainNoteHit(a,t,dm){if(!training||a.side!==0||!t.dummy)return;const L=trainLog;
  if(tick-L.last>ms2t(TRAIN.comboGapMs)){L.combo=0;L.comboDmg=0;}
  L.combo++;L.comboDmg+=dm;L.last=tick;L.lastDmg=dm;L.recent.push([tick,dm]);
  if(L.combo>L.best||(L.combo===L.best&&L.comboDmg>L.bestDmg)){L.best=L.combo;L.bestDmg=L.comboDmg;}}
function trainSimTick(){trainPickTarget();const p=trainPlayer();
  updFighter(p);
  for(const d of sides[1].team){if(d.phantom||d.dummy.beh!=='fight')updDummy(d);else updFighter(d);}
  fxTick(p);for(const d of sides[1].team)if(!d.phantom)fxTick(d);
  trainRefill();}
function trainDummyName(f){return 'DUMMY '+f.dummy.n+' · '+(TRAIN_BEH.find(b=>b[0]===f.dummy.beh)||['',''])[1].toUpperCase()+' · '+f.k.name;}
function trainHud(){const L=trainLog,el=$('trn');if(!el)return;
  const live=tick-L.last<=ms2t(TRAIN.comboGapMs);const from=tick-ms2t(5000);L.recent=L.recent.filter(r=>r[0]>from);
  const dps=L.recent.reduce((s,r)=>s+r[1],0)/Math.min(5,Math.max(1,tick*DT));
  const html='<b>TRAINING</b><span class="'+(live?'hot':'')+'">Combo <em>'+L.combo+'</em> hits · '+Math.round(L.comboDmg)+' dmg</span>'+
    '<span>Best <em>'+L.best+'</em> · '+Math.round(L.bestDmg)+'</span><span>Last hit '+Math.round(L.lastDmg)+'</span><span>DPS (5 s) '+Math.round(dps)+'</span>';
  if(el.innerHTML!==html)el.innerHTML=html;}
function trainBegin(){newTraining();running=true;paused=false;Menu.close();host.focus();document.body.classList.add('playing','training');
  const n=trainDummies().length;callout('TRAINING',n?n+' dumm'+(n===1?'y':'ies')+' · Esc for Training settings':'No dummies · Esc for Training settings','#e8ecfb',1.4);}
