'use strict';
/* Main: fixed-tick game loop, fight flow (new / end / pause / title), boot. */
/* ================= loop ================= */
function simTick(){
  tick++;
  for(let i=lat.length-1;i>=0;i--){if(lat[i].t<=tick){const l=lat.splice(i,1)[0];l.fn();}}
  inputDir=readDir();
  {const f=sides[0].team[sides[0].on];if(f&&level!=='watch'&&canFly(f)){   // flyers: R / F climb / descend (ground fighters jump: input.js)
  if(keys.KeyR){f.manualZ=clamp(f.z+500,0,ZMAX);}else if(keys.KeyF){f.manualZ=clamp(f.z-500,0,ZMAX);}else if(f.manualZ!=null){f.manualZ=f.z;f.manualZT=(f.manualZT||0)+1;if(f.manualZT>ms2t(700)){f.manualZ=null;f.manualZT=0;}}if(keys.KeyR||keys.KeyF)f.manualZT=0;}}
  const [a,b]=onField();
  // started counters for tempo
  [a,b].forEach(f=>{const n=stats.starts[f.side];f.startedNow=n-(f._ls||0);f._ls=n;});
  if(training)trainSimTick();   // training.js: you + every dummy
  else{updFighter(a);updFighter(b);
  fxTick(a);fxTick(b);}   // real kits' FX laid in 3D (fxlive.js / fx3d.js)
  if(a.bufChain&&!a.act){a.bufChain=false;tryAttack(a,b,true);}
  if(a.buf){if(tick>a.buf.until){const c=a.buf.code;a.buf=null;deny(c);}else if(!(a.act||a.stun>0||a.gone>0||a.snap)){const c=a.buf.code;a.buf.until=tick;command(c,true);a.buf=null;}}
  stepShots();
  planetTick();   // planet.js: pillars / scenery / landmarks vs fighters, trenches
  for(let i=fieldBlades.length-1;i>=0;i--){const b=fieldBlades[i];if(tick>b.until){scene.remove(b.m);fieldBlades.splice(i,1);}}
  stepDirector();
  // enemy AI tagging
  const s1=sides[1];if(!training&&s1.tagCd<=tick&&!b.ko&&b.hp/b.max<.35&&!b.act&&Math.random()<.01){const opts=[0,1,2].filter(i=>i!==s1.on&&!s1.team[i].ko&&s1.team[i].hp/s1.team[i].max>.5);if(opts.length)tagIn(1,opts[0],'tag');}
  // AI tagging for player side in watch mode
  const s0=sides[0];if(!training&&level==='watch'&&s0.tagCd<=tick&&!a.ko&&a.hp/a.max<.35&&!a.act&&Math.random()<.01){const opts=[0,1,2].filter(i=>i!==s0.on&&!s0.team[i].ko&&s0.team[i].hp/s0.team[i].max>.5);if(opts.length)tagIn(0,opts[0],'tag');}
  // bench regen
  sides.forEach(s=>s.team.forEach((g,i)=>{if(i!==s.on&&!g.ko)g.hp=Math.min(g.max,g.hp+g.max*.01*DT);}));
  // metrics
  if(!a.ko&&!b.ko){metr.dist.push([tick,Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)/BODY]);metr.both.push([tick,!!(a.act&&b.act)]);}
  metr.burst.push([tick,burst()]);
  if(tick%2===0)floaters.forEach(o=>{o.m.position.y=o.y+Math.sin(tick*DT*.6+o.ph)*.4;o.m.rotation.y+=.002;});
  if(tick%600===0)for(const k in metr){const cut=tick-ms2t(60000);metr[k]=metr[k].filter(r=>(Array.isArray(r)?r[0]:r)>cut);}
}
let last=performance.now(),acc2=0;
function frame(now){requestAnimationFrame(frame);const rdt=Math.min(.05,(now-last)/1000);last=now;
  try{
    if(running&&!paused&&!ended){
      let sp=pace;if(slowmo>0){sp*=.35;}
      if(hitstopMs>0){hitstopMs-=rdt*1000;}else{acc2+=rdt*1000*sp;let n=0;while(acc2>=TICK&&n<4){acc2-=TICK;simTick();n++;if(slowmo>0)slowmo--;}if(n>=4)acc2=0;}
      stepFx(rdt*Math.max(.4,sp));stepNums(rdt);sides.forEach(s=>s.team.forEach(f=>sync(f,rdt)));planetFrame(rdt*Math.max(.4,sp));camStep(rdt);fxDraw();hud(rdt);
    }else if(!running){planetFrame(rdt,true);camStep(rdt,true);}
  }catch(err){console.error(err);}
  renderer.render(scene,cam);}

