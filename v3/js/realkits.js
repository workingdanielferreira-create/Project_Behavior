'use strict';
/* Real character kits: turns window.PB3_KITS (built from characters/ by tools/build_kits.py, see run_v3.bat) into
   V3 kits, replacing the hand-made stand-ins. Only the glue the V3 sim needs is derived here; the FX themselves,
   their damage, knockback and timing are played by FX Studio's own runtime, laid in 3D (fx3d.js / fxlive.js).
   2D sizes: the 2D game's fighters stand 28 px; a V3 body is BODY (88) px, so 2D distances x PX2D. */
const PX2D=BODY/28;
const REAL_KITS=window.PB3_KITS||{};
const SKIP_ACTIONS={idle:1,run:1,switch_out:1,transform:1};
function hexInt(h,d){h=String(h||'').replace('#','');if(h.length===3)h=h.split('').map(c=>c+c).join('');const v=parseInt(h,16);return h.length===6&&isFinite(v)?v:d;}
function lighten(c,k){const r=(c>>16)&255,g=(c>>8)&255,b=c&255;const f=x=>Math.round(x+(255-x)*k);return (f(r)<<16)|(f(g)<<8)|f(b);}
// A colour bright enough to read as FX / HP bar on the dark arena.
function vivid(c){const r=(c>>16)&255,g=(c>>8)&255,b=c&255;return Math.max(r,g,b)<120?lighten(c,.55):c;}
function shortName(n){const w=String(n).replace(/[^A-Za-z0-9 ]/g,' ').trim().split(/\s+/);return (w.length>1?w[0][0]+w[1][0]:w[0].slice(0,2)).toUpperCase();}

