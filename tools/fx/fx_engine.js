// ================= FX ENGINE =================
// Sections: [LAYER SCHEMA & DEFAULTS] [BATTLE/FX SEMANTICS] [TRIGGERS] [TIMELINE/KEYFRAMES]
//           [LAYERS UI] [HIT DETECTION] [SIMULATION] [RENDER] [EXPORT/IMPORT]
// Roadmap slots (do NOT implement here yet): projectile spec presets, cadence, fire_cycle,
// muzzle-anchor spawning and palette.stops all attach to [LAYER SCHEMA & DEFAULTS]/[EXPORT].
// ---- [LAYER SCHEMA & DEFAULTS] ----
const DEF={
particles:{px:0,py:0,prot:0,anchor:'point',follow:false,count:24,spread_deg:360,angle_deg:-90,speed_min:80,speed_max:280,gravity:0,drag:0.94,size_min:2,size_max:5,size_over_life:'shrink',life_min:250,life_max:550,c1:'#ff4040',c2:'#ffd070',glow:10,blend:'additive',shape:'circle',delay_ms:0,burst:true,emit_rate:60},
ring:{px:0,py:0,prot:0,anchor:'point',follow:false,radius_start:4,radius_end:90,thickness:6,life_min:350,life_max:350,c1:'#ffffff',c2:'#ff4040',glow:14,blend:'additive',delay_ms:0,thin_out:true},
flash:{px:0,py:0,prot:0,anchor:'point',follow:false,size_min:20,size_max:60,life_min:90,life_max:140,c1:'#fff6d0',c2:'#ff8030',glow:20,blend:'additive',delay_ms:0,rays:0},
crescent:{px:0,py:0,prot:0,anchor:'point',follow:false,radius_start:20,radius_end:70,arc_deg:120,thickness:9,angle_deg:0,spin_deg:180,life_min:220,life_max:300,c1:'#ff3050',c2:'#ffb0c0',glow:12,blend:'additive',delay_ms:0},
trail:{px:0,py:0,prot:0,anchor:'point',emit_rate:90,size_min:3,size_max:7,life_min:200,life_max:420,c1:'#40c0ff',c2:'#a0f0ff',glow:10,blend:'additive',line:true,delay_ms:0,drag:0.9,speed_min:0,speed_max:30,spread_deg:360,size_over_life:'shrink',shape:'circle'},
afterimage:{px:0,py:0,prot:0,anchor:'hip',emit_rate:22,life_min:180,life_max:320,c1:'#dc143c',c2:'#500010',glow:8,blend:'additive',w:16,h:44,delay_ms:0,ghost_rig:true},
image:{px:0,py:0,prot:0,anchor:'point',scale:1,opacity:1,src:null,w0:64,h0:64},
beam:{px:0,py:0,prot:0,anchor:'point',follow:true,length:320,w_start0:10,w_start1:10,w_end0:10,w_end1:10,travel_speed:0,detach_ms:400,angle_deg:0,segments:14,pulse_hz:8,life_min:600,life_max:600,c1:'#ffffff',c2:'#ff2020',glow:16,blend:'additive',delay_ms:0,jitter:3,aim_weapon:true}};
['particles','ring','flash','crescent','trail','afterimage','beam'].forEach(k=>Object.assign(DEF[k],{trig:'immediate',trig_ref:'',trig_delay_ms:0,can_hit:false}));
['particles','crescent','beam'].forEach(k=>{DEF[k].homing=false});DEF.crescent.homing_speed=320;
const FIELDS={can_hit:['Can hit target','chk'],anchor:['Anchor joint','anc'],follow:['Follow joint','chk'],count:['Count','r',1,300,1],spread_deg:['Spread °','r',0,360,1],angle_deg:['Angle °','r',-180,180,1],speed_min:['Speed min','r',0,600,5],speed_max:['Speed max','r',0,900,5],gravity:['Gravity','r',-400,800,10],drag:['Drag','r',0.5,1,0.01],size_min:['Size min','r',1,40,0.5],size_max:['Size max','r',1,80,0.5],size_over_life:['Size/life','sel',['shrink','grow','pulse','constant']],life_min:['Life min ms','r',30,3000,10],life_max:['Life max ms','r',30,3000,10],glow:['Glow','r',0,40,1],blend:['Blend','sel',['additive','normal']],shape:['Shape','sel',['circle','spark','square']],delay_ms:['Delay ms','r',0,2000,10],burst:['Burst (vs stream)','chk'],emit_rate:['Emit/sec','r',1,240,1],radius_start:['Radius start','r',0,200,1],radius_end:['Radius end','r',5,400,1],thickness:['Thickness','r',1,40,0.5],thin_out:['Thin as expands','chk'],rays:['Rays','r',0,16,1],arc_deg:['Arc °','r',10,360,5],spin_deg:['Spin °','r',-720,720,10],line:['Connect line','chk'],w:['Ghost W','r',4,80,1],h:['Ghost H','r',8,140,1],ghost_rig:['Ghost full rig pose','chk'],length:['Length','r',40,10000,5],width:['Width','r',1,600,1],w_start0:['Start W begin','r',1,600,1],w_start1:['Start W end','r',1,600,1],w_end0:['End W begin','r',1,600,1],w_end1:['End W end','r',1,600,1],travel_speed:['Travel px/s','r',0,3000,10],detach_ms:['Detach ms','r',0,5000,10],homing:['Homing (seek target)','chk'],homing_speed:['Homing px/s','r',20,2000,10],segments:['Segments','r',2,40,1],pulse_hz:['Pulse Hz','r',0,30,0.5],jitter:['Jitter','r',0,20,0.5],aim_weapon:['Aim along weapon','chk']};
// ---- [BATTLE/FX SEMANTICS] per-FX-layer battle properties (attach to can_hit layers; identical in Solo & Battle) ----
// Roadmap slot: damage model (real HP pool, pierce/explode wiring) consumes these blocks game-side.
const FX_SEMANTICS={
 battle_fx_placement:'All battle FX (explode/scatter/pierce/slash and deflect/block visuals) spawn at the FIRST OVERLAP POINT between the hitting FX and the target — the point of collision — not at the FX origin. Identical in Solo & Battle.',
 homing:'Homing (particles, crescent, beam): the FX steers toward the target every tick until collision; on impact the FX ends immediately and, if can_hit, triggers hit/battle FX at the collision point. Particles keep their own speed; crescents travel at homing_speed px/s; beams re-aim their direction at the target. Identical in Solo & Battle.',
 beam_travel:'travel_speed>0: the beam head advances from the fire point at travel_speed px/s; after detach_ms the tail leaves the source and the whole segment travels forward. Visible length is capped at Length. travel_speed=0 keeps the classic static full-length beam. Identical in Solo & Battle.',
 beam_width:'Beam widths animate over the layer lifetime: w_start0→w_start1 at the start point (source/tail side), w_end0→w_end1 at the end point (head). Max width 600, max length 10000. Identical in Solo & Battle.'};