/* ================= flow ================= */
// Game flow: new fight, end of fight, pause, back to the title. The screens
// themselves live in menus.js; this file only says which one to open.
function clearAll(){sides.forEach(s=>s.team.forEach(fxClear));sides.forEach(s=>s.team.forEach(f=>f.aline&&scene.remove(f.aline)));fieldBlades.forEach(b=>scene.remove(b.m));fieldBlades.length=0;sides.forEach(s=>s.team.forEach(f=>{scene.remove(f.g);scene.remove(f.sh);}));shots.forEach(s=>scene.remove(s.m));shots.length=0;fxs.forEach(f=>scene.remove(f.o));fxs.length=0;lat.length=0;labels.forEach(l=>l&&l.remove());labels.length=0;nums.forEach(n=>n.el.remove());nums.length=0;sides.forEach(s=>s.team.forEach(f=>{if(f.beam){scene.remove(f.beam.m);f.beam=null;}}));}
function newGame(){clearAll();planetReset();trackReset();training=false;document.body.classList.remove('training');
  const T0=validTeam(settings.teams[0],DEFAULT_SETTINGS.teams[0]),T1=validTeam(settings.teams[1],DEFAULT_SETTINGS.teams[1]);
  sides[0].team=T0.map(k=>mkFighter(k,0));sides[1].team=T1.map(k=>mkFighter(k,1));
  // A character on both teams: the enemy copy wears its alternate colours.
  sides[1].team.forEach(f=>{if(T0.includes(f.key)){const alt=ALT[f.key]||altColours(f.k);f.k=Object.assign({},f.k,alt);f.mat.color.setHex(alt.col);}});
  sides.forEach((s,si)=>{s.on=0;s.tagCd=0;s.team.forEach((f,i)=>{setOn(f,i===0);f.x=MX0+MAPW*(si?.54:.46);f.y=MY0+MAPH*.5+rnd(-60,60);f.face=si?Math.PI:0;enter(f,'neutral');});});
  tick=0;hitstopMs=0;slowmo=0;shake=0;ended=false;Object.assign(director,{I:0,phase:'calm',left:0,at:.8,quiet:0,hits:0,dmg:0,cnt:0,taken:0,ko:0});
  for(const k in metr)metr[k]=[];
  stats={starts:[0,0],used:[{normal:0,special:0,special2:0,ult:0},{normal:0,special:0,special2:0,ult:0}],snaps:[0,0],dealt:[0,0],kos:[0,0],tags:[0,0],parries:[0,0],perfect:0,inputs:0,pSnaps:0,pChains:0,pSkills:0,pIntents:0,pTags:0,actions:0,t0:0,pParries:0,perfectParries:0};
  sides.forEach(s=>s.team.forEach(f=>{f._ls=0;}));hudFor=-1;
  // Idle pose for the title backdrop: fighters placed, drawn once.
  sides.forEach(s=>s.team.forEach(f=>sync(f,0)));}
function validTeam(t,def){return [0,1,2].map(i=>(t&&KITS[t[i]])?t[i]:def[i]);}
function endGame(win){if(ended)return;ended=true;const secs=(tick*DT).toFixed(0);
  const rows=[['Fight length',secs+' s'],['Your inputs',stats.inputs],['  Snaps · chains · skills',stats.pSnaps+' · '+stats.pChains+' · '+stats.pSkills],['  Intent calls · tags',stats.pIntents+' · '+stats.pTags],['Perfect snaps',stats.perfect],['Your parries · perfect',stats.pParries+' · '+stats.perfectParries],['Parries (you · enemy)',stats.parries[0]+' · '+stats.parries[1]],['Damage dealt (you · enemy)',Math.round(stats.dealt[0])+' · '+Math.round(stats.dealt[1])],['K.O.s (you · enemy)',stats.kos[1]+' · '+stats.kos[0]]];
  setTimeout(()=>Menu.results(win,rows),800);}
function setPaused(v){if(!running||ended)return;paused=v;if(v)Menu.show('pause',true);else{Menu.close();host.focus();}}
function begin(){newGame();running=true;paused=false;Menu.close();host.focus();document.body.classList.add('playing');
  callout('FIGHT',level==='watch'?'Watching AI vs AI':'The AI fights; your inputs take over','#e8ecfb',1.6);}
function toTitle(){running=false;paused=false;ended=false;document.body.classList.remove('playing');newGame();Menu.show('title',true);}
function setLevel(v){level=v;settings.level=v;saveSettings();if(running&&!ended)callout(v==='watch'?'Watch':v==='commander'?'Commander':'Hands-on',v==='watch'?'AI vs AI':v==='commander'?'AI fights, your inputs take over':'Your fighter acts only when you press','#e8ecfb',.8,true);}
function setCam(v){camMode=v;settings.cam=v;saveSettings();cut.t=0;if(running&&!ended)callout('Camera: '+(v==='shoulder'?'over the shoulder':v),'','#e8ecfb',.6,true);}
function setPace(pct){settings.pace=pct;pace=pct/100;saveSettings();}

/* ================= boot ================= */
level=settings.level;camMode=settings.cam;pace=settings.pace/100;applyQuality();
loadGlbBody(()=>{newGame();Menu.show('title',true);requestAnimationFrame(frame);});   // the .glb body parses async
// Debug hook (console): __pt.s for a live snapshot.
const ish={};setInterval(()=>{if(!running||paused||ended)return;const [a,b]=onField();[a,b].forEach(f=>{const k=f.k.short+':'+f.tp.intent;ish[k]=(ish[k]||0)+1;});},50);
window.__pt={ish,cam:v=>setCam(v),get s(){const [a,b]=onField();return {tick,z:[Math.round(a.z),Math.round(b.z)],ended,hp:[a.hp,b.hp],on:[a.k.short,b.k.short],intent:[a.tp.intent,b.tp.intent],dir:director.phase,I:director.I.toFixed(2),stats,feel:$('feel').innerText};},level:v=>setLevel(v),pace:v=>{pace=v;}};
