'use strict';
/* HUD: damage numbers, screen flash, command bar, callouts, HP / bench / director, intent labels, feel panel. */
const nums=[];
function dmgNum(t,v,col,wv){if(v<1)return;const el=document.createElement('div');el.className='dnum';el.textContent=v;el.style.color=cssc(col);el.style.fontSize=(1+wv*.28)+'em';$('labels').appendChild(el);
  nums.push({el,x:t.x+rnd(-20,20),y:t.y,z:t.z,h:2.1,t:0,dx:rnd(-.4,.4)});}
function stepNums(rdt){const r=host.getBoundingClientRect();for(let i=nums.length-1;i>=0;i--){const n=nums[i];n.t+=rdt;const p=VA(n.x,n.y,n.z,n.h+n.t*1.6).project(cam);
  n.el.style.left=((p.x+1)/2*r.width+n.dx*n.t*60)+'px';n.el.style.top=((1-p.y)/2*r.height)+'px';n.el.style.opacity=n.t<.45?1:Math.max(0,1-(n.t-.45)/.35);n.el.style.transform='translate(-50%,-50%) scale('+(n.t<.08?1.6-n.t*7.5:1)+')';
  if(n.t>.8){n.el.remove();nums.splice(i,1);}}}
function flash(a){const el=$('flash');el.style.transition='none';el.style.opacity=a;requestAnimationFrame(()=>{el.style.transition='opacity .22s';el.style.opacity=0;});}
/* ================= HUD ================= */
const CMDS=[['Space','Snap'],['Parry','Parry'],['KeyJ','Chain'],['KeyK','Special'],['KeyL','Special 2'],['KeyI','Ultimate'],['Digit1','1 Pressure'],['Digit2','2 Punish'],['Digit3','3 Reset'],['Digit4','4 Feint'],['KeyQ','Q Tag'],['KeyE','E Tag']];
const KEYLBL={Parry:'Ctrl+Space',Space:'Space',KeyJ:'J',KeyK:'K',KeyL:'L',KeyI:'I'};
const cmdEls={};
(function(){const bar=$('cmdbar');const r1=document.createElement('div');r1.className='crow';const r2=document.createElement('div');r2.className='crow';bar.appendChild(r1);bar.appendChild(r2);
  CMDS.forEach((c,i)=>{const el=document.createElement('div');el.className='ck';el.innerHTML=(KEYLBL[c[0]]?'<kbd>'+KEYLBL[c[0]]+'</kbd>':'')+'<span>'+c[1]+'</span><i class="cd"></i>';
    el.addEventListener('mousedown',ev=>{ev.preventDefault();if(running&&!paused&&!ended)command(c[0]);host.focus();});(i<6?r1:r2).appendChild(el);cmdEls[c[0]]=el;});})();