const BATTLE_SEMANTICS={
 attach:'Battle properties are attached per FX layer, only on layers with can_hit=true (not per character or per action).',
 trigger:'Both categories fire at the moment a can_hit FX contacts a target.',
 damage:'Each hitting FX layer deals its own damage value (0-100).',
 attack:{stacking:'Attack properties stack freely on one layer.',
  explode:'Visual only: particles spawn around the target at max size, grow, then fade away.',
  scatter:'Visual only: sparks fly in a line in the same direction the attack was travelling when it hit.',
  pierce:'Visual only: sparks fly back out toward the direction the target was hit from.',
  slash:'Visual only: a crescent sweeps across the point of impact.'},
 defence:{exclusive:'Deflect and Block are mutually exclusive per FX layer.',
  deflect:'A crescent strikes the incoming can_hit FX; that FX is knocked perpendicular to its travel direction, auto up/down picking whichever side points away from the defender body; HP damage is voided.',
  block:'A ring erases the incoming can_hit FX; HP damage taken is reduced by 50%.'},
 parity:'Behaviour is identical in Solo & Battle modes.'};
function ensureBattle(l){if(!l.battle)l.battle={damage:10,attack:{explode:false,scatter:false,pierce:false,slash:false},defence:'none'};
 if(!l.battle.attack)l.battle.attack={explode:false,scatter:false,pierce:false,slash:false};
 if(l.battle.defence===undefined)l.battle.defence='none';if(l.battle.damage===undefined)l.battle.damage=10;return l.battle}
function battleHtml(l){if(!l.can_hit)return'';const b=ensureBattle(l);
 const ck=(k,lab)=>`<div class="row"><label>${lab}</label><div class="v"><input type="checkbox" ${b.attack[k]?'checked':''} onchange="bSetL('${k}',this.checked)"></div></div>`;
 return `<div class="row"><label><b>Battle</b></label><div class="v"><small>fires on target hit</small></div></div>
 <div class="row"><label>Damage</label><div class="v"><input type="range" min="0" max="100" step="1" value="${b.damage}" oninput="bSetL('damage',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${b.damage}</span></div></div>
 <small style="color:#7a8599;display:block;padding:2px 0">Attack — stackable, visual only:</small>
 ${ck('explode','Explode')+ck('scatter','Scatter')+ck('pierce','Pierce')+ck('slash','Slash')}
 <div class="row"><label>Defence</label><div class="v"><select onchange="bSetL('defence',this.value)">${['none','deflect','block'].map(o=>`<option ${o===b.defence?'selected':''}>${o}</option>`).join('')}</select></div></div>
 <small style="color:#7a8599;display:block;padding:2px 0">Deflect: crescent knocks the FX perpendicular away from the defender, voids HP damage. Block: ring erases the FX, HP damage −50%. Mutually exclusive.</small>`}
function bSetL(k,v){const l=fx.layers[sel];if(!l)return;const b=ensureBattle(l);
 if(k==='damage')b.damage=v;else if(k==='defence')b.defence=v;else b.attack[k]=v}
function spawnBFX(type,over,hx,hy){const tl={type,...JSON.parse(JSON.stringify(DEF[type])),...over,anchor:'point',follow:false,px:hx-W/2,py:hy-H/2,can_hit:false};
 const n=type==='particles'?(tl.count||16):1;const before=parts.length;spawn(tl,-1,n);
 for(let i=before;i<parts.length;i++)parts[i].bfx=true}
function onBattleHit(p,chx,chy){const l=p.l,b=l.battle;if(!b)return;const hx=chx!==undefined?chx:p.x,hy=chy!==undefined?chy:p.y;
 let ang=0;if(p.vx!==undefined&&(p.vx||p.vy))ang=Math.atan2(p.vy,p.vx);
 else{const[ax,ay]=aPos(l);ang=Math.atan2(hy-ay,hx-ax)||0}
 const dg=ang*180/Math.PI,A=b.attack||{};
 if(A.explode)spawnBFX('particles',{count:20,spread_deg:360,angle_deg:0,speed_min:15,speed_max:60,size_min:9,size_max:15,size_over_life:'grow',life_min:380,life_max:650,c1:'#ffd070',c2:'#ff4020',shape:'circle',burst:true,drag:0.9,gravity:0,glow:16},hx,hy);
 if(A.scatter)spawnBFX('particles',{count:10,spread_deg:12,angle_deg:dg,speed_min:220,speed_max:480,size_min:2,size_max:4,life_min:180,life_max:360,c1:'#fff0a0',c2:'#ff8020',shape:'spark',burst:true,drag:0.96,gravity:0,glow:10},hx,hy);
 if(A.pierce)spawnBFX('particles',{count:10,spread_deg:24,angle_deg:dg+180,speed_min:180,speed_max:420,size_min:2,size_max:4,life_min:180,life_max:360,c1:'#ffffff',c2:'#60b0ff',shape:'spark',burst:true,drag:0.95,gravity:0,glow:10},hx,hy);
 if(A.slash)spawnBFX('crescent',{radius_start:14,radius_end:52,arc_deg:130,thickness:8,angle_deg:dg,spin_deg:140,life_min:240,life_max:240,c1:'#ff3050',c2:'#ffd0d8',glow:12},hx,hy);
 if(b.defence==='deflect'){spawnBFX('crescent',{radius_start:12,radius_end:46,arc_deg:120,thickness:7,angle_deg:dg+180,spin_deg:-120,life_min:220,life_max:220,c1:'#a0e0ff',c2:'#4090ff',glow:12},hx,hy);
  const G=dummyGeom(),awx=hx-G.X,awy=hy-(G.top+G.bot)/2;
  const p1=ang+Math.PI/2,p2=ang-Math.PI/2;
  const pick=(Math.cos(p1)*awx+Math.sin(p1)*awy)>=(Math.cos(p2)*awx+Math.sin(p2)*awy)?p1:p2;
  for(const q of parts){if(q.l!==l||q.bfx)continue;if(q.vx!==undefined){const s=Math.hypot(q.vx,q.vy)||200;q.vx=Math.cos(pick)*s;q.vy=Math.sin(pick)*s}}}
 else if(b.defence==='block'){spawnBFX('ring',{radius_start:6,radius_end:70,thickness:6,life_min:300,life_max:300,c1:'#ffffff',c2:'#4090ff',glow:14,thin_out:true},hx,hy);
  for(let i=parts.length-1;i>=0;i--){if(parts[i].l===l&&!parts[i].bfx)parts.splice(i,1)}}}

