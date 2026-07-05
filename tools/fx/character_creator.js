// ================= CHARACTER WIZARD =================
// The tool is wizard-only: it always edits a pb_character. Standalone FX authoring lives
// inside each action step (same layer engine); pb_fx export remains available per action.
// Sections: [STATE] [ACTION DEFS] [CHARACTER MODEL] [WEAPON MATH] [WIZARD FLOW] [STEP UI] [EXPORT/IMPORT]
// Roadmap slots (planned, NOT implemented yet — keep these homes stable):
//  - Identity/archetype, movement.wander_strength, display_name/description  -> IMPLEMENTED (Setup step; JSON v2)
//  - stats {max_hp, chase_speed, follow_speed, scale}                        -> IMPLEMENTED (Setup step; JSON v2)
//  - handedness                                                              -> [CHARACTER MODEL] + Setup step UI
//  - per-attack projectile spec, cadence, fire_cycle, melee params           -> per-action step UI (act:* steps)
//  - ultimate {trigger_hp_pct,...}, defense_params, impact_params, survival  -> dedicated wizard steps after actions
//  - extra action slots (death, victory, spawn, dash, knockback, teleport)   -> ACT_DEFS optional entries
//  - sfx, trail component, palette.stops                                     -> Setup/action step UI + export
// ---- [STATE] ----
const appMode='char';let CH=null,curStep='setup',weaponEdit=false,dragWP=-1;
// ---- [ACTION DEFS] ---- (roadmap: optional slots death/victory/spawn/dash/knockback/teleport append here)
const ACT_DEFS=[
 ['idle','Idle','ambient',0],['run','Running','ambient',0],
 ['attack_normal','Normal Attack','on_hit',1],['attack_special','Special Attack','on_hit',1],
 ['ultimate','Ultimate','on_ult',1],['defend','Block / Dodge','on_parry',0],
 ['special_ability','Special Ability','ambient',0],['impact','Impact (got hit)','on_hit',0]];
const SAB_PRESETS=['none','shield','heal','clone','time_slow','rage','teleport','dual_defense'];
// ---- [ACTIVATION TRIGGERS] ---- multi-select trigger conditions for attack_special/ultimate/special_ability.
// Any enabled trigger fires the action (OR logic). hp_threshold fires once per crossing unless "repeatable" is
// set, in which case it can refire on its own cooldown_ms. after_on_impact/after_on_hit counters reset to 0 the
// moment they fire. radius_proximity is a min/max distance band. retrigger_cooldown_ms is a shared minimum gap
// between activations regardless of which trigger fired. Identical in Solo & Battle.
const TRIGGER_TYPES=[['hp_threshold','HP threshold'],['on_impact','On impact (being hit)'],
 ['after_on_impact','After On_Impact ×N'],['after_on_hit','After On_hit ×N'],['radius_proximity','Radius proximity']];
function ensureTriggers(a){if(!a.activation_triggers)a.activation_triggers=[];if(a.retrigger_cooldown_ms===undefined)a.retrigger_cooldown_ms=0;return a.activation_triggers}
function trigDefault(type){if(type==='hp_threshold')return{type,pct:50,repeatable:false,cooldown_ms:4000};
 if(type==='after_on_impact')return{type,count:3};if(type==='after_on_hit')return{type,count:5};
 if(type==='radius_proximity')return{type,min:0,max:150};return{type}}
function trigToggle(ak,type,on){const a=CH.actions[ak],arr=ensureTriggers(a),i=arr.findIndex(t=>t.type===type);
 if(on&&i<0)arr.push(trigDefault(type));else if(!on&&i>=0)arr.splice(i,1);renderStepUI()}
function trigSet(ak,type,k,v){const t=ensureTriggers(CH.actions[ak]).find(x=>x.type===type);if(!t)return;
 t[k]=(k==='repeatable')?!!v:+v}
