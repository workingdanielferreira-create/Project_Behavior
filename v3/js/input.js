'use strict';
/* Input: keyboard state, camera-relative WASD, commands (snap, chain, skills, intents, tag, jump / fast fall or fly, camera, control level). */
/* ================= input ================= */
const keys={};let inputDir=null;const GAMEK={KeyR:1,KeyF:1,KeyC:1,KeyW:1,KeyA:1,KeyS:1,KeyD:1,ArrowUp:1,ArrowDown:1,ArrowLeft:1,ArrowRight:1,Space:1,KeyJ:1,KeyK:1,KeyL:1,KeyI:1,Digit1:1,Digit2:1,Digit3:1,Digit4:1,KeyQ:1,KeyE:1,Tab:1,Escape:1,KeyP:1};
function readDir(){let x=0,y=0;if(keys.KeyW||keys.ArrowUp)y-=1;if(keys.KeyS||keys.ArrowDown)y+=1;if(keys.KeyA||keys.ArrowLeft)x-=1;if(keys.KeyD||keys.ArrowRight)x+=1;const l=Math.hypot(x,y);if(!l)return null;x/=l;y/=l;
  // camera-relative: W = away from the camera along the ground
  const fx=camLook.x-cam.position.x,fz=camLook.z-cam.position.z,fl=Math.hypot(fx,fz)||1;const F=[fx/fl,fz/fl],Rt=[-F[1],F[0]];return [F[0]*(-y)+Rt[0]*x,F[1]*(-y)+Rt[1]*x];}
window.addEventListener('keydown',ev=>{if(Menu.isOpen()||!running||ended||!GAMEK[ev.code])return;ev.preventDefault();if(ev.code==='Escape'||ev.code==='KeyP'){setPaused(!paused);return;}if(paused)return;if(ev.code==='Space'&&ev.ctrlKey){if(!ev.repeat)command('Parry');return;}keys[ev.code]=true;if(ev.repeat)return;command(ev.code);});
window.addEventListener('keyup',ev=>{keys[ev.code]=false;});
window.addEventListener('blur',()=>{for(const k in keys)keys[k]=false;if(running&&!ended)setPaused(true);});
function command(code,retry){const f=sides[0].team[sides[0].on];if(!f||f.ko)return;const e=enemyOf(f);
  const busy=()=>!!(f.act||f.stun>0||f.gone>0||f.snap||f.leap>0);
  const fail=c=>{if(!retry&&busy()){f.buf={code:c,until:tick+ms2t(400)};return;}if(!retry||tick>=(f.buf&&f.buf.until||0))deny(c);};
  if(code==='KeyC'){const M=['shoulder','dynamic','wide'];setCam(M[(M.indexOf(camMode)+1)%3]);return;}
  if(code==='Tab'){const L=['watch','commander','handson'];setLevel(L[(L.indexOf(level)+1)%3]);return;}
  if(level==='watch'){callout('Watch mode','Press Tab to take command','#9aa1bd',.6,true);return;}
  if(!retry)stats.inputs++;
  // Ctrl+Space: parry / deflect (parry.js). Works while staggered too (parry the counter back).
  if(code==='Parry'){if(f.gone>0||!parryReady(f)){deny('Parry');return;}if(parryPress(f)){flashKey('Parry');f.buf=null;}else deny('Parry');return;}
  // R = jump / double jump, F = fast fall (ground fighters, gravity.js). Flyers hold R / F to climb / descend (main.js).
  if(code==='KeyR'){if(canFly(f))return;if(f.act&&f.act.kind!=='normal'){fail('KeyR');return;}if(f.stun>0||f.gone>0||f.snap||f.leap>0){fail('KeyR');return;}
    if(!canJump(f))return;if(f.act)endAct(f);if(jumpPress(f))f.buf=null;return;}
  if(code==='KeyF'){if(!canFly(f)&&f.z>.5&&f.stun<=0)f.ffall=true;return;}
  if(code==='Space'){const dir=readDir();const fly=canFly(f);let tx,ty,tz=fly&&keys.KeyR?f.z+380:fly&&keys.KeyF?f.z-380:(dir?f.z:e.z);if(dir){tx=f.x+dir[0]*300;ty=f.y+dir[1]*300;}else if(fly&&(keys.KeyR||keys.KeyF)){tx=f.x;ty=f.y;}else{const a=Math.atan2(e.y-f.y,e.x-f.x);tx=e.x+Math.cos(a)*90;ty=e.y+Math.sin(a)*90;}
    if(f.stun>0||f.gone>0){fail('Space');return;}if(f.act&&f.act.kind!=='normal'&&f.act.kind!=='react'){fail('Space');return;}
    if(f.act)endAct(f);f.snapCd=0;if(snapTo(f,tx,ty,Math.random()<Math.max(.3,f.k.blink),true,tz)){f.iframe=ms2t(160);f.perfectReady=incoming(f,e)!=null;stats.pSnaps++;f.buf=null;}else fail('Space');return;}
  if(code==='KeyJ'){if(f.act&&f.act.kind==='normal'){const a=f.act;const lastHit=a.def.hits.length?a.def.hits[a.def.hits.length-1][0]:a.def.fx.length?a.def.fx[a.def.fx.length-1][0]:0;if(a.t*TICK>lastHit+20)endAct(f);else{f.bufChain=true;return;}}
    if(!tryAttack(f,e,true))fail('KeyJ');else{stats.pChains++;f.buf=null;}return;}
  if(code==='KeyK'||code==='KeyL'||code==='KeyI'){const w=code==='KeyK'?'special':code==='KeyL'?'special2':'ult';if(!useSkill(f,w)){if(f.cds[w]>tick&&!busy())deny(code);else fail(code);}else{stats.pSkills++;f.buf=null;}return;}
  if(code.startsWith('Digit')){const n=+code[5];const map={1:'engage',2:'punish',3:'reset',4:'feint'};const it=map[n];
    if(level==='handson'){deny(code);return;}
    if(it==='punish'&&!isOpen(e)){deny(code);callout('Not open','Punish only works on a stunned or whiffing target','#ff6a80',.6,true);return;}
    enter(f,it);f.manualUntil=0;if(it==='punish'){f.gapUntil=0;f.snapCd=0;const a=Math.atan2(f.y-e.y,f.x-e.x);snapTo(f,e.x+Math.cos(a)*45,e.y+Math.sin(a)*45,Math.random()<f.k.blink);}
    stats.pIntents++;flashKey(code);return;}
  if(code==='KeyQ'||code==='KeyE'){if(training){deny(code);return;}const s=sides[0];const bench=[0,1,2].filter(i=>i!==s.on);const idx=bench[code==='KeyQ'?0:1];if(s.team[idx].ko||s.tagCd>tick){deny(code);return;}tagIn(0,idx,'tag');stats.pTags++;return;}}