let fx={layers:[]},sel=-1,parts=[],playing=false,t0=0,last=0,acc={},spawned={},curJ=null;
// ---- [TRIGGERS] per-layer trigger system ----
const TRIG_OPTS=['immediate','on_hit','on_dash','on_fire','on_death','on_parry','on_ult','ambient','after_fx','after_layer'];
let _lidc=1,hitAt=null;function layerId(l){if(!l._id)l._id='L'+(_lidc++);return l._id}
function fxDurOf(name){name=(name||'').replace(/^action: /,'');
 if(typeof CH!=='undefined'&&CH&&CH.actions&&CH.actions[name])return CH.actions[name].duration_ms||800;return 800}
function trigFxList(){const cur=(typeof curActionKey==='function')?curActionKey():null;
 return (typeof CH!=='undefined'&&CH&&CH.actions)?Object.keys(CH.actions).filter(k=>k!==cur).map(k=>'action: '+k):[]}
function layerStart(li,seen){const l=fx.layers[li];if(!l)return 0;seen=seen||new Set();
 if(seen.has(li))return 0;seen.add(li);const m=l.trig||'immediate';
 if(m==='after_fx')return fxDurOf(l.trig_ref)+(l.trig_delay_ms||0);
 if(m==='after_layer'){const ri=fx.layers.findIndex(x=>x._id===l.trig_ref);
  if(ri<0||ri===li)return l.trig_delay_ms||0;
  return layerStart(ri,seen)+(fx.layers[ri].delay_ms||0)+(l.trig_delay_ms||0)}
 return 0}
function chainSpan(){let m=0;fx.layers.forEach((l,i)=>{if(isBI(l)||l.type==='image')return;const s=layerStart(i);if(s>m)m=s});return m}
function trigHtml(l){layerId(l);if(l.can_hit===undefined)l.can_hit=false;const tm=l.trig||'immediate';
 let h=`<div class="row"><label>Trigger</label><div class="v"><select onchange="setP('trig',this.value);renderProps()">${TRIG_OPTS.map(o=>`<option ${o===tm?'selected':''}>${o}</option>`).join('')}</select></div></div>`;
 if(tm==='on_hit')h+=`<small style="color:#7a8599;display:block;padding:2px 0 4px">Plays only when a layer marked <b>Can hit target</b> contacts the target dummy. Dormant if the dummy is off. Fires once per loop cycle. Same rule in Solo &amp; Battle.</small>`;
 if(tm==='after_fx'){const list=trigFxList();if(!list.includes(l.trig_ref))l.trig_ref=list[0]||'';
  h+=`<div class="row"><label>After FX</label><div class="v"><select onchange="setP('trig_ref',this.value)">${list.map(o=>`<option ${o===l.trig_ref?'selected':''}>${o}</option>`).join('')}</select></div></div>`}
 if(tm==='after_layer'){const opts=fx.layers.map((x,i)=>({x,i})).filter(q=>!isBI(q.x)&&q.x.type!=='image'&&q.x!==l);
  if(!opts.some(q=>layerId(q.x)===l.trig_ref))l.trig_ref=opts.length?layerId(opts[0].x):'';
  h+=`<div class="row"><label>After layer</label><div class="v"><select onchange="setP('trig_ref',this.value)">${opts.map(q=>`<option value="${layerId(q.x)}" ${layerId(q.x)===l.trig_ref?'selected':''}>${q.i+1}. ${q.x.type}</option>`).join('')}</select></div></div>`}
 if(tm==='after_fx'||tm==='after_layer')h+=`<div class="row"><label>Chain delay ms</label><div class="v"><input type="number" min="0" step="10" style="width:70px" value="${l.trig_delay_ms||0}" onchange="setP('trig_delay_ms',+this.value)"></div></div>`;
 return h}
function fixKF(ks){ks.forEach(k=>{const p=k.p;
 if(p.sht!==undefined){p.lsht=p.rsht=p.sht;delete p.sht}
 if(p.pvt!==undefined){p.lpvt=p.rpvt=p.pvt;delete p.pvt}
 PK.forEach(q=>{if(p[q]===undefined)p[q]=Z[q]})})}
function togglePose(){poseMode=!poseMode;$('posebtn').className=poseMode?'on':'';
 if(poseMode){playing=false;if(selKF<0&&keyframes.length){selKF=0}$('stat').textContent='pose mode — drag joints';renderTL()}
 else{$('stat').textContent='';play()}}
function syncDur(){}
function curT(){return playing?(((performance.now()-t0)*+$('slow').value)%(+$('dur').value))/+$('dur').value:(selKF>=0?keyframes[selKF].t:0)}
// ---- [TIMELINE/KEYFRAMES] ----
// Roadmap slot: playback control honoring keyframe t-brackets is a game-side change; authoring already stores t.
const tl=$('tl');
function renderTL(){tl.innerHTML='';keyframes.forEach((k,i)=>{const d=document.createElement('div');d.className='kf'+(i===selKF?' sel':'');
 d.style.left=(k.t*100)+'%';
 d.onmousedown=e=>{e.stopPropagation();e.preventDefault();selKF=i;dragKF=k;if(!poseMode)togglePose();else renderTL()};
 d.onclick=e=>e.stopPropagation();tl.appendChild(d)});
 const ph=document.createElement('div');ph.className='ph';ph.id='ph';tl.appendChild(ph);
 $('tlhint').textContent=poseMode?`Editing keyframe ${selKF+1}/${keyframes.length} @ t=${keyframes[selKF]?.t.toFixed(2)} — drag joints on canvas; drag hip to move root; drag ◆ along timeline to retime; ←/→ nudge KF (Shift=×5); click timeline to scrub`:'Timeline — ◆ keyframes (click to edit) | wheel=zoom, drag canvas=pan | Pose Mode to sculpt, + KF to capture new keyframe at playhead'}
