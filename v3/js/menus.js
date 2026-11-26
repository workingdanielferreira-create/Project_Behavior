'use strict';
/* ================= menus =================
   The in-game screens that replace the old page text: title, teams,
   settings, controls, pause and results. One overlay (#menu), one screen at
   a time, a back stack (Esc = back; on the pause screen Esc resumes).
   Keyboard: Up / Down move between items, Left / Right change a value,
   Enter / Space press. Mouse works everywhere. */
const Menu=(function(){
  const root=$('menu');
  let cur=null,stack=[],result=null;

  const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const btn=(id,label,cls)=>'<button type="button" class="mb'+(cls?' '+cls:'')+'" data-nav data-act="'+id+'">'+label+'</button>';
  const KEYS=Object.keys(NAMES);
  const SLOT=['Lead','Tag 1','Tag 2'];

  /* ---------- screens ---------- */
  function title(){
    const t=settings.teams;const nm=a=>a.map(k=>esc(NAMES[k]||k)).join(' · ');
    return '<div class="scr title"><div class="brand"><span class="eyebrow">Project Behavior</span><h1>BEHAVIOR <em>3D</em></h1><span class="ver">V3 · foundation build</span></div>'+
      '<nav class="stack">'+btn('fight','Fight','primary')+btn('training','Training')+btn('teams','Teams')+btn('settings','Settings')+btn('controls','Controls')+btn('fullscreen',document.fullscreenElement?'Leave fullscreen':'Fullscreen')+'</nav>'+
      '<p class="foot"><b>'+nm(t[0])+'</b> <span>vs</span> <b>'+nm(t[1])+'</b><br><small>F11 fullscreen · Alt+F4 quit</small></p></div>';}

  function teams(){
    const side=(si,label)=>'<section class="team t'+si+'"><h2>'+label+'</h2>'+[0,1,2].map(i=>{const k=settings.teams[si][i];const kit=KITS[k];
      return '<div class="slot" data-nav data-cyc="team" data-side="'+si+'" data-i="'+i+'" tabindex="0"><span class="sl">'+SLOT[i]+'</span>'+
        '<button type="button" class="ar" data-step="-1" tabindex="-1" aria-label="Previous">◀</button>'+
        '<span class="who"><i style="background:'+cssc(kit.col)+';box-shadow:0 0 0 2px '+cssc(kit.fx)+'"></i><b>'+esc(NAMES[k])+'</b><small>'+esc(ROLES[k]||'')+' · '+kit.hp+' HP</small></span>'+
        '<button type="button" class="ar" data-step="1" tabindex="-1" aria-label="Next">▶</button></div>';}).join('')+'</section>';
    return '<div class="scr wide"><h1>Teams</h1><p class="sub">One fighter per side is on the field; the other two wait to be tagged in.</p>'+
      '<div class="teams2">'+side(0,'You')+'<div class="vs">VS</div>'+side(1,'Enemy')+'</div>'+
      '<nav class="row">'+btn('random','Randomize')+btn('swap','Swap sides')+btn('back','Back')+btn('fight','Fight','primary')+'</nav></div>';}

  function seg(key,opts){return '<div class="seg" data-nav data-cyc="seg" data-key="'+key+'" tabindex="0">'+opts.map(o=>'<button type="button" tabindex="-1" data-v="'+o[0]+'" aria-pressed="'+(settings[key]===o[0])+'">'+o[1]+'</button>').join('')+'</div>';}
  function tog(key){return '<button type="button" class="tog" data-nav data-tog="'+key+'" aria-pressed="'+!!settings[key]+'">'+(settings[key]?'On':'Off')+'</button>';}
  // a numeric setting: slider + value, Left / Right steps it (data-cyc="num")
  function num(key,label,mn,mx,st,unit,help){const v=settings[key];return '<div class="srow"><div><b>'+label+'</b>'+(help?'<small>'+help+'</small>':'')+'</div><div class="rng" data-nav data-cyc="num" data-key="'+key+'" data-min="'+mn+'" data-max="'+mx+'" data-step="'+st+'" data-unit="'+unit+'" tabindex="0"><input type="range" min="'+mn+'" max="'+mx+'" step="'+st+'" value="'+v+'" tabindex="-1" aria-label="'+label+'"><output>'+String(+(+v).toFixed(2))+unit+'</output></div></div>';}
  function settingsScr(){
    const row=(l,ctl,help)=>'<div class="srow"><div><b>'+l+'</b>'+(help?'<small>'+help+'</small>':'')+'</div>'+ctl+'</div>';
    return '<div class="scr wide"><h1>Settings</h1><div class="sets">'+
      row('Control level',seg('level',[['watch','Watch'],['commander','Commander'],['handson','Hands-on']]),'Watch: AI vs AI. Commander: the AI fights, your inputs take over. Hands-on: your fighter only acts when you press. (Tab in game)')+
      row('Game speed','<div class="rng" data-nav data-cyc="pace" tabindex="0"><input type="range" min="25" max="100" step="5" value="'+settings.pace+'" tabindex="-1"><output>'+settings.pace+'%</output></div>')+
      row('Camera',seg('cam',[['shoulder','Over the shoulder'],['dynamic','Dynamic'],['wide','Wide'],['cinematic','Cinematic']]),'Dynamic cuts between angles and on launches and ultimates. Cinematic: a director picks composed shots (two-shot, low hero angle, crane, orbit, long lens), event shots on ultimates / heavy hits / launches / K.O.s and on scenery breaking, on a weighted camera rig. (C in game)')+
      '<h3 class="sgroup">Sight lines (every camera)</h3>'+
      row('Move round obstacles',tog('sightMove'),'Planet: when a tree, pillar or landmark would block the fighters, the camera swings, rises or pulls in to a clear line first.')+
      num('sightMaxDeg','Max swing',0,80,5,'°','How far round the fighters the camera may swing off the shot to see past something.')+
      num('sightRaise','Max rise',0,10,.5,' m','How far it may rise to look over something.')+
      row('See-through',tog('sightFade'),'Anything still between the camera and the fighters dithers out (and comes back once clear).')+
      num('sightFadePct','See-through amount',0,80,5,'%','How much of a blocking object is left drawn. 0 = gone.')+
      row('X-ray silhouettes',tog('xrayOn'),'A fighter still hidden (by something not faded, or the planet horizon) shows as a flat team-coloured silhouette.')+
      num('xrayPct','X-ray strength',5,100,5,'%','')+
      '<h3 class="sgroup">Cinematic camera</h3>'+
      num('cineShotMin','Shortest shot',.5,10,.1,' s','Each shot is held a random time between these (shorter in a burst).')+
      num('cineShotMax','Longest shot',.5,15,.1,' s','')+
      num('cineCutPct','Cut chance',0,100,5,'%','A shot change is a hard cut this often, else the camera glides to the next shot.')+
      num('cineWeight','Camera weight',0,100,5,'%','Low = a heavy camera that lags and swings in; high = snappy.')+
      num('cineDamp','Overshoot damping',30,120,5,'%','Below 100 the camera overshoots a little and settles, like a real operator. 100 = no overshoot.')+
      num('cineLeadMs','Look ahead',0,800,25,' ms','The view leads the fighters by this much of their movement.')+
      num('cineFrame','Composed framing',0,150,5,'%','Lead room: the fighters sit off centre with space the way they move (rule of thirds). 0 = always centred.')+
      num('cineDutch','Dutch tilt',0,25,1,'°','The most the camera tilts on intense moments (bursts, low shots, ultimates).')+
      row('Event shots',tog('cineEvents'),'Ultimate = low hero shot pushing in; launch / spike = a crane on the thrown fighter; K.O. = slow orbit on the fallen.')+
      num('cineCrash','Crash zoom',0,50,1,'%','Heavy hits punch the view in by this much, then it springs back.')+
      row('Destruction shots',tog('cineBreakOn'),'A tree, pillar or scenery piece breaking near the fight cuts to a short shot of the break with a touch of slow-mo.')+
      num('cineBreakMinM','Least height',0,20,.5,' m','Only pieces at least this tall get a shot.')+
      num('cineBreakS','Break shot length',.3,4,.1,' s','More breaks during it stretch it a little (a chain through a grove reads as one shot).')+
      num('cineBreakSlowMs','Break slow-mo',0,1500,50,' ms','')+
      num('cineBreakCdS','Break shot cooldown',0,30,.5,' s','')+
      '<h3 class="sgroup">Knockback tracking shot</h3>'+
      row('Tracking shot',tog('trackOn'),'Over the shoulder, Dynamic and Cinematic: when one hit throws a fighter far, the camera swoops in behind it in one move, rides along with it facing the way it flies, then glides back just before the knockback ends.')+
      num('trackMinPx','Starts at knockback',200,3000,50,' px','A single hit must carry the fighter at least this far.')+
      num('trackDist','Distance behind',1.5,14,.5,' m','')+
      num('trackHeight','Height above',0,6,.25,' m','')+
      row('Golden-ratio framing',tog('trackGolden'),'Puts the flying fighter on the top-right golden-ratio crossing of the frame (off = centred).')+
      row('Side',seg('trackSide',[['right','Right'],['left','Left']]),'Which quarter the camera swings to.')+
      num('trackAngle','Angle',0,90,5,'°','3/4 view: how far the camera swings off straight behind the flight. 0 = straight behind (full face of a fighter thrown backwards).')+
      num('trackZoom','Zoom in',0,60,5,'%','How much narrower the view gets while tracking.')+
      num('trackInMs','Swoop-in time',100,1500,20,' ms','The single move from the normal shot to the fighter.')+
      num('trackOutMs','Glide-back time',100,2000,20,' ms','')+
      num('trackLeadMs','Ease out early',0,1000,25,' ms','Start the glide back this long before the knockback ends.')+
      num('trackMaxS','Longest track',.5,6,.25,' s','Ends sooner when the fighter lands and stops.')+
      num('trackCdS','Cooldown',0,30,.5,' s','Least time between two tracking shots.')+
      '<h3 class="sgroup">Knockback combos</h3>'+
      row('Combos',tog('comboOn'),'A fighter still stunned by a hit can be hit again. Each hit redirects its flight: a light hit holds it near you, a heavy one throws it the new way. You and the AI.')+
      row('Auto chase',tog('comboChase'),'A melee attacker snaps after the fighter it knocked back. Off: catch it yourself with Space (no WASD) or the lock-on.')+
      num('comboChaseMs','Chase delay',0,600,10,' ms','Auto chase: how long after the hit it sets off.')+
      num('comboCap','Combo cap',2,20,1,' hits','The hit that reaches this count still lands, then the target breaks free.')+
      num('comboDecayPct','Decay per hit',0,40,1,'%','Each hit already in the combo: this much less damage and stun.')+
      num('comboBreakMs','Break-free guard',0,2000,50,' ms','After breaking free the target cannot be hit until its stun ends plus this.')+
      num('comboReachPct','Extra reach',0,200,5,'%','Melee reach against a stunned, flying target.')+
      num('comboLift','Air juggle lift',0,1500,25,' px/s','Each combo hit on an airborne target lifts it this much (less each hit).')+
      '<h3 class="sgroup">Lock-on (T or middle mouse)</h3>'+
      num('lockHomePx','Homing range',0,3000,50,' px','Attack keys snap in to the locked target from up to this far.')+
      row('Tracking shot while locked',tog('lockTrack'),'Off: the camera stays on the over-the-shoulder shot of your target while locked on.')+
      '<h3 class="sgroup">Display</h3>'+
      row('Show intents',tog('labels'),'Each fighter\'s rhythm intent above its head.')+
      row('Feel panel',tog('feel'),'Live numbers against the 2D duel ranges.')+
      row('AI parries',tog('aiParry'),'Computer fighters parry by chance (you always parry with Ctrl+Space).')+
      row('Quality',seg('quality',[['low','Low'],['medium','Medium'],['high','High']]),'Render resolution. Lower it if the game stutters.')+
      row('Fullscreen','<button type="button" class="tog" data-nav data-act="fullscreen" aria-pressed="'+!!document.fullscreenElement+'">'+(document.fullscreenElement?'On':'Off')+'</button>','Or press F11.')+
      '</div><nav class="row">'+btn('back','Back','primary')+'</nav></div>';}

  function controls(){
    const K=[['WASD','Steer, relative to the camera (the AI takes back over 0.6 s after you let go)'],['Shift (hold)','Sprint: Lv2 speed while held. Double-tap and hold = Lv3 (characters with Lv3 speed on in FX Studio 3D)'],['Space','Snap: blink-dash your WASD way, or through and behind the target. Just before an enemy hit = perfect snap'],['Ctrl+Space','Parry. Right on the hit = perfect: no damage, attacker staggered, counter window (your hits x1.5). A shot is sent back at the shooter, or away the way you hold WASD. A bit late = normal parry: less damage and knockback'],['J','Chain: start the next attack now, skipping the rhythm gap'],['K / L','Special / second special'],['I','Ultimate'],['1 2 3 4','Call an intent: pressure · punish (target open) · reset · feint'],['Q / E','Tag a partner in (enters with an attack)'],['R','Jump. Press again in the air = double jump, then gravity brings you down'],['F','Fast fall (in the air)'],['R / F (flyers)','Characters that can fly: hold to climb / descend, let go to stay at that height. With Space: snap straight up / down'],['T / Middle mouse','Lock on to the enemy (Training: the nearest dummy). WASD: in / out / circle it, the camera holds the shot on it, attacks snap in to it. Again to release'],['C','Camera: over the shoulder / dynamic / wide / cinematic'],['Tab','Control level'],['Esc / P','Pause']];
    return '<div class="scr wide"><h1>Controls</h1><dl class="keys">'+K.map(k=>'<dt>'+k[0]+'</dt><dd>'+esc(k[1])+'</dd>').join('')+'</dl>'+
      '<nav class="row">'+btn('back','Back','primary')+'</nav></div>';}

  function pause(){
    return '<div class="scr"><h1>Paused</h1><nav class="stack">'+btn('resume','Resume','primary')+(running&&training?btn('training','Training settings')+btn('restart','Restart training'):btn('restart','Restart fight'))+btn('settings','Settings')+btn('controls','Controls')+btn('title','Quit to title')+'</nav></div>';}

  function results(){
    const r=result||{win:false,rows:[]};
    return '<div class="scr"><h1 class="'+(r.win?'win':'lose')+'">'+(r.win?'Victory':'Defeat')+'</h1><table class="res">'+r.rows.map(x=>'<tr><td>'+esc(x[0])+'</td><td>'+esc(x[1])+'</td></tr>').join('')+'</table>'+
      '<nav class="row">'+btn('fight','Rematch','primary')+btn('teams','Change teams')+btn('title','Title')+'</nav></div>';}


  /* ---------- training screen: top-down map of the arena (training.js) ----------
     Click empty ground = drop a dummy (it takes the last behaviour / character you picked), drag = move it,
     right-click = remove it, Delete = remove the selected one. The panel sets the selected dummy. */
  let trSel=0,trDrag=-1,trLast={beh:'stand',kit:''};
  const who=(k,sub)=>{const kit=KITS[k];return '<span class="who"><i style="background:'+cssc(kit.col)+';box-shadow:0 0 0 2px '+cssc(kit.fx)+'"></i><b>'+esc(NAMES[k]||kit.name)+'</b><small>'+esc(sub||((ROLES[k]||'')+' · '+kit.hp+' HP'))+'</small></span>';};
  const pick=(cyc,k,sub)=>'<div class="slot" data-nav data-cyc="'+cyc+'" tabindex="0"><button type="button" class="ar" data-step="-1" tabindex="-1" aria-label="Previous">◀</button>'+who(k,sub)+'<button type="button" class="ar" data-step="1" tabindex="-1" aria-label="Next">▶</button></div>';
  function trainingScr(){
    const T=trainCfg(),ds=T.dummies;trSel=Math.min(trSel,ds.length-1);const d=ds[trSel];const live=running&&training;
    const m=z=>(z/BODY*1.8).toFixed(1)+' m';
    let side='<h3>Your fighter</h3>'+pick('trfighter',trainFighterKey());
    side+='<h3>'+(d?'Dummy '+(trSel+1):'Dummies')+' <small style="color:var(--muted);letter-spacing:0">'+ds.length+' / '+TRAIN.maxDummies+'</small></h3>';
    if(d){side+='<div class="seg" data-nav data-cyc="trbeh" tabindex="0">'+TRAIN_BEH.map(b=>'<button type="button" tabindex="-1" data-v="'+b[0]+'" aria-pressed="'+(d.beh===b[0])+'">'+b[1]+'</button>').join('')+'</div>'+
        '<p class="note">'+({stand:'Never moves or acts. A good punching bag.',guard:'Blocks every hit (damage −70 %) and parries by chance.',fight:'Fights back with its character\'s AI, at half damage.'}[d.beh]||'')+'</p>'+
        pick('trkit',trainDummyKit(d))+
        '<div class="rng" data-nav data-cyc="trz" tabindex="0"><span style="font-size:.85em;color:var(--muted)">Height</span><input type="range" min="0" max="'+ZMAX+'" step="25" value="'+Math.round(d.z||0)+'" tabindex="-1"><output>'+m(d.z||0)+'</output></div>'+
        '<nav class="row" style="justify-content:flex-start">'+btn('trdel','Remove dummy')+btn('trclear','Clear all')+'</nav>';}
    else side+='<p class="note">Click the map to drop a dummy. With none, your fighter trains alone (it only acts on your inputs).</p>';
    return '<div class="scr wide"><h1>Training</h1><p class="sub">You alone on the field with practice dummies. Nobody is K.O.\'d: HP refills after a short pause.</p>'+
      '<div class="trgrid"><div class="trmapw"><canvas id="trmap"></canvas><small>Click = drop a dummy · drag = move · right-click / Delete = remove · ◆ = you'+(live?' (now)':' (start)')+'</small></div><div class="trside">'+side+'</div></div>'+
      '<nav class="row">'+(live?btn('back','Back to training','primary'):btn('back','Back')+btn('trstart','Start training','primary'))+'</nav></div>';}
  function trMapXY(cv,ev){const r=cv.getBoundingClientRect();return [clamp((ev.clientX-r.left)/r.width*MAPW,60,MAPW-60),clamp((ev.clientY-r.top)/r.height*MAPH,60,MAPH-60)];}   // map px (the old arena area)
  function trHit(cv,ev){const r=cv.getBoundingClientRect(),ds=trainCfg().dummies;let bi=-1,bd=14;
    ds.forEach((d,i)=>{const dd=Math.hypot(ev.clientX-r.left-d.x/MAPW*r.width,ev.clientY-r.top-d.y/MAPH*r.height);if(dd<bd){bd=dd;bi=i;}});return bi;}
  function trDraw(){const cv=root.querySelector('#trmap');if(!cv)return;const dpr=window.devicePixelRatio||1,cw=Math.max(200,Math.floor(cv.parentNode.clientWidth-parseFloat(getComputedStyle(cv.parentNode).paddingLeft)*2)),ch=Math.round(cw*MAPH/MAPW);
    if(cv.width!==Math.round(cw*dpr)||cv.style.width!==cw+'px'){cv.width=Math.round(cw*dpr);cv.height=Math.round(ch*dpr);cv.style.width=cw+'px';cv.style.height=ch+'px';}
    const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,cw,ch);const sx=cw/MAPW,sy=ch/MAPH;
    g.fillStyle='#0c1026';g.fillRect(0,0,cw,ch);g.strokeStyle='#1e2548';g.lineWidth=1;
    for(let x=0;x<=MAPW;x+=300){g.beginPath();g.moveTo(x*sx+.5,0);g.lineTo(x*sx+.5,ch);g.stroke();}for(let y=0;y<=MAPH;y+=300){g.beginPath();g.moveTo(0,y*sy+.5);g.lineTo(cw,y*sy+.5);g.stroke();}
    g.strokeStyle='#2a3360';g.strokeRect(.5,.5,cw-1,ch-1);
    // you: start spot, or where your fighter is now while training runs
    const p=running&&training?sides[0].team[0]:null;const px=((p?p.x:TRAIN_START[0])-MX0)*sx,py=((p?p.y:TRAIN_START[1])-MY0)*sy,kit=KITS[trainFighterKey()];
    g.save();g.translate(px,py);g.rotate(Math.PI/4);g.fillStyle=cssc(kit.col);g.strokeStyle='#fff';g.lineWidth=1.5;g.fillRect(-6,-6,12,12);g.strokeRect(-6,-6,12,12);g.restore();
    g.font='600 11px '+getComputedStyle(document.body).fontFamily;g.textAlign='center';g.textBaseline='middle';g.fillStyle='#e8ecfb';g.fillText('YOU',px,py-15);
    const COL={stand:'#9aa1bd',guard:'#8fd3ff',fight:'#ff6a80'};
    trainCfg().dummies.forEach((d,i)=>{const x=d.x*sx,y=d.y*sy;
      if(d.z>0){const up=Math.min(28,d.z/ZMAX*28+4);g.strokeStyle=COL[d.beh]||'#9aa1bd';g.setLineDash([2,2]);g.beginPath();g.moveTo(x,y);g.lineTo(x,y-up);g.stroke();g.setLineDash([]);
        g.fillStyle='#c9cfe6';g.textAlign='left';g.fillText('↑'+(d.z/BODY*1.8).toFixed(1)+'m',x+11,y-up);g.textAlign='center';}
      g.beginPath();g.arc(x,y,9,0,TAU);g.fillStyle=COL[d.beh]||'#9aa1bd';g.fill();
      if(i===trSel){g.lineWidth=2.5;g.strokeStyle='#ffffff';g.stroke();g.beginPath();g.arc(x,y,13,0,TAU);g.lineWidth=1;g.strokeStyle='rgba(255,255,255,.45)';g.stroke();}
      g.fillStyle='#0c1026';g.fillText(String(i+1),x,y+.5);});}
  function trSetup(){const cv=root.querySelector('#trmap');if(!cv)return;trDraw();
    cv.addEventListener('mousedown',ev=>{if(ev.button!==0)return;ev.preventDefault();const T=trainCfg(),i=trHit(cv,ev);
      if(i>=0){trSel=i;trDrag=i;}else if(T.dummies.length<TRAIN.maxDummies){const [x,y]=trMapXY(cv,ev);T.dummies.push({x,y,z:0,beh:trLast.beh,kit:trLast.kit});trSel=trDrag=T.dummies.length-1;saveSettings();}
      else{trDrag=-1;}render(root.querySelector('[data-cyc="trbeh"]'));});
    cv.addEventListener('contextmenu',ev=>{ev.preventDefault();const i=trHit(cv,ev);if(i<0)return;trRemove(i);});}
  function trRemove(i){const T=trainCfg();if(i<0||i>=T.dummies.length)return;T.dummies.splice(i,1);trSel=Math.max(0,Math.min(trSel,T.dummies.length-1));saveSettings();render();}
  window.addEventListener('mousemove',ev=>{if(trDrag<0||cur!=='training')return;const cv=root.querySelector('#trmap'),d=trainCfg().dummies[trDrag];if(!cv||!d)return;[d.x,d.y]=trMapXY(cv,ev);trDraw();});
  window.addEventListener('mouseup',()=>{if(trDrag<0)return;trDrag=-1;saveSettings();});
  window.addEventListener('resize',()=>{if(cur==='training')trDraw();});

  const SCREENS={title,teams,settings:settingsScr,controls,pause,results,training:trainingScr};

  /* ---------- actions ---------- */
  function act(id){
    switch(id){
    case'fight':begin();break;
    case'teams':show('teams');break;
    case'settings':show('settings');break;
    case'controls':show('controls');break;
    case'back':back();break;
    case'resume':setPaused(false);break;
    case'restart':if(training)trainBegin();else begin();break;
    case'training':show('training');break;
    case'trstart':trainBegin();break;
    case'trdel':trRemove(trSel);break;
    case'trclear':trainCfg().dummies.length=0;trSel=0;saveSettings();render();break;
    case'title':toTitle();break;
    case'fullscreen':toggleFullscreen();break;
    case'random':settings.teams=[0,1].map(()=>{const p=KEYS.slice().sort(()=>Math.random()-.5);return p.slice(0,3);});saveSettings();refreshTitleTeams();render();break;
    case'swap':settings.teams=[settings.teams[1],settings.teams[0]];saveSettings();refreshTitleTeams();render();break;}}
  function refreshTitleTeams(){if(!running)newGame();}
  function cycle(el,step){
    const c=el.dataset.cyc;
    if(c==='team'){const si=+el.dataset.side,i=+el.dataset.i;const k=settings.teams[si][i];const n=KEYS[(KEYS.indexOf(k)+step+KEYS.length)%KEYS.length];
      settings.teams[si]=settings.teams[si].slice();settings.teams[si][i]=n;saveSettings();refreshTitleTeams();render(el);}
    else if(c==='seg'){const key=el.dataset.key;const vs=[...el.querySelectorAll('button')].map(b=>b.dataset.v);setSeg(key,vs[clamp(vs.indexOf(settings[key])+step,0,vs.length-1)]);render(el);}
    else if(c==='pace'){setPace(clamp(settings.pace+step*5,25,100));render(el);}
    else if(c==='num'){const k=el.dataset.key,st=+el.dataset.step;settings[k]=clamp(Math.round((settings[k]+step*st)/st)*st,+el.dataset.min,+el.dataset.max);saveSettings();render(el);}
    else if(c==='trfighter'){const T=trainCfg();const k=trainFighterKey();T.fighter=KEYS[(KEYS.indexOf(k)+step+KEYS.length)%KEYS.length];saveSettings();render(el);}
    else if(c==='trkit'||c==='trbeh'||c==='trz'){const d=trainCfg().dummies[trSel];if(!d)return;
      if(c==='trkit'){const k=trainDummyKit(d);d.kit=KEYS[(KEYS.indexOf(k)+step+KEYS.length)%KEYS.length];trLast.kit=d.kit;}
      else if(c==='trbeh'){const vs=TRAIN_BEH.map(b=>b[0]);d.beh=vs[clamp(vs.indexOf(d.beh)+step,0,vs.length-1)];trLast.beh=d.beh;}
      else d.z=clamp((+d.z||0)+step*50,0,ZMAX);
      saveSettings();render(el);}}
  function setSeg(key,v){if(key==='level')setLevel(v);else if(key==='cam')setCam(v);else{settings[key]=v;saveSettings();if(key==='quality')applyQuality();}}
  function toggleFullscreen(){try{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen();}catch(e){}}
  document.addEventListener('fullscreenchange',()=>{if(cur==='title'||cur==='settings')render();setTimeout(resize,50);});

  /* ---------- rendering + input ---------- */
  function render(keep){
    if(!cur){root.hidden=true;return;}
    const sel=keep&&keep.dataset?navKey(keep):null;
    root.hidden=false;root.className='menu m-'+cur+(running&&!ended?' over':'');root.innerHTML=SCREENS[cur]();
    root.querySelectorAll('[data-act]').forEach(b=>b.addEventListener('click',()=>act(b.dataset.act)));
    root.querySelectorAll('[data-tog]').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.tog;settings[k]=!settings[k];saveSettings();render(b);}));
    root.querySelectorAll('[data-cyc="team"],[data-cyc="trfighter"],[data-cyc="trkit"]').forEach(el=>el.querySelectorAll('[data-step]').forEach(b=>b.addEventListener('click',ev=>{ev.stopPropagation();cycle(el,+b.dataset.step);})));
    root.querySelectorAll('[data-cyc="seg"]').forEach(el=>el.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{setSeg(el.dataset.key,b.dataset.v);render(el);})));
    root.querySelectorAll('[data-cyc="trbeh"]').forEach(el=>el.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{const d=trainCfg().dummies[trSel];if(!d)return;d.beh=trLast.beh=b.dataset.v;saveSettings();render(el);})));
    root.querySelectorAll('[data-cyc="trz"] input').forEach(inp=>inp.addEventListener('input',()=>{const d=trainCfg().dummies[trSel];if(!d)return;d.z=+inp.value;inp.nextElementSibling.textContent=(d.z/BODY*1.8).toFixed(1)+' m';saveSettings();trDraw();}));
    if(cur==='training')trSetup();
    root.querySelectorAll('[data-cyc="num"] input').forEach(inp=>inp.addEventListener('input',()=>{const el=inp.parentNode,st=+el.dataset.step;settings[el.dataset.key]=+inp.value;inp.nextElementSibling.textContent=String(+(+inp.value).toFixed(2))+el.dataset.unit;saveSettings();}));
    root.querySelectorAll('[data-cyc="pace"] input').forEach(inp=>inp.addEventListener('input',()=>{setPace(+inp.value);inp.nextElementSibling.textContent=inp.value+'%';}));
    const items=nav();let f=sel?items.find(e=>navKey(e)===sel):null;(f||items[0])&&(f||items[0]).focus({preventScroll:true});}
  function nav(){return [...root.querySelectorAll('[data-nav]')];}
  function navKey(el){return [el.dataset.act,el.dataset.tog,el.dataset.cyc,el.dataset.key,el.dataset.side,el.dataset.i].join('|');}
  window.addEventListener('keydown',ev=>{
    if(!cur)return;
    const items=nav();const i=items.indexOf(document.activeElement);
    if(ev.code==='Escape'||ev.code==='KeyP'&&cur==='pause'){ev.preventDefault();ev.stopImmediatePropagation();if(cur==='pause')setPaused(false);else if(cur!=='title'&&cur!=='results')back();return;}
    if(ev.code==='ArrowDown'||ev.code==='ArrowUp'||ev.code==='Tab'){ev.preventDefault();const d=(ev.code==='ArrowUp'||(ev.code==='Tab'&&ev.shiftKey))?-1:1;const n=items[(i+d+items.length)%items.length];n&&n.focus();return;}
    if((ev.code==='ArrowLeft'||ev.code==='ArrowRight')&&i>=0&&items[i].dataset.cyc){ev.preventDefault();cycle(items[i],ev.code==='ArrowLeft'?-1:1);return;}
    if((ev.code==='Enter'||ev.code==='Space')&&i>=0){const el=items[i];if(el.dataset.cyc){ev.preventDefault();if(el.dataset.cyc!=='pace'&&el.dataset.cyc!=='trz')cycle(el,1);}}
    if(cur==='training'&&(ev.code==='Delete'||ev.code==='Backspace')){ev.preventDefault();trRemove(trSel);}
  },true);

  /* ---------- API ---------- */
  function show(name,reset){if(reset)stack=[];else if(cur&&cur!==name)stack.push(cur);cur=name;render();}
  function back(){const was=cur;if(was==='training')trainApply();   // training.js: rebuild the dummies from the map
    cur=stack.length?stack.pop():null;if(!cur&&running&&!ended){paused=false;host.focus();}render();}
  function close(){cur=null;stack=[];render();}
  return {show,back,close,isOpen:()=>cur!=null,results:(win,rows)=>{result={win,rows};show('results',true);},current:()=>cur};
})();