function realKit(R){
  const F=R.fxkit||{},T=F.timing||{},AS=F.action_settings||{},st=R.stats||{},pal=R.palette||{},pr=R.predicates||{};
  const body=hexInt(pal.body,0x8a8fb0),acc=hexInt(pal.accent,0x8fd3ff);
  const eff=(F.effects||[]).filter(e=>e.enabled!==false);
  const fxCol=(()=>{const e=eff.find(x=>x.color&&x.color.c2)||eff.find(x=>x.color&&x.color.c1);return e?hexInt(e.color.c2||e.color.c1,acc):acc;})();
  const dur=a=>Math.max(120,Math.round((T[a].frames||1)*(T[a].frame_ms||16)));
  const cfg=a=>AS[a]||{};
  const def=(a,extra)=>Object.assign({n2d:a,name:a.replace(/_/g,' '),dur:dur(a),hits:[],fx:[],fx2d:true,frames:T[a].frames||1,frameMs:T[a].frame_ms||16,
    mcd:+cfg(a).cooldown_ms||0,move3d:cfg(a).move3d&&cfg(a).move3d.enabled?cfg(a).move3d:null},extra||{});   // move3d: FX Studio 3D movement (fxlive.js)
  const melee=pr.uses_melee!==false;
  const reach=clamp((+st.basic_attack_radius||(melee?120:400))*(melee?1:PX2D*.5),70,melee?260:900);
  const acts=Object.keys(T).filter(a=>!SKIP_ACTIONS[a]);
  const k={key:R.key,name:String(R.display_name||R.name||R.key).toUpperCase(),short:shortName(R.display_name||R.key),real:true,fx2d:true,src:R,
    col:body,acc:acc,fx:vivid(fxCol),core:lighten(vivid(fxCol),.7),hp:+st.max_hp||2000,melee:melee,reach:reach,
    speed:clamp((+st.chase_speed||2.5)*95,160,560),blink:0,gate:false,
    t:{neutral:[350,1200],feint:20,string:[3,6],gap:[320,80],spacing:melee?40:200,reset:180},
    normals:[],triggers:[],flight:!!(F.flight&&F.flight.enabled),
    sprint:F.sprint?{lv3:!!F.sprint.lv3,lv2Pct:+F.sprint.lv2_pct||0,lv3Pct:+F.sprint.lv3_pct||0}:null};   // sprint levels (sprint.js; FX Studio 3D)   // can fly (gravity.js); set by the future FX Studio 3D
  // normals: attack_normal, _2, _3 ... in chain order (those with their own conditions become triggers)
  const normals=acts.filter(a=>/^attack_normal(_\d+)?$/.test(a)).sort((a,b)=>(+(a.split('_')[2]||1))-(+(b.split('_')[2]||1)));
  for(const a of normals){const c=cfg(a);const lunge=melee?[[0,Math.min(260,(+c.attack_px||120))]]:null;
    if((c.conditions||[]).length&&a!=='attack_normal')addTrigger(k,'x:'+a,def(a,{lunge}),c);else k.normals.push(def(a,{lunge}));}
  if(!k.normals.length)k.normals.push({name:'—',dur:400,hits:[],fx:[],none:true});
  // named slots the HUD / keys use
  const slot=(s,a)=>{if(T[a]){k[s]=def(a,{name:prettyName(F,a)});const c=cfg(a);if((c.conditions||[]).length)addTrigger(k,s,null,c);}};
  slot('special','attack_special');slot('special2','attack_special_2');slot('ult','ultimate');
  if(T.defend){k.defend=def('defend');const c=cfg('defend');if((c.conditions||[]).length)addTrigger(k,'defend',null,c);}
  if(T.switch_in)k.switchIn=def('switch_in');
  for(const s of['special','special2','ult'])if(!k[s])k[s]={name:'—',none:true,dur:1,hits:[],fx:[],mcd:1e9,cd:1e9};
  // any other action with conditions (attack_special_3, ultimate_2 ...) fires as a trigger
  for(const a of acts){if(normals.includes(a)||['attack_special','attack_special_2','ultimate','defend','switch_in'].includes(a))continue;
    const c=cfg(a);if((c.conditions||[]).length)addTrigger(k,'x:'+a,def(a,{name:prettyName(F,a)}),c);}
  // dodge (pack.dodge) -> V3's auto reaction
  const D=F.dodge;
  if(D&&D.enabled){const parry=D.style==='parry';k.react={kind:parry?'parry':'sidestep',p:clamp((+D.chance_pct||100)/100,0,1)*.6,cd:Math.max(300,+D.cooldown_ms||0),
      dist:(+D.distance_px||108)*1.0,trig:(+D.trigger_px||90)*1.5,shotsOnly:D.react_to!=='all'&&D.react_to!=='all_fx'};}
  else k.react={kind:melee?'sidestep':'dodge',p:.15,cd:1400};
  // movement style (pack.movement_style): orbit radius / chase speed of its first phases
  const MS=F.movement_style;
  if(MS&&MS.enabled&&MS.phases&&MS.phases.length){const orb=MS.phases.find(p=>p.pattern==='orbit'),ch=MS.phases.find(p=>p.pattern==='chase');
    k.style={orbit:orb?clamp((+((orb.params||{}).radius_px)||130)*PX2D*.5,90,600):null,orbitSpd:orb?clamp(((orb.modifiers||{}).speed_pct||100)/100,.5,3):1,
      chaseSpd:ch?clamp(((ch.modifiers||{}).speed_pct||100)/100,.5,3):1};}
  return k;}
function prettyName(F,a){// an action's FX name (first enabled damaging effect), else the action id
  const e=(F.effects||[]).find(x=>x.action===a&&x.enabled!==false&&(x.battle||{}).deals_damage&&x.name);
  const n=e?String(e.name).split(/[·:]/).pop().replace(/\s*(copy|\d+)(\s+(copy|\d+))*$/i,'').trim():'';
  const t=s=>s.replace(/\b\w/g,c=>c.toUpperCase());return t(n&&n.length<26?n:a.replace(/_/g,' '));}
function addTrigger(k,slot,d,c){if(d)k[slot]=d;k.triggers.push({slot,logic:c.logic==='all'?'all':'any',cd:+c.cooldown_ms||0,conds:(c.conditions||[]).map(x=>Object.assign({},x))});}