tl.onclick=e=>{const r=tl.getBoundingClientRect(),t=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
 if(poseMode){playing=false;scrubT=t;$('ph').style.left=(t*100)+'%'}};
let scrubT=0,dragKF=null;
document.addEventListener('mousemove',e=>{if(!dragKF)return;const r=tl.getBoundingClientRect();
 dragKF.t=+Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)).toFixed(3);
 keyframes.sort((a,b)=>a.t-b.t);selKF=keyframes.indexOf(dragKF);renderTL()});
document.addEventListener('mouseup',()=>{dragKF=null});
document.addEventListener('keydown',e=>{if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
 const ae=document.activeElement;if(ae&&['INPUT','TEXTAREA','SELECT'].includes(ae.tagName))return;
 if(selKF<0||!keyframes[selKF])return;e.preventDefault();
 const k=keyframes[selKF],st=e.shiftKey?0.05:0.01;
 k.t=+Math.max(0,Math.min(1,k.t+(e.key==='ArrowRight'?st:-st))).toFixed(3);
 keyframes.sort((a,b)=>a.t-b.t);selKF=keyframes.indexOf(k);renderTL()});
function addKF(){const t=+curT().toFixed(3),p=poseAt(poseMode?scrubT:curT());
 keyframes.push({t:poseMode?+scrubT.toFixed(3):t,p});keyframes.sort((a,b)=>a.t-b.t);
 selKF=keyframes.findIndex(k=>k.p===p);if(!poseMode)togglePose();renderTL()}
function delKF(){if(selKF>=0&&keyframes.length>1){keyframes.splice(selKF,1);selKF=Math.min(selKF,keyframes.length-1);renderTL()}}
function dupKF(){if(selKF<0){alert('Select a keyframe first (Pose Mode)');return}
 const k=keyframes[selKF],p={...k.p},t=Math.min(1,+(k.t+0.05).toFixed(3));
 keyframes.push({t,p});keyframes.sort((a,b)=>a.t-b.t);selKF=keyframes.findIndex(q=>q.p===p);renderTL()}
window.dupKF=dupKF;
// ---- [LAYERS UI] ----
function addLayer(){const t=$('newtype').value;ensureBuiltin(fx.layers);
 let at=fx.layers.findIndex(isBI);if(at<0)at=fx.layers.length;
 fx.layers.splice(at,0,{type:t,...JSON.parse(JSON.stringify(DEF[t]))});sel=at;renderLayers();renderProps();
 if(t==='image')pickImage()}
function pickImage(){const inp=$('imgfile');inp.onchange=()=>{const f=inp.files[0];inp.value='';if(!f)return;
  const rd=new FileReader();rd.onload=()=>{const im=new Image();im.onload=()=>{const l=fx.layers[sel];if(!l||l.type!=='image')return;
   l.src=rd.result;l.w0=im.naturalWidth||64;l.h0=im.naturalHeight||64;
   l.scale=+(140/Math.max(l.w0,l.h0)).toFixed(3);IMGC.set(l.src,im);renderLayers();renderProps()};
   im.src=rd.result};rd.readAsDataURL(f)};inp.click()}
const IMGC=new Map();
function getImg(l){if(!l.src)return null;let im=IMGC.get(l.src);if(!im){im=new Image();im.src=l.src;IMGC.set(l.src,im)}return im}
function drawImageLayer(l){const im=getImg(l);const[x,y]=aPos(l);
 ctx.save();ctx.globalCompositeOperation='source-over';ctx.shadowBlur=0;
 ctx.translate(x,y);ctx.rotate((l.prot||0)*D);ctx.globalAlpha=Math.max(0,Math.min(1,l.opacity??1));
 const w=(l.w0||64)*(l.scale||1),h=(l.h0||64)*(l.scale||1);
 if(im&&im.complete&&im.naturalWidth)ctx.drawImage(im,-w/2,-h/2,w,h);
 else{ctx.strokeStyle='#7a8599';ctx.setLineDash([4,4]);ctx.strokeRect(-w/2,-h/2,w,h);ctx.setLineDash([])}
 if(fx.layers[sel]===l&&!weaponEdit&&!poseMode){ctx.globalAlpha=1;ctx.strokeStyle='#ffd24a';ctx.lineWidth=1/cam.z;ctx.setLineDash([5/cam.z,4/cam.z]);ctx.strokeRect(-w/2,-h/2,w,h);ctx.setLineDash([])}
 ctx.restore()}
function renderLayers(){const d=$('layers');d.innerHTML='';ensureBuiltin(fx.layers);fx.layers.forEach((l,i)=>{
 const e=document.createElement('div');e.className='layer'+(i===sel?' sel':'');
 const off=l.visible===false?' style="opacity:.45"':'';
 if(isBI(l))e.innerHTML=`<span class="t"${off}>${i+1}. <b>${l.type==='figure'?'⚑ Character':'⚔ Weapon'}</b> <small>${l.visible===false?'hidden':'op '+Math.round((l.opacity??1)*100)+'%'}</small></span>`;
 else e.innerHTML=`<span class="t">${i+1}. <b>${l.type}</b> <small>@${l.anchor}</small></span>`;
 const mv=f=>{const j=i+f;if(j<0||j>=fx.layers.length)return;[fx.layers[j],fx.layers[i]]=[fx.layers[i],fx.layers[j]];sel=j;renderLayers()};
 const up=document.createElement('button');up.textContent='↑';up.title='move back (drawn earlier)';up.onclick=ev=>{ev.stopPropagation();mv(-1)};
 const dn=document.createElement('button');dn.textContent='↓';dn.title='move front (drawn later)';dn.onclick=ev=>{ev.stopPropagation();mv(1)};
 e.append(up,dn);
 if(!isBI(l)){
  const dp=document.createElement('button');dp.textContent='⧉';dp.onclick=ev=>{ev.stopPropagation();fx.layers.splice(i+1,0,JSON.parse(JSON.stringify(l)));renderLayers()};
  const x=document.createElement('button');x.textContent='✕';x.onclick=ev=>{ev.stopPropagation();fx.layers.splice(i,1);sel=Math.min(sel,fx.layers.length-1);renderLayers();renderProps()};
  e.append(dp,x)}
 e.onclick=()=>{sel=i;renderLayers();renderProps()};d.appendChild(e)})}