function trigCooldownSet(ak,v){CH.actions[ak].retrigger_cooldown_ms=Math.max(0,+v)}
function activationTriggersHtml(ak){const a=CH.actions[ak],arr=ensureTriggers(a),has=type=>arr.find(t=>t.type===type);
 let h=`<h3 style="padding-left:0">Activation Triggers</h3>
 <small style="color:#7a8599;display:block;padding:2px 0 4px">Pick any combination — this action fires the moment ANY enabled condition below is true (OR logic). Identical in Solo &amp; Battle.</small>`;
 TRIGGER_TYPES.forEach(([type,label])=>{const t=has(type);
  h+=`<div class="row"><label><input type="checkbox" ${t?'checked':''} onchange="trigToggle('${ak}','${type}',this.checked)"> ${label}</label><div class="v">`;
  if(t){
   if(type==='hp_threshold')h+=`HP ≤ <input type="number" min="1" max="99" style="width:56px" value="${t.pct}" onchange="trigSet('${ak}','hp_threshold','pct',this.value)">%`+
    `<label style="margin-left:8px;font-size:11px"><input type="checkbox" ${t.repeatable?'checked':''} onchange="trigSet('${ak}','hp_threshold','repeatable',this.checked);renderStepUI()"> repeatable</label>`+
    (t.repeatable?` cooldown <input type="number" min="0" step="100" style="width:70px" value="${t.cooldown_ms}" onchange="trigSet('${ak}','hp_threshold','cooldown_ms',this.value)">ms`:' <small style="color:#7a8599">fires once per crossing</small>');
   else if(type==='after_on_impact'||type==='after_on_hit')h+=`every <input type="number" min="1" max="50" style="width:56px" value="${t.count}" onchange="trigSet('${ak}','${type}','count',this.value)"> hits <small style="color:#7a8599">(counter resets to 0 after firing)</small>`;
   else if(type==='radius_proximity')h+=`between <input type="number" min="0" style="width:64px" value="${t.min}" onchange="trigSet('${ak}','radius_proximity','min',this.value)"> and <input type="number" min="0" style="width:64px" value="${t.max}" onchange="trigSet('${ak}','radius_proximity','max',this.value)"> px of enemy`;
   else if(type==='on_impact')h+=`<small style="color:#7a8599">fires whenever the character takes a hit</small>`;
  }
  h+=`</div></div>`});
 h+=chRow('Retrigger cooldown ms',`<input type="number" min="0" step="50" value="${a.retrigger_cooldown_ms||0}" onchange="trigCooldownSet('${ak}',this.value)">`)+
  `<small style="color:#7a8599;display:block;padding:2px 0 8px">Minimum time between activations, regardless of which trigger fired (0 = no extra cooldown beyond a trigger's own).</small>`;
 return h}
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
// ---- [CHARACTER MODEL] ----
// _extra: forward-compat passthrough — unknown top-level keys from imported pb_character JSON
// (e.g. future archetype/stats/movement blocks) are preserved and re-emitted on export so this
// tool never strips roadmap fields it doesn't edit yet.
const ARCH_PRED={shooter:{can_shoot:true,uses_melee:false,retreats:true,charges_full:false},
 melee:{can_shoot:false,uses_melee:true,retreats:false,charges_full:true}};
const PRED_KEYS=['can_shoot','uses_melee','retreats','charges_full'];
function archSet(v){CH.archetype=v;if(ARCH_PRED[v])CH.predicates={...ARCH_PRED[v]};renderStepUI()}
function predSet(k,on){CH.predicates[k]=!!on}
function wanderSet(v){CH.movement.wander_strength=Math.max(0,Math.min(1,+v));
 const s=$('wsl'),e=$('wsv');if(s)s.value=CH.movement.wander_strength;if(e)e.textContent=CH.movement.wander_strength.toFixed(2)}
function statSet(k,v){const lims={max_hp:[50,200],chase_speed:[1,8],follow_speed:[1,8],scale:[0.5,2],basic_attack_radius:[20,600]};
 const [lo,hi]=lims[k]||[-Infinity,Infinity];CH.stats[k]=Math.max(lo,Math.min(hi,+v));
 const e=$('stv_'+k);if(e)e.textContent=CH.stats[k].toFixed(k==='max_hp'||k==='basic_attack_radius'?0:2)}
function newChar(){return{_extra:{},name:'new_fighter',display_name:'New Fighter',description:'',
 archetype:'melee',predicates:{...ARCH_PRED.melee},movement:{wander_strength:0.15},
 stats:{max_hp:100,chase_speed:3.0,follow_speed:4.5,scale:1.0,basic_attack_radius:180},
 palette:{body:'#8fa0b8',accent:'#ff5050'},defense:'block',
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
  keyframes:kf,fx_layers:[],activation_triggers:[],retrigger_cooldown_ms:0}}