function deny(code){const el=cmdEls[code];if(!el)return;el.classList.remove('deny');void el.offsetWidth;el.classList.add('deny');}
function flashKey(code){const el=cmdEls[code];if(!el)return;el.classList.add('on');setTimeout(()=>el.classList.remove('on'),300);}
const co=$('callout');let coT=0;
function callout(t,s,col,dur,small){co.querySelector('b').textContent=t;co.querySelector('b').style.fontSize=small?'1.5em':'';co.querySelector('span').textContent=s||'';co.querySelector('b').style.color=col||'#e8ecfb';co.classList.add('on');coT=dur||1;}
const cssc=c=>'#'+c.toString(16).padStart(6,'0');
let hudFor=-1;const labels=[];
function hud(rdt){const [a,b]=onField();
  [a,b].forEach((f,i)=>{$('h'+i).style.width=(f.hp/f.max*100)+'%';$('h'+i+'t').textContent=Math.round(f.hp)+' / '+f.max;$('n'+i).textContent=f.k.name;
    const bench=$('b'+i);const s=sides[i];const html=s.team.map((g,j)=>j===s.on?'':'<div class="'+(g.ko?'ko':'')+'">'+g.k.short+'<i><b style="width:'+(g.hp/g.max*100)+'%;background:'+cssc(g.k.fx)+'"></b></i></div>').join('');if(bench.innerHTML!==html)bench.innerHTML=html;});
  $('dph').textContent=director.phase.toUpperCase();$('dph').style.color=director.phase==='burst'?'#ffc857':director.phase==='build'?'#8fd3ff':'#9aa1bd';$('dbar').style.width=(director.I*100)+'%';$('dbar').style.background=director.phase==='burst'?'#ffc857':'#8fd3ff';$('dmark').style.left=(director.at*100)+'%';
  const f=a;const e=b;
  const setCk=(code,ready,hot,frac)=>{const el=cmdEls[code];el.classList.toggle('off',!ready);el.classList.toggle('hot',!!hot&&ready);el.querySelector('.cd').style.width=((frac||0)*100)+'%';};
  const cdf=(k,total)=>f.cds[k]>tick?(f.cds[k]-tick)/ms2t(total):0;
  setCk('Space',f.snapCd<=tick&&f.stun<=0,incoming(f,e)!=null);
  {const st=f.pw;const c=parryCfg(f);const left=st&&tick<st.cd?(st.cd-tick)/ms2t(c.windowMs+c.cooldownMs):0;setCk('Parry',parryReady(f),incoming(f,e)!=null||incomingShot(f,c.reach*3)!=null,left);}
  setCk('KeyJ',!f.act||f.act.kind==='normal',f.tp.intent==='pressure'&&Math.hypot(e.x-f.x,e.y-f.y)<f.k.reach*1.6);
  setCk('KeyK',f.cds.special<=tick,false,cdf('special',f.k.special.cd));cmdEls.KeyK.querySelector('span').textContent=f.k.special.name;
  setCk('KeyL',f.cds.special2<=tick,false,cdf('special2',f.k.special2.cd));cmdEls.KeyL.querySelector('span').textContent=f.k.special2.name;
  setCk('KeyI',f.cds.ult<=tick,burst(),cdf('ult',f.k.ult.cd));cmdEls.KeyI.querySelector('span').textContent=f.k.ult.name;
  setCk('Digit2',!!isOpen(e),!!isOpen(e));['Digit1','Digit3','Digit4'].forEach(c=>setCk(c,level!=='handson'));
  const s=sides[0];const bench=[0,1,2].filter(i=>i!==s.on);['KeyQ','KeyE'].forEach((c,j)=>{const g=s.team[bench[j]];setCk(c,!g.ko&&s.tagCd<=tick,false,s.tagCd>tick?(s.tagCd-tick)/ms2t(3000):0);cmdEls[c].querySelector('span').textContent=(c==='KeyQ'?'Q ':'E ')+g.k.short;});
  ['Digit1','Digit2','Digit3','Digit4'].forEach((c,j)=>cmdEls[c].classList.toggle('on',f.tp.intent===['engage','punish','reset','feint'][j]&&level!=='handson'&&false));
  // intent labels
  const L=$('labels');const show=settings.labels;
  [a,b].forEach((g,i)=>{let el=labels[i];if(!el){el=document.createElement('div');el.className='lab';L.appendChild(el);labels[i]=el;}
    if(!show||g.gone>0){el.style.display='none';return;}el.style.display='';const p=VA(g.x,g.y,g.z,2.3+(g.h||0)).project(cam);const r=host.getBoundingClientRect();
    el.style.left=((p.x+1)/2*r.width)+'px';el.style.top=((1-p.y)/2*r.height)+'px';const it=parryWindow(g)?'parry':g.act&&g.act.kind==='react'?g.act.name:g.stun>0?'stunned':(g.side===0&&level==='handson')?'—':g.k.rhythm===false?(g.formChannel>=0?'transform':'style: '+(g.hp/g.max<=.3?'keep away':Math.hypot(g.x-enemyOf(g).x,g.y-enemyOf(g).y)>=500?'orbit':'kite')):g.tp.intent;
    el.textContent=it+(g.z>60?'  ↑'+Math.round(g.z/BODY*1.8)+'m':'');el.style.color=it==='punish'?'#ffc857':it==='pressure'||it==='engage'?'#ff8a9a':it==='stunned'?'#9aa1bd':it==='parry'||it==='block'?'#ffffff':'#8fd3ff';});
  if(coT>0){coT-=rdt;if(coT<=0)co.classList.remove('on');}
  $('vig').classList.toggle('on',slowmo>0||burst());
  feelPanel();}
/* feel panel: rolling 20 s window vs 2D duel ranges */
let feelT=0;
function feelPanel(){if(!settings.feel){$('feel').style.display='none';return;}$('feel').style.display='';if(tick-feelT<15)return;feelT=tick;
  const win=ms2t(20000),from=tick-win;const span=Math.min(tick,win)*DT||1;
  const hits=metr.hits.filter(t=>t>from);const ht=[...new Set(hits)];const gaps=[];for(let i=1;i<ht.length;i++)gaps.push((ht[i]-ht[i-1])*DT);gaps.sort((x,y)=>x-y);
  const med=a=>a.length?a[Math.floor(a.length/2)]:0;
  const dist=metr.dist.filter(r=>r[0]>from).map(r=>r[1]).sort((x,y)=>x-y);
  const both=metr.both.filter(r=>r[0]>from);const bothPct=both.length?both.filter(r=>r[1]).length/both.length*100:0;
  const burstPct=metr.burst.filter(r=>r[0]>from);const bp=burstPct.length?burstPct.filter(r=>r[1]).length/burstPct.length*100:0;
  const sn=metr.snaps.filter(r=>r[0]>from);const snapMin=sn.length/2/span*60;
  const st=metr.starts.filter(t=>t>from).length/2;const actGap=st?span/st:0;
  const row=(n,v,unit,lo,hi,fmt)=>{const ok=v>=lo&&v<=hi;return '<tr><td>'+n+'</td><td class="'+(ok?'ok':'lo')+'">'+fmt(v)+unit+'</td><td>2D '+fmt(lo)+'–'+fmt(hi)+unit+'</td></tr>';};
  const f1=v=>v.toFixed(1),f2=v=>v.toFixed(2),f0=v=>Math.round(v);
  $('feel').innerHTML='<div class="t">FEEL · LAST 20 S vs 2D DUEL</div><table>'+
    row('Hits / s',ht.length/span,'',0.9,1.3,f2)+row('Median hit gap',med(gaps),' s',0.55,0.85,f2)+row('Distance',med(dist),' bodies',0.6,1.4,f1)+
    row('Action start every',actGap,' s',0.3,0.55,f2)+row('Snaps / min (each)',snapMin,'',30,140,f0)+row('Both acting',bothPct,'%',40,60,f0)+row('Director burst',bp,'%',15,30,f0)+'</table>';}
