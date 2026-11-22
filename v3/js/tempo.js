'use strict';
/* Fight rhythm: port of laser/tempo.py intents (neutral, feint, engage, pressure, punish, reset) and their movement targets. */
/* ================= tempo (port of laser/tempo.py) ================= */
function dirI(){return director.I;}
function burst(){return director.phase==='burst';}
function aggr(f){const c=f.k.t;return (c.aggr||1)*(1+(c.mom==null?.35:c.mom)*f.tp.mom);}
function randMs(a,b,k){return ms2t(rnd(a,b)*(k==null?1:k));}
function enter(f,intent){const st=f.tp,c=f.k.t,I=dirI(),bu=burst();st.intent=intent;st.since=tick;
  if(intent==='neutral'){const k=(1-.6*I)*(bu?.45:1)/Math.max(.25,aggr(f));st.until=tick+randMs(c.neutral[0],c.neutral[1],k);}
  else if(intent==='feint'){st.feintKind=Math.random()<.6?'dash_in':'fake_retreat';st.feintBit=false;st.until=tick+randMs(380*.7,380*1.3);}
  else if(intent==='engage'){st.until=tick+ms2t(1400);st.n=Math.round(rnd(c.string[0],c.string[1]))+(bu?2:0);st.done=0;}
  else if(intent==='punish'){st.until=tick+randMs(720,1080);st.openSeen=true;if(st.n-st.done<2)st.n=st.done+2+Math.floor(rnd(0,3));}
  else if(intent==='reset'){st.until=tick+randMs((c.resetMs||[350,1100])[0],(c.resetMs||[350,1100])[1],bu?.5:1);st.resetAng=rnd(-.8,.8);if(Math.random()<.5)st.orbit=-st.orbit;}
  else if(intent==='pressure'){st.until=tick+ms2t(8000);}}
function isOpen(t){if(!t||t.ko||!t.on)return 0;if(t.stun>0)return 1;if(tick-t.lastEnd<=ms2t(260)&&t.lastWhiff)return 2;return 0;}
function think(f,e,started,ended){const st=f.tp,c=f.k.t,I=dirI(),bu=burst();
  st.mom*=1-.15*DT;
  const d=Math.hypot(f.x-e.x,f.y-e.y),reach=f.k.reach;
  if(started>0)st.lastStart=tick;
  const op=isOpen(e);const took=f.hurts.some(h=>tick-h<=ms2t(500));
  const open=(op===1||(op===2&&!took))&&tick-f.lastLanded>ms2t(700);
  if(!open)st.openSeen=false;
  if(open&&!st.openSeen&&tick>=st.punishReady&&d<=280&&['neutral','wait','feint','reset'].includes(st.intent)){st.openSeen=true;if(Math.random()*100<(c.punish||70)*(.7+.6*I))enter(f,'punish');}
  const it=st.intent;
  if(it==='neutral'){if(d<=reach&&(tick-st.since)%ms2t(200)===0&&Math.random()<.35*aggr(f)*(.6+I))enter(f,'engage');
    else if(tick>=st.until){if(Math.random()*100<c.feint*(.7+.8*I))enter(f,'feint');else enter(f,'engage');}}
  else if(it==='feint'){if(e.act&&e.act.kind!=='react')st.feintBit=true;if(e.gone>0)st.feintBit=true;
    if(tick>=st.until){if(st.feintBit&&Math.random()*100<(c.punish||70))enter(f,'punish');else if(st.feintKind==='fake_retreat')enter(f,'engage');else{enter(f,'neutral');st.until=st.since+Math.max(ms2t(150),Math.floor((st.until-st.since)/3));}}}
  else if(it==='engage'){if(started>0){st.done+=started;enter(f,'pressure');}else if(tick>=st.until)enter(f,'reset');}
  else if(it==='pressure'||it==='punish'){if(started>0)st.done+=started;
    const recent=f.hurts.filter(h=>tick-h<=ms2t(500)).length;
    if(it==='punish'&&tick>=st.until){st.punishReady=tick+ms2t(1500);enter(f,'pressure');}
    else if((st.done>=st.n&&!f.act)||recent>=2||tick-Math.max(st.lastStart,st.since)>ms2t(1500)||d>reach*6)enter(f,'reset');}
  else if(it==='reset'){if(tick>=st.until)enter(f,'neutral');}
  if(ended&&['pressure','punish','engage'].includes(st.intent)){const u=Math.min(1,st.done/Math.max(1,st.n));let gap=c.gap[0]+(c.gap[1]-c.gap[0])*Math.pow(u,.7);
    if(st.intent==='punish')gap=Math.min(gap,c.gap[1])*.5;if(bu)gap*=.7;gap*=1+rnd(-.35,.35);f.gapUntil=tick+Math.round(Math.max(0,gap)/TICK);}}
function allows(f){if(f.k.rhythm===false)return true;return ['engage','pressure','punish'].includes(f.tp.intent)||(!f.k.melee&&f.tp.intent==='wait');}
function moveTarget(f,e){const st=f.tp,reach=f.k.reach;let dx=f.x-e.x,dy=f.y-e.y,d=Math.hypot(dx,dy);if(d<1e-3){dx=1;dy=0;d=1;}const ux=dx/d,uy=dy/d;
  const ring=(r,lead)=>{const a=Math.atan2(uy,ux)+lead*st.orbit;return [e.x+Math.cos(a)*r,e.y+Math.sin(a)*r];};const it=st.intent;
  if(it==='neutral'){const sway=40*Math.sin(st.swayPh+TAU*tick*TICK/st.swayMs);if(Math.random()<.004)st.orbit=-st.orbit;return ring(Math.max(10,reach+f.k.t.spacing+sway),.35);}
  if(it==='feint'){const u=(tick-st.since)/Math.max(1,st.until-st.since);if(st.feintKind==='fake_retreat')return [e.x+ux*(d+160),e.y+uy*(d+160)];if(u<.6&&d>reach*1.15)return [e.x+ux*reach*1.1,e.y+uy*reach*1.1];return ring(reach*1.6,1.1);}
  if(it==='engage'||it==='punish'||it==='pressure'){const r=reach*.5;return [e.x+ux*r,e.y+uy*r];}
  if(it==='reset'){const a=Math.atan2(uy,ux)+st.resetAng;const r=d+f.k.t.reset;return [e.x+Math.cos(a)*r,e.y+Math.sin(a)*r];}
  return null;}