// ---- [WEAPON MATH] --- custom weapon math (points are in weapon-local frame, origin=r_hand, +x along weapon angle) ---
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
// ---- [WIZARD FLOW] ----
function curActionKey(){return curStep&&curStep.startsWith('act:')?curStep.slice(4):null}
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
 const as=$('act');as.innerHTML='';const _o=document.createElement('option');_o.textContent=ak;as.appendChild(_o);as.value=ak;
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
// ---- [STEP UI] ----
function renderStepUI(){const d=$('stepui');let h='';
 if(curStep==='setup'){h=`<h3 style="padding-left:0">Character Setup</h3>`+
  chRow('Name',`<input type="text" value="${CH.name}" onchange="chSet('name',this.value)">`)+
  chRow('Display name',`<input type="text" value="${CH.display_name}" onchange="chSet('display_name',this.value)">`)+
  chRow('Description',`<input type="text" value="${CH.description}" onchange="chSet('description',this.value)">`)+
  chRow('Archetype',`<select onchange="archSet(this.value)">${['shooter','melee','New'].map(a=>`<option value="${a}" ${CH.archetype===a?'selected':''}>${a}</option>`).join('')}</select>`)+
  chRow('Predicates',PRED_KEYS.map(k=>`<label style="margin-right:6px;font-size:11px"><input type="checkbox" ${CH.predicates[k]?'checked':''} ${CH.archetype==='New'?'':'disabled'} onchange="predSet('${k}',this.checked)">${k}</label>`).join(''))+
  chRow('Wander',`<input type="range" id="wsl" min="0" max="1" step="0.01" value="${CH.movement.wander_strength}" oninput="wanderSet(this.value)"><span class="val" id="wsv">${CH.movement.wander_strength.toFixed(2)}</span><button onclick="wanderSet(0.15)">Swordsman</button><button onclick="wanderSet(1)">Runner</button>`)+
  `<small style="color:#7a8599;display:block;padding:4px 0">Archetype maps directly to game predicates; pick <b>New</b> to mix them freely. Wander caps lateral drift in battle chase (0.15 = charge straight, 1.0 = full weave) — identical in Solo & Battle.</small>`+
  chRow('Max HP',`<input type="range" min="50" max="200" step="5" value="${CH.stats.max_hp}" oninput="statSet('max_hp',this.value)"><span class="val" id="stv_max_hp">${CH.stats.max_hp}</span>`)+
  chRow('Chase speed',`<input type="range" min="1" max="8" step="0.1" value="${CH.stats.chase_speed}" oninput="statSet('chase_speed',this.value)"><span class="val" id="stv_chase_speed">${CH.stats.chase_speed.toFixed(2)}</span>`)+
  chRow('Follow speed',`<input type="range" min="1" max="8" step="0.1" value="${CH.stats.follow_speed}" oninput="statSet('follow_speed',this.value)"><span class="val" id="stv_follow_speed">${CH.stats.follow_speed.toFixed(2)}</span>`)+
  chRow('Scale',`<input type="range" min="0.5" max="2" step="0.05" value="${CH.stats.scale}" oninput="statSet('scale',this.value)"><span class="val" id="stv_scale">${CH.stats.scale.toFixed(2)}</span>`)+
  chRow('Basic attack radius',`<input type="range" min="20" max="600" step="5" value="${CH.stats.basic_attack_radius}" oninput="statSet('basic_attack_radius',this.value)"><span class="val" id="stv_basic_attack_radius">${CH.stats.basic_attack_radius.toFixed(0)}</span>`)+
  `<small style="color:#7a8599;display:block;padding:4px 0">Core stats feed MODE_CONFIGS at load — HP and speeds tune combat directly, Scale resizes the whole rig (hurtbox is derived automatically, not editable here). Basic attack radius is the distance from the enemy at which this character's Normal Attack is allowed to fire — per-character, so a swordsman and mage can have different reach. Identical in Solo & Battle.</small>`+
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
 else if(curStep==='act:special_ability'){const sa=CH.special_ability;ensureAction('special_ability');
  h=`<h3 style="padding-left:0">${CH.name} — Special Ability</h3>`+
  chRow('Preset base',`<select onchange="sabSet('preset',this.value)">${SAB_PRESETS.map(p=>`<option ${p===sa.preset?'selected':''}>${p}</option>`).join('')}</select>`)+
  chRow('Duration ms',`<input type="number" value="${sa.params.duration_ms}" onchange="sabSet('duration_ms',this.value)">`)+
  chRow('Cooldown ms',`<input type="number" value="${sa.params.cooldown_ms}" onchange="sabSet('cooldown_ms',this.value)">`)+
  chRow('Magnitude',`<input type="number" value="${sa.params.magnitude}" onchange="sabSet('magnitude',this.value)">`)+
  `<small style="color:#7a8599;display:block;padding:4px 0">Preset defines the mechanic; add custom FX layers below for its visuals. <b>dual_defense</b> adds a second defense animation step.</small>`+
  activationTriggersHtml('special_ability')}
 else if(curStep==='act:attack_special'||curStep==='act:ultimate'){const ak=curStep.slice(4),def=ACT_DEFS.find(a=>a[0]===ak);ensureAction(ak);
  h=`<h3 style="padding-left:0">${CH.name} — ${def[1]}</h3>
  <small style="color:#7a8599;display:block;padding:4px 0">Sculpt the animation with Pose Mode + keyframes, add FX layers on the left. Trigger/duration in the top bar are saved per action.</small>
  <small style="color:#7a8599;display:block;padding:4px 0"><b>Battle Properties</b> live on each FX layer: tick <b>Can hit target</b> on a layer to set its Damage, Attack effects (Explode / Scatter / Pierce / Slash — stackable, visual only) and Defence (Deflect / Block — mutually exclusive).</small>`+
  activationTriggersHtml(ak)}
 else if(curStep.startsWith('act:')){const ak=curStep.slice(4),def=ACT_DEFS.find(a=>a[0]===ak);
  h=`<h3 style="padding-left:0">${CH.name} — ${def?def[1]:ak==='defend2'?'Second Defense':ak}</h3>
  <small style="color:#7a8599;display:block;padding:4px 0">Sculpt the animation with Pose Mode + keyframes, add FX layers on the left. Trigger/duration in the top bar are saved per action.</small>
  <small style="color:#7a8599;display:block;padding:4px 0"><b>Battle Properties</b> live on each FX layer: tick <b>Can hit target</b> on a layer to set its Damage, Attack effects (Explode / Scatter / Pierce / Slash — stackable, visual only) and Defence (Deflect / Block — mutually exclusive).</small>`}
 else if(curStep==='review'){const done=Object.keys(CH.actions).length,need=wizSteps().filter(s=>s.k.startsWith('act:')).length;
  h=`<h3 style="padding-left:0">${CH.name} — Review & Export</h3>
  <div class="row"><label>Name</label><div class="v"><b>${CH.name}</b></div></div>
  <div class="row"><label>Archetype</label><div class="v">${CH.archetype}${CH.archetype==='New'?' ('+PRED_KEYS.filter(k=>CH.predicates[k]).join(', ')+')':''} — wander ${CH.movement.wander_strength.toFixed(2)}</div></div>
  <div class="row"><label>Defense</label><div class="v">${CH.defense}${CH.special_ability.preset==='dual_defense'?' + both (dual)':''}</div></div>
  <div class="row"><label>Weapon pts</label><div class="v">${CH.weapon.points.length}</div></div>
  <div class="row"><label>Ability</label><div class="v">${CH.special_ability.preset}</div></div>
  <div class="row"><label>Actions</label><div class="v">${done}/${need} created</div></div>
  <button class="pri" style="width:100%;margin-top:8px" onclick="openJson(1)">Export Character JSON</button>
  <small style="color:#7a8599;display:block;padding:4px 0">Give this JSON to Claude to implement in Solo & Battle modes.</small>`}
 d.innerHTML=h}
function wizNext(){const s=wizSteps(),i=s.findIndex(x=>x.k===curStep);if(i<s.length-1)gotoStep(s[i+1].k)}
function wizPrev(){const s=wizSteps(),i=s.findIndex(x=>x.k===curStep);if(i>0)gotoStep(s[i-1].k)}
function bootWizard(){if(!CH)CH=newChar();$('fig').value='custom';curStep='setup';gotoStep('setup')}
// ---- [EXPORT/IMPORT] ---- pb_character (full fighter). pb_fx (single action FX) is in fx_engine.js.
const ACTIVATION_TRIGGER_SEMANTICS={
 attach:'activation_triggers + retrigger_cooldown_ms live per action (currently authored for attack_special, ultimate, special_ability).',
 logic:'Any combination of trigger types may be enabled at once; the action fires the moment ANY one of them is true (OR logic).',
 hp_threshold:'Fires when HP first drops to/at or below pct. If repeatable=false (default) it fires once per crossing, like the existing hardcoded swordsman/runner ultimates. If repeatable=true it can refire any time HP is at/below pct again, gated by its own cooldown_ms.',
 on_impact:'Fires every time the character takes a hit (subject to the action-level retrigger_cooldown_ms).',
 after_on_impact:'Fires once the character has been hit `count` times since this counter last fired; the counter resets to 0 immediately after firing.',
 after_on_hit:'Fires once the character has landed `count` hits on the enemy since this counter last fired; the counter resets to 0 immediately after firing.',
 radius_proximity:'Fires while the distance to the enemy is between min and max px (a band, not a single threshold).',
 retrigger_cooldown_ms:'Shared minimum time between activations of this action, regardless of which trigger condition fired it. 0 = no extra gating beyond a trigger\'s own rules.',
 parity:'Behaviour is identical in Solo & Battle modes.'};
function buildCharJson(){saveStep();const acts={};for(const k in CH.actions){const a=CH.actions[k];
 (a.fx_layers||[]).forEach(l=>{if(l.can_hit)ensureBattle(l)});
 acts[k]={trigger:a.trigger,duration_ms:a.duration_ms,keyframes:a.keyframes,fx_layers:a.fx_layers,
  activation_triggers:a.activation_triggers||[],retrigger_cooldown_ms:a.retrigger_cooldown_ms||0}}
 return JSON.stringify({...(CH._extra||{}),format:'pb_character',version:2,name:CH.name,display_name:CH.display_name,description:CH.description,archetype:CH.archetype,predicates:{...CH.predicates},movement:{wander_strength:CH.movement.wander_strength},stats:{...CH.stats},rig:'humanoid_v2',modes:['solo','battle'],
  bones:CH.bones,
  palette:CH.palette,defense:CH.defense,dual_defense:CH.special_ability.preset==='dual_defense',
  weapon:{points:CH.weapon.points,thickness:CH.weapon.thickness,color:CH.weapon.color,anchors:['weapon_mid','weapon_tip']},
  special_ability:CH.special_ability,actions:acts,target_dummy:dummyExport(),battle_semantics:BATTLE_SEMANTICS,fx_semantics:FX_SEMANTICS,activation_trigger_semantics:ACTIVATION_TRIGGER_SEMANTICS},null,1)}
const CH_KNOWN=['format','version','name','display_name','description','archetype','predicates','movement','stats','rig','modes','bones','palette','defense','dual_defense','weapon','special_ability','actions','target_dummy','battle_semantics','fx_semantics','activation_trigger_semantics'];
function importChar(o){CH=newChar();CH.name=o.name||CH.name;if(o.palette)CH.palette=o.palette;if(o.bones)CH.bones=o.bones;
 CH.display_name=o.display_name||CH.name;CH.description=o.description||'';
 CH.archetype=o.archetype||((o.weapon&&o.weapon.points&&o.weapon.points.length)?'melee':'shooter');
 CH.predicates=o.predicates?PRED_KEYS.reduce((m,k)=>(m[k]=!!o.predicates[k],m),{}):{...(ARCH_PRED[CH.archetype]||ARCH_PRED.melee)};
 if(o.movement&&isFinite(+o.movement.wander_strength))CH.movement.wander_strength=Math.max(0,Math.min(1,+o.movement.wander_strength));
 if(o.stats){const lims={max_hp:[50,200],chase_speed:[1,8],follow_speed:[1,8],scale:[0.5,2],basic_attack_radius:[20,600]};
  for(const k in CH.stats){if(o.stats[k]!=null&&isFinite(+o.stats[k])){const[lo,hi]=lims[k];CH.stats[k]=Math.max(lo,Math.min(hi,+o.stats[k]))}}}
 for(const k in o){if(!CH_KNOWN.includes(k))CH._extra[k]=o[k]}
 if(o.defense)CH.defense=o.defense;if(o.weapon)CH.weapon={points:o.weapon.points||[],thickness:o.weapon.thickness||3,color:o.weapon.color||'#d8dee9'};
 if(o.special_ability)CH.special_ability=o.special_ability;
 CH.actions={};for(const k in (o.actions||{})){const a=o.actions[k];fixKF(a.keyframes||[]);
  CH.actions[k]={trigger:a.trigger||'ambient',duration_ms:a.duration_ms||800,keyframes:a.keyframes||DEF_KF.idle(),
   fx_layers:(a.fx_layers||[]).map(l=>{if(l.can_hit)ensureBattle(l);return l}),
   activation_triggers:a.activation_triggers||[],retrigger_cooldown_ms:a.retrigger_cooldown_ms||0}}
 dummyImport(o.target_dummy);
 curStep='setup';gotoStep('setup')}

