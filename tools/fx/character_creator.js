// ================= CHARACTER CREATOR =================
let appMode='fx',CH=null,curStep='setup',weaponEdit=false,dragWP=-1;
const ACT_DEFS=[
 ['idle','Idle','ambient',0],['run','Running','ambient',0],
 ['attack_normal','Normal Attack','on_hit',1],['attack_special','Special Attack','on_hit',1],
 ['ultimate','Ultimate','on_ult',1],['defend','Block / Dodge','on_parry',0],
 ['special_ability','Special Ability','ambient',0],['impact','Impact (got hit)','on_hit',0]];
const SAB_PRESETS=['none','shield','heal','clone','time_slow','rage','teleport','dual_defense'];
const DEF_KF={
 idle:()=>[{t:0,p:P({})},{t:.5,p:P({ry:2,sp:2})},{t:1,p:P({})}],
 run:()=>[{t:0,p:P({lth:-35,lsh:40,rth:30,rsh:8,lua:-30,rua:25,sp:6})},{t:.5,p:P({lth:30,lsh:8,rth:-35,rsh:40,lua:25,rua:-30,sp:6})},{t:1,p:P({lth:-35,lsh:40,rth:30,rsh:8,lua:-30,rua:25,sp:6})}],
 attack_normal:()=>[{t:0,p:P({rua:-150,rfa:-40,wp:-50,sp:-10,rx:-10})},{t:.4,p:P({rua:-155,rfa:-45,wp:-55,sp:-12,rx:-14})},{t:.6,p:P({rua:35,rfa:25,wp:35,sp:14,rx:25,lth:25,rth:-30})},{t:1,p:P({})}],
 attack_special:()=>[{t:0,p:P({rx:-40,rua:-160,rfa:-50,wp:-60,sp:-14})},{t:.45,p:P({rx:30,rua:40,rfa:30,wp:40,sp:16,lth:30,rth:-35})},{t:.7,p:P({rx:45,rua:20,rfa:15,wp:20,sp:8})},{t:1,p:P({})}],
 ultimate:()=>[{t:0,p:P({})},{t:.25,p:P({rua:-170,rfa:-10,wp:-80,lua:-40,sp:-8,ry:-6})},{t:.7,p:P({rua:-170,rfa:-10,wp:-80,lua:-40,sp:-8,ry:-10})},{t:1,p:P({})}],
 defend_block:()=>[{t:0,p:P({})},{t:.2,p:P({rua:-120,rfa:-60,wp:-90,sp:-4,lua:-30})},{t:.8,p:P({rua:-120,rfa:-60,wp:-90,sp:-4,lua:-30})},{t:1,p:P({})}],
 defend_dodge:()=>[{t:0,p:P({})},{t:.35,p:P({rx:-55,sp:18,lth:-28,rth:24,ry:6})},{t:.7,p:P({rx:-70,sp:8})},{t:1,p:P({})}],
 special_ability:()=>[{t:0,p:P({})},{t:.3,p:P({lua:-140,rua:-140,lfa:-20,rfa:-20,sp:-6,ry:-4})},{t:.75,p:P({lua:-150,rua:-150,lfa:-25,rfa:-25,sp:-6,ry:-8})},{t:1,p:P({})}],
 impact:()=>[{t:0,p:P({})},{t:.15,p:P({rx:14,sp:14,hd:12,rua:15,lua:-25,ry:4})},{t:.5,p:P({rx:8,sp:8,hd:6})},{t:1,p:P({})}]};
function newChar(){return{name:'new_fighter',palette:{body:'#8fa0b8',accent:'#ff5050'},defense:'block',
 bones:{ua:22,fa:20,th:26,sh:24,torso:36},
 weapon:{points:[[14,0],[34,0]],thickness:3,color:'#d8dee9'},
 special_ability:{preset:'none',params:{duration_ms:3000,cooldown_ms:8000,magnitude:25},fx_layers:[]},
 actions:{}}}
function ensureAction(ak){if(CH.actions[ak])return;const d=ACT_DEFS.find(a=>a[0]===ak);let kf;
 if(ak==='defend')kf=CH.defense==='block'?DEF_KF.defend_block():DEF_KF.defend_dodge();
 else if(ak==='defend2')kf=CH.defense==='block'?DEF_KF.defend_dodge():DEF_KF.defend_block();
 else kf=(DEF_KF[ak]||DEF_KF.idle)();
 fixKF(kf);
 // baseline actions start from Idle's 1st KF pose (one-time copy, editable after)
 if(ak!=='idle'&&ak!=='defend2'&&ACT_DEFS.some(a=>a[0]===ak)){
  let src=CH.actions.idle?CH.actions.idle.keyframes:null;
  if(!src){src=DEF_KF.idle();fixKF(src)}
  kf[0]={t:kf[0].t,p:{...src[0].p}}}
 CH.actions[ak]={trigger:ak==='defend2'?'on_parry':(d?d[2]:'ambient'),duration_ms:ak==='run'||ak==='idle'?900:800,
  keyframes:kf,fx_layers:[]}}