function renderProps(){const d=$('props'),l=fx.layers[sel];if(!l){d.innerHTML='<em style="color:#7a8599">Select a layer</em>';return}
 if(isBI(l)){d.innerHTML=`<div class="row"><label>Type</label><div class="v"><b>${l.type==='figure'?'Character (built-in)':'Weapon (built-in)'}</b></div></div>
 <div class="row"><label>Visible</label><div class="v"><input type="checkbox" ${l.visible!==false?'checked':''} onchange="setP('visible',this.checked);renderLayers()"></div></div>
 <div class="row"><label>Opacity</label><div class="v"><input type="range" min="0" max="1" step="0.05" value="${l.opacity??1}" oninput="setP('opacity',+this.value);this.nextElementSibling.textContent=this.value;renderLayers()"><span class="val">${l.opacity??1}</span></div></div>
 <small style="color:#7a8599;display:block;padding:4px 0">Use ↑/↓ in the Layers list to move FX behind or in front of the ${l.type==='figure'?'character':'weapon'}.</small>`;return}
 if(l.type==='image'){d.innerHTML=`<div class="row"><label>Type</label><div class="v"><b>image</b></div></div>
 <div class="row"><label>Image</label><div class="v"><button onclick="pickImage()">${l.src?'Replace\u2026':'Choose\u2026'}</button> <small>${l.src?(l.w0+'\u00d7'+l.h0):'none'}</small></div></div>
 <div class="row"><label>Anchor joint</label><div class="v"><select onchange="setP('anchor',this.value)">${ANCHORS().map(o=>`<option ${o===l.anchor?'selected':''}>${o}</option>`).join('')}</select></div></div>
 <div class="row"><label>Scale</label><div class="v"><input type="range" min="0.05" max="10" step="0.01" value="${l.scale||1}" oninput="setP('scale',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${l.scale||1}</span></div></div>
 <div class="row"><label>Opacity</label><div class="v"><input type="range" min="0" max="1" step="0.05" value="${l.opacity??1}" oninput="setP('opacity',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${l.opacity??1}</span></div></div>
 <div class="row"><label>Rotation \u00b0</label><div class="v"><input type="range" min="-180" max="180" step="1" value="${Math.round(l.prot||0)}" oninput="setP('prot',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${Math.round(l.prot||0)}</span></div></div>
 <div class="row"><label>Pivot</label><div class="v"><span id="pivinfo" class="val">x ${(l.px||0).toFixed(0)}  y ${(l.py||0).toFixed(0)}  rot ${Math.round(l.prot||0)}\u00b0</span> <button onclick="resetPivot()">\u21ba</button></div></div>
 <small style="color:#7a8599;display:block;padding:2px 0 4px">Drag the <b style="color:#ffd24a">gold</b> handle to move, <b style="color:#4ad0ff">blue</b> to rotate, <b style="color:#8dff6a">green corner</b> to resize \u2014 like a shape in PowerPoint.</small>`;return}
 d.innerHTML=`<div class="row"><label>Type</label><div class="v"><b>${l.type}</b></div></div>
 <div class="row"><label>Pivot</label><div class="v"><span id="pivinfo" class="val">x ${(l.px||0).toFixed(0)}  y ${(l.py||0).toFixed(0)}  rot ${Math.round(l.prot||0)}°</span> <button onclick="resetPivot()">↺</button></div></div>
 <small style="color:#7a8599;display:block;padding:2px 0 4px">Drag the <b style="color:#ffd24a">gold</b> handle on canvas to move the FX; drag the <b style="color:#4ad0ff">blue</b> handle to set its rotation origin.</small>
 ${trigHtml(l)}
 <div class="row"><label>Colors</label><div class="v cols"><input type="color" value="${l.c1}" oninput="setP('c1',this.value)"><input type="color" value="${l.c2}" oninput="setP('c2',this.value)"><small>start→end</small></div></div>`;
 for(const k in l){if(['type','c1','c2'].includes(k))continue;const f=FIELDS[k];if(!f)continue;
 const r=document.createElement('div');r.className='row';
 if(f[1]==='anc')r.innerHTML=`<label>${f[0]}</label><div class="v"><select onchange="setP('anchor',this.value)">${ANCHORS().map(o=>`<option ${o===l.anchor?'selected':''}>${o}</option>`).join('')}</select></div>`;
 else if(f[1]==='r')r.innerHTML=`<label>${f[0]}</label><div class="v"><input type="range" min="${f[2]}" max="${f[3]}" step="${f[4]}" value="${l[k]}" oninput="setP('${k}',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${l[k]}</span></div>`;
 else if(f[1]==='sel')r.innerHTML=`<label>${f[0]}</label><div class="v"><select onchange="setP('${k}',this.value)">${f[2].map(o=>`<option ${o===l[k]?'selected':''}>${o}</option>`).join('')}</select></div>`;
 else r.innerHTML=`<label>${f[0]}</label><div class="v"><input type="checkbox" ${l[k]?'checked':''} onchange="setP('${k}',this.checked)${k==='can_hit'?';renderProps()':''}"></div>`;
 d.appendChild(r)}
 const bwrap=document.createElement('div');bwrap.innerHTML=battleHtml(l);d.appendChild(bwrap)}
function setP(k,v){fx.layers[sel][k]=v;if(k==='anchor')renderLayers()}
// ---- [HIT DETECTION] ---- vs target dummy (drives per-layer on_hit trigger; same semantics in Solo & Battle)
// arcDum/fxHitsDummy return the FIRST OVERLAP POINT [x,y] with the target, or null.
// Battle FX spawn exactly at that point of collision. Identical in Solo & Battle.
function arcDum(x,y,r,a0,a1){const n=16;for(let i=0;i<=n;i++){const a=a0+(a1-a0)*i/n,qx=x+Math.cos(a)*r,qy=y+Math.sin(a)*r;if(dummyHit(qx,qy))return[qx,qy]}return null}
function beamGeom(p){const l=p.l;
 if(p.dirA!==undefined)return{a:p.dirA,ox:p.ox,oy:p.oy,td:p.td||0,hd:p.hd!==undefined?p.hd:(l.length||0)};
 let a=((l.angle_deg||0)+(l.prot||0))*D;if(l.aim_weapon&&curJ&&curJ._wW!==undefined)a=curJ._wW+(l.prot||0)*D;
 return{a,ox:p.x,oy:p.y,td:0,hd:l.length||0}}
