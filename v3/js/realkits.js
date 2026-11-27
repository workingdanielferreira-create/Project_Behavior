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
    mcd:+cfg(a).cooldown_ms||0,move3d:cfg(a).move3d&&cfg(a).move3d.enabled?cfg(a).move3d:null,tdist:trigDist(cfg(a).trigger_dist)},extra||{});   // move3d: FX Studio 3D movement (fxlive.js); tdist: trigger distance (combat.js inTrigDist)
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
  for(const a of acts){if(normals.includes(a)||['attack_special','attack_special_2','ultimate','defend','switch_in'].includes(a)||!COND3D.triggerable(a))continue;
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
// FX Studio 3D trigger distance (Daniel 2026-11-26): action_settings[a].trigger_dist {enabled, min_m, max_m (0 = no limit)}
function trigDist(t){if(!t||!t.enabled)return null;const mn=Math.max(0,+t.min_m||0),mx=Math.max(0,+t.max_m||0);return mn||mx?{min:mn,max:mx}:null;}
function addTrigger(k,slot,d,c){if(d)k[slot]=d;k.triggers.push({slot,logic:c.logic==='all'?'all':'any',cd:+c.cooldown_ms||0,conds:(c.conditions||[]).map(x=>Object.assign({},x))});}

/* FX Studio trigger conditions + V3's own 3D ones (js/conds3d.js COND3D.TYPES, Daniel 2026-11-27: every type works in V3)
   read against the V3 sim. FX Studio's distances / speeds are 2D game px (x PX2D = V3 px); the "3D (V3 only)" types are
   metres (x 1/K). name = the action this trigger starts (its 2D name). Unknown types are never true. */
const cnum=(v,d)=>{const n=+v;return isFinite(n)&&v!==''&&v!=null?n:d;};
function seg3(P,A,B){const ab=B.clone().sub(A),l2=ab.lengthSq();if(l2<1e-9)return P.distanceTo(A);const u=clamp(P.clone().sub(A).dot(ab)/l2,0,1);return P.distanceTo(A.clone().addScaledVector(ab,u));}
const bodyC=f=>VA(f.x,f.y,f.z,.9+(f.h||0));
// enemy threats near point P (metres, world): damaging FX of every foe of `side` (fxlive.js fxWorld) + their shots.
// tags: COND3D.tags list ([] = any). Returns the nearest distance (m) to a matching one, Infinity if none.
function threatDist(side,P,want){let best=Infinity;const T=COND3D.tagMatch;
  for(const o of foesOf(side)){if(!o||o.ko)continue;for(const x of fxWorld(o)){if(!(x.dmg>0))continue;const fx=x.inst.fx||{};
    if(want.length&&!T(want,fx.tag)&&!T(want,fx.prim))continue;const dd=(x.T?seg3(P,x.T,x.H):P.distanceTo(x.H))-(x.r||0)-(x.rEnd||0);if(dd<best)best=dd;}}
  if(!want.length||T(want,'bullet'))for(const s of shots){if(s.side===side)continue;const dd=P.distanceTo(VA(s.x,s.y,s.z||0,1.1));if(dd<best)best=dd;}
  return Math.max(0,best);}
// own hop blades (FX Studio Blade hop beacons) with their world spot
function hopBlades(f){if(!window.FXK||!FXK.hopIsBeacon)return [];return fxWorld(f).filter(x=>FXK.hopIsBeacon(x.inst)).map(x=>{const i=x.inst;
  const field=!!(i.lodge&&i.lodge.g)||!!i.hopStopped||(!i.hopL&&Math.hypot(i.vx||0,i.vy||0)<1);return {H:x.H,field};});}
/* "just happened" events (hit_by_fx, bullet_deflected): the fighter is usually still busy (parry, hit stun) on the tick it
   happens, so the event holds for JUST_MS and is used up by the first action it starts (combat.js realTriggers -> justUse). */
const JUST_MS=500,JUST_TYPES=['hit_by_fx','bullet_deflected'];
const justUsed=(f,t)=>(f.justU&&f.justU[t]!=null)?f.justU[t]:-1e9;
function justUse(f,conds){for(const c of conds)if(JUST_TYPES.includes(c.type)&&!c.not)(f.justU||(f.justU={}))[c.type]=tick;}
const teamOf=f=>sides[f.side].team.filter(m=>m&&m!==f&&!m.ko&&!m.phantom);
const standing=s=>sides[s].team.filter(m=>m&&!m.ko&&!m.phantom).length;
function realCond(f,e,c,trig,name){const d=Math.hypot(f.x-e.x,f.y-e.y),now=tick,P=PX2D,neg=!!c.not;let v=false;
  switch(c.type){
  // own state
  case'hp_below':v=f.hp/f.max*100<=cnum(c.pct,50)&&(c.repeat||!f.thr[name+':'+cnum(c.pct,50)]);break;   // marked on fire (combat.js realTriggers)
  case'hp_above':v=f.hp/f.max*100>=cnum(c.pct,80);break;
  case'self_speed_above':v=(f.spd||0)>=cnum(c.px_s,120)*P;break;
  case'self_speed_below':v=(f.spd||0)<=cnum(c.px_s,20)*P;break;
  // target
  case'target_within':v=d<=cnum(c.px,80)*P;break;
  case'target_beyond':v=d>=cnum(c.px,200)*P;break;
  case'target_between':{const a=cnum(c.min_px,60)*P,b=cnum(c.max_px,200)*P;v=d>=Math.min(a,b)&&d<=Math.max(a,b);break;}
  case'target_above':v=e.z-f.z>=cnum(c.px,40)*P;break;
  case'target_below':v=f.z-e.z>=cnum(c.px,40)*P;break;
  case'target_facing':{const to=Math.atan2(f.y-e.y,f.x-e.x);const tw=Math.cos(e.face-to)>0;v=c.dir==='away'?!tw:tw;break;}
  case'target_attacking':v=!!(e.act&&e.act.kind!=='react');break;
  case'target_defending':v=!!(e.block>0||e.parry>0||parryWindow(e));break;
  case'target_hp_below':v=e.hp/e.max*100<=cnum(c.pct,50);break;
  case'target_hp_above':v=e.hp/e.max*100>=cnum(c.pct,80);break;
  case'target_speed_above':v=(e.spd||0)>=cnum(c.px_s,120)*P;break;
  case'target_speed_below':v=(e.spd||0)<=cnum(c.px_s,20)*P;break;
  // hits & projectiles
  case'attacks_made':v=(f.nStarts||0)-(trig.starts0==null?(trig.starts0=f.nStarts||0):trig.starts0)>=cnum(c.count,3);break;
  case'hits_taken':v=f.hurts.filter(h=>h>(trig.fired||0)).length>=cnum(c.count,3);break;
  case'damage_taken':{const from=now-ms2t(cnum(c.ms,2000));v=f.dmgLog.filter(x=>x[0]>from).reduce((a,x)=>a+x[1],0)>=cnum(c.hp,10);break;}
  case'landed_hit':v=now-f.lastLanded<=1;break;
  case'hit_by_fx':{const want=COND3D.tags(c.tags),u=justUsed(f,'hit_by_fx');v=(f.hitTags||[]).some(h=>h[0]>u&&now-h[0]<=ms2t(JUST_MS)&&COND3D.tagMatch(want,h[1]));break;}
  case'fx_near':v=threatDist(f.side,bodyC(f),COND3D.tags(c.tags))<=cnum(c.px,60)*P*K;break;
  case'projectile_count':{let n=shots.filter(s=>s.side!==f.side).length;for(const o of foesOf(f.side))if(o&&!o.ko)n+=fxWorld(o).filter(x=>x.moving&&x.dmg>0).length;v=n>=cnum(c.count,5);break;}
  case'bullet_deflected':{const t=f.deflT==null?-1e9:f.deflT;v=t>justUsed(f,'bullet_deflected')&&now-t<=ms2t(JUST_MS);break;}
  // timing & order
  case'after_actions':{const seq=String(c.sequence||'').split(',').map(s=>s.trim()).filter(Boolean),h=f.hist||[];v=seq.length>0&&h.length>=seq.length&&seq.every((s,i)=>h[h.length-seq.length+i]===s);break;}
  case'since_action':{const o=String(c.action||'')||name;const playing=f.act&&f.act.def&&f.act.def.n2d===o;const at=(f.endAt||{})[o];v=!playing&&(at==null||now-at>=ms2t(cnum(c.ms,2000)));break;}
  case'every_ms':v=now-(trig.last||0)>=ms2t(cnum(c.ms,3000));break;
  case'idle_for':v=!f.act&&now-f.lastEnd>=ms2t(cnum(c.ms,1000));break;
  case'chance':v=Math.random()<1-Math.pow(1-clamp(cnum(c.pct_s,30),0,100)/100,DT);break;
  // actions
  case'action_triggered':{const who=c.who==='self'||c.who==='own'?f:e;v=!!who.lastAct2d&&(!c.action||who.lastAct2d===c.action)&&now-who.lastActTick<=ms2t(cnum(c.ms,300))+1;break;}
  // blade hop
  case'hop_blades':{const w=c.which||'field';v=hopBlades(f).filter(b=>w==='any'||(w==='field')===b.field).length>=cnum(c.count,1);break;}
  case'hop_blade_near':{const C=bodyC(f),r=cnum(c.px,60)*P*K;v=hopBlades(f).some(b=>b.H.distanceTo(C)<=r);break;}
  // fight rhythm & team
  case'tempo_intent':v=f.tp.intent===(c.intent||'engage');break;
  case'director_phase':v=director.phase===(c.phase||'burst');break;
  case'director_above':v=director.I*100>=cnum(c.pct,60);break;
  case'has_token':v=true;break;   // one fighter per side: the attacker always holds it
  case'target_open':v=isOpen(e)>0;break;
  case'partner_intent':v=teamOf(f).some(m=>m.on&&m.tp.intent===(c.intent||'pressure'));break;
  case'partner_within':v=teamOf(f).some(m=>m.on&&Math.hypot(m.x-f.x,m.y-f.y)<=cnum(c.px,200)*P);break;
  case'partner_hp_below':v=teamOf(f).some(m=>m.hp/m.max*100<=cnum(c.pct,40));break;
  case'outnumbered':v=standing(f.side)<standing(1-f.side);break;
  // ally support: a fielded team-mate (at most max_px from this fighter, 0 = any) with a threat within px
  case'ally_threatened':{const r=cnum(c.px,120)*P*K,mx=cnum(c.max_px,600)*P,by=c.by||'fx_or_enemy';
    v=teamOf(f).some(m=>{if(!m.on||(mx>0&&Math.hypot(m.x-f.x,m.y-f.y)>mx))return false;const C=bodyC(m);
      const fx=()=>threatDist(f.side,C,[])<=r,en=()=>foesOf(f.side).some(o=>o&&!o.ko&&bodyC(o).distanceTo(C)<=r),al=()=>teamOf(f).some(o=>o!==m&&o.on&&bodyC(o).distanceTo(C)<=r);
      return by==='fx'?fx():by==='enemy'?en():by==='ally'?al():by==='any'?fx()||en()||al():fx()||en();});break;}
  // 3D (V3 only), metres
  case'self_airborne':v=f.z*K>=cnum(c.m,.5);break;
  case'target_airborne':v=e.z*K>=cnum(c.m,.5);break;
  case'target_vertical':{const vz=(e.vz||0)*K,m=cnum(c.m_s,2);v=e.z*K>.1&&(c.dir==='rising'?vz>=m:-vz>=m);break;}
  case'height_gap':{const g=(e.z-f.z)*K,a=cnum(c.min_m,-1),b=cnum(c.max_m,1);v=g>=Math.min(a,b)&&g<=Math.max(a,b);break;}
  case'target_dist_3d':{const g=Math.hypot(f.x-e.x,f.y-e.y,f.z-e.z)*K,mx=cnum(c.max_m,4);v=g>=cnum(c.min_m,0)&&(!mx||g<=mx);break;}
  case'self_sprinting':v=(f.spdLv||1)>=cnum(c.level,2);break;
  case'self_flying':v=canFly(f);break;
  case'target_knocked_back':v=e.stun>0&&Math.hypot(e.vx,e.vy,e.vz||0)*K>=cnum(c.m_s,5);break;
  case'target_juggled':v=comboJuggled(e)&&(e.cmbN||0)>=cnum(c.count,1);break;
  case'target_behind_me':{const to=Math.atan2(e.y-f.y,e.x-f.x);v=Math.abs(((to-f.face+Math.PI)%TAU+TAU)%TAU-Math.PI)*180/Math.PI>=cnum(c.deg,90);break;}
  case'target_stunned':v=e.stun>0&&(!c.kind||c.kind==='any'||e.stunKind===c.kind);break;
  case'locked_on':v=typeof lockOn!=='undefined'&&lockOn&&lockT===e&&lockPlayer()===f;break;
  case'self_parry_window':{const w=parryWindow(f);v=!!w&&(!c.grade||c.grade==='any'||w===c.grade);break;}
  case'counter_ready':v=!!(f.pw&&f.pw.counterOn===e&&tick<=f.pw.counterUntil);break;}
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