// --- custom weapon math (points are in weapon-local frame, origin=r_hand, +x along weapon angle) ---
function wpnWorld(hand,wW){if(!CH||!CH.weapon.points.length)return[];const c=Math.cos(wW),s=Math.sin(wW);
 return CH.weapon.points.map(p=>[hand[0]+p[0]*c-p[1]*s,hand[1]+p[0]*s+p[1]*c])}
function wpnMid(pts,hand){const chain=[hand,...pts];let tot=0;const segs=[];
 for(let i=0;i<chain.length-1;i++){const d=Math.hypot(chain[i+1][0]-chain[i][0],chain[i+1][1]-chain[i][1]);segs.push(d);tot+=d}
 if(!tot)return[hand[0],hand[1]];let h=tot/2;
 for(let i=0;i<segs.length;i++){if(h<=segs[i]){const f=h/(segs[i]||1);return[lerp(chain[i][0],chain[i+1][0],f),lerp(chain[i][1],chain[i+1][1],f)]}h-=segs[i]}
 return pts[pts.length-1]}
function wpnLocal(wx,wy){const hand=curJ.r_hand,wW=curJ._wW,dx=wx-hand[0],dy=wy-hand[1],c=Math.cos(-wW),s=Math.sin(-wW);
 return[+(dx*c-dy*s).toFixed(1),+(dx*s+dy*c).toFixed(1)]}
function wpnClick(wx,wy){if(!curJ)return;const pts=curJ._wpts||[];
 for(let i=0;i<pts.length;i++){if(Math.hypot(pts[i][0]-wx,pts[i][1]-wy)<9/cam.z){dragWP=i;return}}
 CH.weapon.points.push(wpnLocal(wx,wy));const c=$('wpc');if(c)c.textContent=CH.weapon.points.length}
function wpnUndo(){CH.weapon.points.pop()}
function wpnClear(){CH.weapon.points=[]}
// --- wizard ---
function wizSteps(){const s=[{k:'setup',n:'Character Setup'},{k:'weapon',n:'Weapon Designer'}];
 ACT_DEFS.forEach(a=>s.push({k:'act:'+a[0],n:a[1]}));
 if(CH.special_ability.preset==='dual_defense'){const i=s.findIndex(x=>x.k==='act:special_ability');
  s.splice(i+1,0,{k:'act:defend2',n:'Second Defense ('+(CH.defense==='block'?'Dodge':'Block')+')'})}
 s.push({k:'review',n:'Review & Export'});return s}
function renderWiz(){const d=$('wsteps');d.innerHTML='';wizSteps().forEach((s,i)=>{
 const done=s.k.startsWith('act:')?!!CH.actions[s.k.slice(4)]:(s.k==='setup'||s.k==='weapon');
 const e=document.createElement('div');e.className='wstep'+(s.k===curStep?' cur':'')+(done?' done':'');
 e.textContent=(i+1)+'. '+s.n;e.onclick=()=>gotoStep(s.k);d.appendChild(e)})}
function saveStep(){if(appMode!=='char'||!CH)return;
 if(curStep.startsWith('act:')){const a=CH.actions[curStep.slice(4)];
  if(a){a.duration_ms=+$('dur').value;a.trigger=$('trig').value;a.keyframes=keyframes;a.fx_layers=fx.layers}}}
function loadCharAction(ak){ensureAction(ak);const a=CH.actions[ak];
 keyframes=a.keyframes;fx.layers=ensureBuiltin(a.fx_layers);$('dur').value=a.duration_ms;$('trig').value=a.trigger;
 $('fxname').value=CH.name+'_'+ak;sel=fx.layers.length?0:-1;selKF=-1;
 if(poseMode)togglePose();renderTL();renderLayers();renderProps();play()}
function gotoStep(k){saveStep();curStep=k;weaponEdit=false;
 if(k==='setup'||k==='review'){ensureAction('idle');loadCharAction('idle')}
 else if(k==='weapon'){ensureAction('idle');loadCharAction('idle');stop();weaponEdit=true;
  $('stat').textContent='weapon edit — click canvas to add points'}
 else if(k.startsWith('act:')){loadCharAction(k.slice(4))}
 renderWiz();renderStepUI()}