function dummyCenter(){const G=dummyGeom();return[G.X,(G.top+G.bot)/2]}
function fxHitsDummy(p,el){const l=p.l,t=p.age/p.life;
 if(p.type==='ring'){const r=lerp(l.radius_start,l.radius_end,t);return arcDum(p.x,p.y,r,0,6.28)}
 if(p.type==='crescent'){const r=lerp(l.radius_start,l.radius_end,t),spin=(l.spin_deg||0)*D*t,a0=p.a0+spin,half=(l.arc_deg*D)/2;return arcDum(p.x,p.y,r,a0-half,a0+half)}
 if(p.type==='flash'){const s=(p.sz||20)*(1-t*0.5);return dummyHit(p.x,p.y)?[p.x,p.y]:arcDum(p.x,p.y,s,0,6.28)}
 if(p.type==='beam'){const g=beamGeom(p);
  for(let i=0;i<=24;i++){const dd=lerp(g.td,g.hd,i/24),bx=g.ox+Math.cos(g.a)*dd,by=g.oy+Math.sin(g.a)*dd;if(dummyHit(bx,by))return[bx,by]}return null}
 return dummyHit(p.x,p.y)?[p.x,p.y]:null}
// ---- [SIMULATION & RENDER] ----
function hex(c){return[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)]}
function colAt(l,t){const a=hex(l.c1),b=hex(l.c2);return`rgb(${lerp(a[0],b[0],t)|0},${lerp(a[1],b[1],t)|0},${lerp(a[2],b[2],t)|0})`}
function aPos(l){let x=W/2,y=H/2;if(l.anchor&&l.anchor!=='point'&&curJ&&curJ[l.anchor])[x,y]=curJ[l.anchor];return[x+(l.px||0),y+(l.py||0)]}
function spawn(l,li,n){const[x,y]=aPos(l);
 for(let i=0;i<n;i++){const life=rnd(l.life_min,l.life_max),p={li,l,x,y,life,age:0,type:l.type};
 if(l.type==='particles'||l.type==='trail'){let base=((l.angle_deg||0)+(l.prot||0))*D;
  const a=base+rnd(-.5,.5)*(l.spread_deg||360)*D,s=rnd(l.speed_min,l.speed_max);
  p.vx=Math.cos(a)*s;p.vy=Math.sin(a)*s;p.sz=rnd(l.size_min,l.size_max);p.rot=rnd(0,6.28)}
 if(l.type==='ring'||l.type==='crescent'){let a0=((l.angle_deg||0)+(l.prot||0))*D;
  if(l.type==='crescent'&&l.follow&&curJ&&curJ._wW!==undefined)a0=curJ._wW+(l.prot||0)*D;p.a0=a0}
 if(l.type==='flash')p.sz=rnd(l.size_min,l.size_max);
 if(l.type==='afterimage'){p.pose=poseAt(curT());p.rootJ=aPos(l)}
 if(l.type==='beam')p.seed=Math.random()*99;
 parts.push(p)}}