// FX Studio trigger conditions (actions.CONDITION_TYPES) read against the V3 sim. Unknown ones are never true.
function realCond(f,e,c,trig){const d=Math.hypot(f.x-e.x,f.y-e.y),now=tick;const neg=!!c.not;let v=false;
  switch(c.type){
  case'hp_below':v=f.hp/f.max*100<=(+c.pct||50)&&(c.repeat||!f.thr['h'+c.pct]);if(v&&!c.repeat)f.thr['h'+c.pct]=1;break;
  case'hp_above':v=f.hp/f.max*100>=(+c.pct||80);break;
  case'target_within':v=d<=(+c.px||80)*PX2D;break;
  case'target_beyond':v=d>=(+c.px||200)*PX2D;break;
  case'target_between':v=d>=(+c.min_px||0)*PX2D&&d<=(+c.max_px||200)*PX2D;break;
  case'target_attacking':v=!!(e.act&&e.act.kind!=='react');break;
  case'target_defending':v=!!(e.block>0||e.parry>0||parryWindow(e));break;
  case'target_hp_below':v=e.hp/e.max*100<=(+c.pct||50);break;
  case'target_hp_above':v=e.hp/e.max*100>=(+c.pct||80);break;
  case'every_ms':v=now-(trig.last||0)>=ms2t(+c.ms||3000);break;
  case'idle_for':v=!f.act&&now-f.lastEnd>=ms2t(+c.ms||1000);break;
  case'chance':v=Math.random()<(+c.pct_s||30)/100*DT;break;
  case'attacks_made':v=(stats.starts[f.side]-(trig.starts0==null?(trig.starts0=stats.starts[f.side]):trig.starts0))>=(+c.count||3);break;
  case'hits_taken':v=f.hurts.filter(h=>h>(trig.fired||0)).length>=(+c.count||3);break;
  case'damage_taken':{const from=now-ms2t(+c.ms||2000);v=f.dmgLog.filter(x=>x[0]>from).reduce((a,x)=>a+x[1],0)>=(+c.hp||10);break;}
  case'landed_hit':v=now-f.lastLanded<=1;break;
  case'projectile_count':v=shots.filter(s=>s.side!==f.side).length>=(+c.count||5);break;
  case'action_triggered':{const who=c.who==='self'||c.who==='own'?f:e;v=!!who.lastAct2d&&(!c.action||who.lastAct2d===c.action)&&now-who.lastActTick<=ms2t(+c.ms||300)+1;break;}
  case'since_action':v=now-f.lastEnd>=ms2t(+c.ms||2000);break;}
  return neg?!v:v;}

// Replace the stand-in roster with the real kits (keeps the stand-ins only if no kit file was built).
(function(){const keys=Object.keys(REAL_KITS);if(!keys.length){console.warn('PB3: no kits.gen.js - run run_v3.bat (builds it from characters/)');return;}
  for(const k in KITS)delete KITS[k];for(const k in NAMES)delete NAMES[k];for(const k in ROLES)delete ROLES[k];
  const used={};
  for(const key of keys){try{const k=realKit(REAL_KITS[key]);const nm=String(REAL_KITS[key].display_name||key).replace(/[^A-Za-z0-9]/g,'').toUpperCase();
    for(let j=1;used[k.short]&&j<nm.length;j++)k.short=nm[0]+nm[j];used[k.short]=1;KITS[key]=k;NAMES[key]=String(REAL_KITS[key].display_name||key);
    ROLES[key]=(k.melee?'Melee':'Ranged')+' · '+k.normals.length+' attack'+(k.normals.length>1?'s':'')+(k.ult.none?'':' · '+k.ult.name);}
    catch(err){console.error('PB3: kit '+key+' failed',err);}}
  const has=k=>!!KITS[k],pick=(want,i)=>want.filter(has).concat(keys).filter((v,j,a)=>a.indexOf(v)===j)[i];
  const DT0=[[0,1,2].map(i=>pick(['hooded_blades','sueko','puck'],i)),[0,1,2].map(i=>pick(['ronin_copy','tough','pewpew','sync'],i))];DEFAULT_SETTINGS.teams=DT0;
  settings.teams=[0,1].map(si=>[0,1,2].map(i=>{const t=settings.teams[si];return t&&KITS[t[i]]?t[i]:DT0[si][i];}));})();
// The enemy copy of a character on both teams: hue-shifted colours.
function altColours(k){const sh=c=>{const col=new THREE.Color(c);const h={};col.getHSL(h);col.setHSL((h.h+.45)%1,h.s,h.l);return col.getHex();};return {col:sh(k.col),fx:sh(k.fx),core:sh(k.core)};}