function chRow(lbl,inner){return `<div class="row"><label>${lbl}</label><div class="v">${inner}</div></div>`}
// Battle properties are now per-FX-layer (see battleHtml/ensureBattle in fx_engine.js): tick 'Can hit target' on a layer to edit them.
function chSet(path,v){const seg=path.split('.');let o=CH;while(seg.length>1)o=o[seg.shift()];o[seg[0]]=v}
function sabSet(k,v){if(k==='preset'){CH.special_ability.preset=v;renderWiz();renderStepUI()}else CH.special_ability.params[k]=+v}
function renderStepUI(){const d=$('stepui');if(appMode!=='char'){d.innerHTML='';return}let h='';
 if(curStep==='setup'){h=`<h3 style="padding-left:0">Character Setup</h3>`+
  chRow('Name',`<input type="text" value="${CH.name}" onchange="chSet('name',this.value)">`)+
  chRow('Body color',`<input type="color" value="${CH.palette.body}" oninput="chSet('palette.body',this.value)">`)+
  chRow('Accent color',`<input type="color" value="${CH.palette.accent}" oninput="chSet('palette.accent',this.value)">`)+
  chRow('Torso len',`<input type="range" min="20" max="60" step="1" value="${CH.bones.torso}" oninput="chSet('bones.torso',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${CH.bones.torso}</span>`)+
  chRow('Upper arm',`<input type="range" min="10" max="40" step="1" value="${CH.bones.ua}" oninput="chSet('bones.ua',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${CH.bones.ua}</span>`)+
  chRow('Forearm',`<input type="range" min="10" max="40" step="1" value="${CH.bones.fa}" oninput="chSet('bones.fa',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${CH.bones.fa}</span>`)+
  chRow('Thigh',`<input type="range" min="12" max="45" step="1" value="${CH.bones.th}" oninput="chSet('bones.th',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${CH.bones.th}</span>`)+
  chRow('Shin',`<input type="range" min="12" max="45" step="1" value="${CH.bones.sh}" oninput="chSet('bones.sh',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${CH.bones.sh}</span>`)+
  chRow('Defense',`<select onchange="chSet('defense',this.value);renderWiz()"><option value="block" ${CH.defense==='block'?'selected':''}>Block</option><option value="dodge" ${CH.defense==='dodge'?'selected':''}>Dodge</option></select>`)+
  `<small style="color:#7a8599;display:block;padding:4px 0">Pick Block or Dodge. The "dual_defense" special ability preset unlocks both later.</small>`}
 else if(curStep==='weapon'){h=`<h3 style="padding-left:0">${CH.name} — Weapon Designer</h3>
  <small style="color:#7a8599;display:block;padding:4px 0">Click on the canvas to add polyline points outward from the hand. Drag points to adjust. Anchors <b>weapon_mid</b> and <b>weapon_tip</b> are auto-generated for FX layers.</small>`+
  chRow('Thickness',`<input type="range" min="1" max="10" step="0.5" value="${CH.weapon.thickness}" oninput="chSet('weapon.thickness',+this.value);this.nextElementSibling.textContent=this.value"><span class="val">${CH.weapon.thickness}</span>`)+
  chRow('Color',`<input type="color" value="${CH.weapon.color}" oninput="chSet('weapon.color',this.value)">`)+
  chRow('Points',`<span class="val" id="wpc">${CH.weapon.points.length}</span><button onclick="wpnUndo();renderStepUI()">Undo</button><button onclick="wpnClear();renderStepUI()">Clear</button>`)}
 else if(curStep==='act:special_ability'){const sa=CH.special_ability;
  h=`<h3 style="padding-left:0">${CH.name} — Special Ability</h3>`+
  chRow('Preset base',`<select onchange="sabSet('preset',this.value)">${SAB_PRESETS.map(p=>`<option ${p===sa.preset?'selected':''}>${p}</option>`).join('')}</select>`)+
  chRow('Duration ms',`<input type="number" value="${sa.params.duration_ms}" onchange="sabSet('duration_ms',this.value)">`)+
  chRow('Cooldown ms',`<input type="number" value="${sa.params.cooldown_ms}" onchange="sabSet('cooldown_ms',this.value)">`)+
  chRow('Magnitude',`<input type="number" value="${sa.params.magnitude}" onchange="sabSet('magnitude',this.value)">`)+
  `<small style="color:#7a8599;display:block;padding:4px 0">Preset defines the mechanic; add custom FX layers below for its visuals. <b>dual_defense</b> adds a second defense animation step.</small>`}
 else if(curStep.startsWith('act:')){const ak=curStep.slice(4),def=ACT_DEFS.find(a=>a[0]===ak);
  h=`<h3 style="padding-left:0">${CH.name} — ${def?def[1]:ak==='defend2'?'Second Defense':ak}</h3>
  <small style="color:#7a8599;display:block;padding:4px 0">Sculpt the animation with Pose Mode + keyframes, add FX layers on the left. Trigger/duration in the top bar are saved per action.</small>
  <small style="color:#7a8599;display:block;padding:4px 0"><b>Battle Properties</b> live on each FX layer: tick <b>Can hit target</b> on a layer to set its Damage, Attack effects (Explode / Scatter / Pierce / Slash — stackable, visual only) and Defence (Deflect / Block — mutually exclusive).</small>`}
 else if(curStep==='review'){const done=Object.keys(CH.actions).length,need=wizSteps().filter(s=>s.k.startsWith('act:')).length;
  h=`<h3 style="padding-left:0">${CH.name} — Review & Export</h3>
  <div class="row"><label>Name</label><div class="v"><b>${CH.name}</b></div></div>
  <div class="row"><label>Defense</label><div class="v">${CH.defense}${CH.special_ability.preset==='dual_defense'?' + both (dual)':''}</div></div>
  <div class="row"><label>Weapon pts</label><div class="v">${CH.weapon.points.length}</div></div>
  <div class="row"><label>Ability</label><div class="v">${CH.special_ability.preset}</div></div>
  <div class="row"><label>Actions</label><div class="v">${done}/${need} created</div></div>
  <button class="pri" style="width:100%;margin-top:8px" onclick="openJson(1)">Export Character JSON</button>
  <small style="color:#7a8599;display:block;padding:4px 0">Give this JSON to Claude to implement in Solo & Battle modes.</small>`}
 d.innerHTML=h}