function play(){parts=[];acc={};spawned={};hitAt=null;playing=true;t0=performance.now();last=t0;$('stat').textContent='playing';poseMode=false;$('posebtn').className=''}
function stop(){playing=false;parts=[]}
function tick(now){requestAnimationFrame(tick);rszChk();
 const slow=+$('slow').value;let dt=Math.min(now-last,50)/1000*slow;last=now;
 const dur=+$('dur').value;
 let el,animT;
 if(playing){el=(now-t0)*slow;animT=(el%dur)/dur;
  const pDur=dur+chainSpan();
  if(el>pDur){if($('loop').checked){play();el=0;animT=0}else{el=pDur;animT=1;if(!parts.length){playing=false;$('stat').textContent='done'}}}}
 else{el=0;animT=poseMode?scrubT:0}
 const pose=(poseMode&&selKF>=0)?keyframes[selKF].p:poseAt(animT);
 curJ=joints(pose);
 if(playing){fx.layers.forEach((l,li)=>{if(isBI(l)||l.type==='image')return;
  if((l.trig||'immediate')==='on_hit'){if(!dummyOn()||hitAt===null||el<hitAt+(l.delay_ms||0))return}
  else if(el<layerStart(li)+(l.delay_ms||0))return;
  const one=['ring','flash','crescent','beam'].includes(l.type)||(l.type==='particles'&&l.burst);
  if(one){if(!spawned[li]){spawned[li]=1;spawn(l,li,l.type==='particles'?l.count:1)}}
  else{const rate=l.emit_rate||60;acc[li]=(acc[li]||0)+dt*rate;while(acc[li]>=1){acc[li]--;spawn(l,li,1)}}});
 for(let i=parts.length-1;i>=0;i--){const p=parts[i];p.age+=dt*1000;if(p.age>=p.life){parts.splice(i,1);continue}
  const homingActive=p.l.homing&&dummyOn()&&!p.bfx;
  if(p.l.follow&&p.l.anchor!=='point'&&curJ[p.l.anchor]&&!(homingActive&&p.type==='crescent')){[p.x,p.y]=aPos(p.l);
   if(p.type==='crescent'&&curJ._wW!==undefined&&p.l.follow&&!homingActive)p.a0=curJ._wW+(p.l.prot||0)*D}
  // homing: steer toward the target every tick until collision (particles keep speed; crescent travels at homing_speed)
  if(homingActive&&p.vx!==undefined){const[tx,ty]=dummyCenter(),s=Math.hypot(p.vx,p.vy)||1,ha=Math.atan2(ty-p.y,tx-p.x);p.vx=Math.cos(ha)*s;p.vy=Math.sin(ha)*s}
  else if(homingActive&&p.type==='crescent'){const[tx,ty]=dummyCenter(),ha=Math.atan2(ty-p.y,tx-p.x),s=p.l.homing_speed||320;p.x+=Math.cos(ha)*s*dt;p.y+=Math.sin(ha)*s*dt}
  if(p.vx!==undefined){const dr=p.l.drag??1;p.vx*=Math.pow(dr,dt*60);p.vy*=Math.pow(dr,dt*60);p.vy+=(p.l.gravity||0)*dt;p.x+=p.vx*dt;p.y+=p.vy*dt}
  // beam travel: head advances at travel_speed from the fire point; after detach_ms the tail leaves the source
  if(p.type==='beam'){const l=p.l,ts=l.travel_speed||0;
   if(ts>0){p.hd=ts*p.age/1000;
    p.td=Math.max(ts*Math.max(0,p.age-(l.detach_ms||0))/1000,p.hd-(l.length||0));
    if(p.td<0)p.td=0}
   else{p.hd=l.length||0;p.td=0}
   const attached=(p.td||0)<=0;
   if(attached||p.ox===undefined){p.ox=p.x;p.oy=p.y}
   if(attached||p.dirA===undefined){let a=((l.angle_deg||0)+(l.prot||0))*D;
    if(l.aim_weapon&&curJ&&curJ._wW!==undefined)a=curJ._wW+(l.prot||0)*D;p.dirA=a}
   if(homingActive){const[tx,ty]=dummyCenter(),bx=p.ox+Math.cos(p.dirA)*(p.td||0),by=p.oy+Math.sin(p.dirA)*(p.td||0);
    p.dirA=Math.atan2(ty-by,tx-bx)}}}
 // hit pass: battle/on_hit fires once per loop at the first overlap point; homing FX end on impact
 if(dummyOn()){for(let i=parts.length-1;i>=0;i--){const p=parts[i];if(p.bfx)continue;
  const wantsHit=p.l.can_hit&&hitAt===null;if(!wantsHit&&!p.l.homing)continue;
  const hp=fxHitsDummy(p,el);if(!hp)continue;
  if(wantsHit){hitAt=el;if(p.l.battle)onBattleHit(p,hp[0],hp[1])}
  if(p.l.homing)parts.splice(i,1)}}}
 // draw
 const g=ctx.createRadialGradient(W/2,H/2,0,W/2,H/2,Math.max(W,H)/1.4);g.addColorStop(0,'#141824');g.addColorStop(1,'#07080c');
 ctx.globalCompositeOperation='source-over';ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
 camInit();ctx.save();ctx.setTransform(cam.z,0,0,cam.z,W/2-cam.x*cam.z,H/2-cam.y*cam.z);
 ctx.strokeStyle='#1c2432';ctx.beginPath();ctx.moveTo(cam.x-W/cam.z,H/2+40+52);ctx.lineTo(cam.x+W/cam.z,H/2+40+52);ctx.stroke();
 if(dummyOn())drawDummy();
 const showF=$('showfig').checked,figV=$('fig').value;
 ensureBuiltin(fx.layers);
 fx.layers.forEach(l=>{
  if(l.type==='figure'){if(!showF||l.visible===false)return;
   if(poseMode&&selKF>=0&&keyframes.length>1){const pm=poseMode;poseMode=false;
    [keyframes[selKF-1],keyframes[selKF+1]].forEach(k=>{if(!k)return;
     ctx.globalAlpha=0.5*(l.opacity??1);drawFigure(joints(k.p),figV);ctx.globalAlpha=1});
    poseMode=pm}
   drawBody(curJ,figV,l.opacity??1)}
  else if(l.type==='weapon'){if(!showF||(l.visible===false&&!weaponEdit))return;
   drawWeapon(curJ,figV,weaponEdit?1:(l.opacity??1))}
  else if(l.type==='image')drawImageLayer(l);
  else render(el,l)});
 render(el,'__bfx__');
 drawJointDots(curJ);
 drawPivotGizmo();
 ctx.restore();
 $('zl').textContent=Math.round(cam.z*100)+'%';
 if(playing&&$('ph'))$('ph').style.left=(animT*100)+'%'}
function rszChk(){if(cv.width!==cv.clientWidth||cv.height!==cv.clientHeight)rsz()}
function render(el,lay){for(const p of parts){if(lay==='__bfx__'){if(!p.bfx)continue}else if(lay&&p.l!==lay)continue;const l=p.l,t=p.age/p.life,fade=1-t*t;
 ctx.globalCompositeOperation=l.blend==='additive'?'lighter':'source-over';
 ctx.shadowBlur=l.glow||0;const col=colAt(l,t);ctx.shadowColor=col;ctx.fillStyle=col;ctx.strokeStyle=col;ctx.globalAlpha=fade;
 if(p.type==='particles'||p.type==='trail'){let s=p.sz;const m=l.size_over_life;
  if(m==='shrink')s*=1-t;else if(m==='grow')s*=0.3+t;else if(m==='pulse')s*=0.7+0.5*Math.sin(t*12);
  if(l.shape==='spark'&&p.vx!==undefined){const vl=Math.hypot(p.vx,p.vy)||1,k=Math.min(0.06,14/vl);
   ctx.lineWidth=Math.max(1,s*0.5);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x-p.vx*k,p.y-p.vy*k);ctx.stroke()}
  else if(l.shape==='square'){ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.rot+t*4);ctx.fillRect(-s/2,-s/2,s,s);ctx.restore()}
  else{ctx.beginPath();ctx.arc(p.x,p.y,Math.max(0.4,s/2),0,6.28);ctx.fill()}
  if(p.type==='trail'&&l.line&&p.px!==undefined){ctx.lineWidth=Math.max(1,s*0.4);ctx.beginPath();ctx.moveTo(p.px,p.py);ctx.lineTo(p.x,p.y);ctx.stroke()}p.px=p.x;p.py=p.y}
 else if(p.type==='ring'){const r=lerp(l.radius_start,l.radius_end,t);let th=l.thickness;if(l.thin_out)th*=1-t*0.7;
  ctx.lineWidth=Math.max(0.5,th);ctx.beginPath();ctx.arc(p.x,p.y,r,0,6.28);ctx.stroke()}
 else if(p.type==='flash'){const s=p.sz*(1-t*0.5),gg=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,s);
  gg.addColorStop(0,colAt(l,0));gg.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=gg;ctx.beginPath();ctx.arc(p.x,p.y,s,0,6.28);ctx.fill();
  if(l.rays){ctx.lineWidth=2;for(let i=0;i<l.rays;i++){const a=i/l.rays*6.28+(l.prot||0)*D;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+Math.cos(a)*s*1.6,p.y+Math.sin(a)*s*1.6);ctx.stroke()}}}
 else if(p.type==='crescent'){const r=lerp(l.radius_start,l.radius_end,t),spin=(l.spin_deg||0)*D*t;
  const a0=p.a0+spin,half=(l.arc_deg*D)/2;ctx.lineWidth=Math.max(1,l.thickness*(1-t*0.5));ctx.lineCap='round';
  ctx.beginPath();ctx.arc(p.x,p.y,r,a0-half,a0+half);ctx.stroke()}
 else if(p.type==='afterimage'){ctx.globalAlpha=fade*0.7;
  if(l.ghost_rig&&p.pose){const save=[W,H];const J2=(()=>{const j={...joints(p.pose)};return j})();
   // freeze at spawn root
   ctx.save();ctx.strokeStyle=col;ctx.lineWidth=3;ctx.lineCap='round';ctx.shadowBlur=l.glow;ctx.shadowColor=col;
   const J=joints(p.pose);const dx=p.rootJ[0]-J.hip[0],dy=p.rootJ[1]-J.hip[1];
   const L2=(a,b)=>{ctx.beginPath();ctx.moveTo(J[a][0]+dx,J[a][1]+dy);ctx.lineTo(J[b][0]+dx,J[b][1]+dy);ctx.stroke()};
   L2('hip','chest');L2('chest','l_shoulder');L2('chest','r_shoulder');L2('hip','l_hip');L2('hip','r_hip');
   L2('l_shoulder','l_elbow');L2('l_elbow','l_hand');L2('r_shoulder','r_elbow');L2('r_elbow','r_hand');
   L2('l_hip','l_knee');L2('l_knee','l_foot');L2('r_hip','r_knee');L2('r_knee','r_foot');
   ctx.beginPath();ctx.arc(J.head[0]+dx,J.head[1]+dy-4,10,0,6.28);ctx.stroke();ctx.restore()}
  else{ctx.save();ctx.translate(p.x,p.y);ctx.rotate((l.prot||0)*D);ctx.beginPath();ctx.roundRect(-l.w/2,-l.h/2,l.w,l.h,l.w/2);ctx.fill();ctx.restore()}}
 else if(p.type==='beam'){const g=beamGeom(p);
  if(g.hd>g.td){const pulse=1+0.3*Math.sin(el/1000*6.28*(l.pulse_hz||0)+p.seed),seg=Math.max(2,l.segments|0);
   const wBase=l.width??10;
   const ws=lerp(l.w_start0??wBase,l.w_start1??wBase,t)*pulse;// width at start point (tail/source side)
   const we=lerp(l.w_end0??wBase,l.w_end1??wBase,t)*pulse;   // width at end point (head)
   const pts=[];for(let i=0;i<=seg;i++){const f=i/seg,j=(i===0||i===seg)?0:(l.jitter||0),dd=lerp(g.td,g.hd,f);
    pts.push([g.ox+Math.cos(g.a)*dd+rnd(-j,j),g.oy+Math.sin(g.a)*dd+rnd(-j,j)])}
   ctx.lineCap='round';
   for(let i=0;i<seg;i++){ctx.lineWidth=Math.max(1,lerp(ws,we,(i+0.5)/seg));
    ctx.beginPath();ctx.moveTo(pts[i][0],pts[i][1]);ctx.lineTo(pts[i+1][0],pts[i+1][1]);ctx.stroke()}
   ctx.strokeStyle='#fff';
   for(let i=0;i<seg;i++){const d0=lerp(g.td,g.hd,i/seg),d1=lerp(g.td,g.hd,(i+1)/seg);
    ctx.lineWidth=Math.max(0.5,lerp(ws,we,(i+0.5)/seg)*0.35);
    ctx.beginPath();ctx.moveTo(g.ox+Math.cos(g.a)*d0,g.oy+Math.sin(g.a)*d0);ctx.lineTo(g.ox+Math.cos(g.a)*d1,g.oy+Math.sin(g.a)*d1);ctx.stroke()}}}}
 ctx.globalAlpha=1;ctx.shadowBlur=0;ctx.globalCompositeOperation='source-over'}
// ---- [EXPORT/IMPORT] ---- pb_fx (standalone action FX) lives here; pb_character in character_creator.js
function buildJson(){fx.layers.forEach(l=>{if(l.can_hit)ensureBattle(l)});
 return JSON.stringify({format:'pb_fx',version:2,name:$('fxname').value,
 trigger:$('trig').value,modes:['solo','battle'],duration_ms:+$('dur').value,
 figure:'custom',action:{name:curActionKey()||'idle',keyframes},layers:fx.layers,target_dummy:dummyExport(),
 trigger_semantics:{on_hit:'Layer plays only when a layer flagged can_hit contacts the target; dormant if no target present; fires once per loop cycle. Identical in Solo & Battle.'},
 battle_semantics:BATTLE_SEMANTICS,fx_semantics:FX_SEMANTICS},null,1)}
let exportKind='char';
function openJson(kind){jsonEl.style.display='flex';exportKind=kind||exportKind;
 $('jt').textContent=kind?'Export — give this to Claude':'Import';
 $('jta').value=kind?(kind==='fx'?buildJson():buildCharJson()):''}
function copyJson(){navigator.clipboard.writeText($('jta').value)}
function dlJson(){const a=document.createElement('a');a.href='data:application/json,'+encodeURIComponent($('jta').value);a.download=exportKind==='fx'?($('fxname').value+'.fx.json'):(CH.name+'.character.json');a.click()}
function applyJson(){try{const o=JSON.parse($('jta').value);
 if(o.format==='pb_character'){importChar(o);jsonEl.style.display='none';return}
 // pb_fx import: applied onto the current wizard action (creates it if needed)
 const ak=(o.action&&o.action.name&&CH.actions[o.action.name])?o.action.name:(curActionKey()||'idle');
 ensureAction(ak);const a=CH.actions[ak];
 a.fx_layers=(o.layers||[]).filter(l=>!isBI(l));
 if(o.trigger)a.trigger=o.trigger;if(o.duration_ms)a.duration_ms=o.duration_ms;
 if(o.action&&o.action.keyframes){a.keyframes=o.action.keyframes;fixKF(a.keyframes)}
 if(o.name)$('fxname').value=o.name;dummyImport(o.target_dummy);
 gotoStep('act:'+ak);jsonEl.style.display='none';play()}catch(e){alert('Bad JSON: '+e.message)}}