function wizNext(){const s=wizSteps(),i=s.findIndex(x=>x.k===curStep);if(i<s.length-1)gotoStep(s[i+1].k)}
function wizPrev(){const s=wizSteps(),i=s.findIndex(x=>x.k===curStep);if(i>0)gotoStep(s[i-1].k)}
function toggleMode(){if(appMode==='fx'){appMode='char';if(!CH)CH=newChar();enterChar()}else{saveStep();appMode='fx';exitChar()}}
function enterChar(){$('apptitle').textContent='CHARACTER CREATOR';$('modebtn').textContent='✦ FX Mode';
 $('wiz').style.display='flex';$('fxpresets').style.display='none';
 $('fig').disabled=true;$('act').disabled=true;$('fig').value='custom';
 curStep='setup';gotoStep('setup')}
function exitChar(){$('apptitle').textContent='FX CREATOR';$('modebtn').textContent='⚔ Characters';
 $('wiz').style.display='none';$('fxpresets').style.display='block';$('stepui').innerHTML='';
 $('fig').disabled=false;$('act').disabled=false;weaponEdit=false;
 $('fig').value='swordsman';fx.layers=ensureBuiltin([]);sel=-1;loadAction();renderLayers();renderProps()}
function buildCharJson(){saveStep();const acts={};for(const k in CH.actions){const a=CH.actions[k];
 (a.fx_layers||[]).forEach(l=>{if(l.can_hit)ensureBattle(l)});
 acts[k]={trigger:a.trigger,duration_ms:a.duration_ms,keyframes:a.keyframes,fx_layers:a.fx_layers}}
 return JSON.stringify({format:'pb_character',version:1,name:CH.name,rig:'humanoid_v2',modes:['solo','battle'],
  bones:CH.bones,
  palette:CH.palette,defense:CH.defense,dual_defense:CH.special_ability.preset==='dual_defense',
  weapon:{points:CH.weapon.points,thickness:CH.weapon.thickness,color:CH.weapon.color,anchors:['weapon_mid','weapon_tip']},
  special_ability:CH.special_ability,actions:acts,target_dummy:dummyExport(),battle_semantics:BATTLE_SEMANTICS},null,1)}
function importChar(o){CH=newChar();CH.name=o.name||CH.name;if(o.palette)CH.palette=o.palette;if(o.bones)CH.bones=o.bones;
 if(o.defense)CH.defense=o.defense;if(o.weapon)CH.weapon={points:o.weapon.points||[],thickness:o.weapon.thickness||3,color:o.weapon.color||'#d8dee9'};
 if(o.special_ability)CH.special_ability=o.special_ability;
 CH.actions={};for(const k in (o.actions||{})){const a=o.actions[k];fixKF(a.keyframes||[]);
  CH.actions[k]={trigger:a.trigger||'ambient',duration_ms:a.duration_ms||800,keyframes:a.keyframes||DEF_KF.idle(),
   fx_layers:(a.fx_layers||[]).map(l=>{if(l.can_hit)ensureBattle(l);return l})}}
 dummyImport(o.target_dummy);
 appMode='char';enterChar()}
