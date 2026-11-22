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
      '<nav class="stack">'+btn('fight','Fight','primary')+btn('teams','Teams')+btn('settings','Settings')+btn('controls','Controls')+btn('fullscreen',document.fullscreenElement?'Leave fullscreen':'Fullscreen')+'</nav>'+
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
  function settingsScr(){
    const row=(l,ctl,help)=>'<div class="srow"><div><b>'+l+'</b>'+(help?'<small>'+help+'</small>':'')+'</div>'+ctl+'</div>';
    return '<div class="scr wide"><h1>Settings</h1><div class="sets">'+
      row('Control level',seg('level',[['watch','Watch'],['commander','Commander'],['handson','Hands-on']]),'Watch: AI vs AI. Commander: the AI fights, your inputs take over. Hands-on: your fighter only acts when you press. (Tab in game)')+
      row('Game speed','<div class="rng" data-nav data-cyc="pace" tabindex="0"><input type="range" min="25" max="100" step="5" value="'+settings.pace+'" tabindex="-1"><output>'+settings.pace+'%</output></div>')+
      row('Camera',seg('cam',[['shoulder','Over the shoulder'],['dynamic','Dynamic'],['wide','Wide']]),'Dynamic cuts between angles and on launches and ultimates. (C in game)')+
      row('Show intents',tog('labels'),'Each fighter\'s rhythm intent above its head.')+
      row('Feel panel',tog('feel'),'Live numbers against the 2D duel ranges.')+
      row('Quality',seg('quality',[['low','Low'],['medium','Medium'],['high','High']]),'Render resolution. Lower it if the game stutters.')+
      row('Fullscreen','<button type="button" class="tog" data-nav data-act="fullscreen" aria-pressed="'+!!document.fullscreenElement+'">'+(document.fullscreenElement?'On':'Off')+'</button>','Or press F11.')+
      '</div><nav class="row">'+btn('back','Back','primary')+'</nav></div>';}

  function controls(){
    const K=[['WASD','Steer, relative to the camera (the AI takes back over 0.6 s after you let go)'],['Space','Snap: blink-dash your WASD way, or through and behind the target. Just before an enemy hit = perfect snap'],['J','Chain: start the next attack now, skipping the rhythm gap'],['K / L','Special / second special'],['I','Ultimate'],['1 2 3 4','Call an intent: pressure · punish (target open) · reset · feint'],['Q / E','Tag a partner in (enters with an attack)'],['R / F','Fly up / down (hold). With Space: snap straight up / down'],['C','Camera: over the shoulder / dynamic / wide'],['Tab','Control level'],['Esc / P','Pause']];
    return '<div class="scr wide"><h1>Controls</h1><dl class="keys">'+K.map(k=>'<dt>'+k[0]+'</dt><dd>'+esc(k[1])+'</dd>').join('')+'</dl>'+
      '<nav class="row">'+btn('back','Back','primary')+'</nav></div>';}

  function pause(){
    return '<div class="scr"><h1>Paused</h1><nav class="stack">'+btn('resume','Resume','primary')+btn('restart','Restart fight')+btn('settings','Settings')+btn('controls','Controls')+btn('title','Quit to title')+'</nav></div>';}

  function results(){
    const r=result||{win:false,rows:[]};
    return '<div class="scr"><h1 class="'+(r.win?'win':'lose')+'">'+(r.win?'Victory':'Defeat')+'</h1><table class="res">'+r.rows.map(x=>'<tr><td>'+esc(x[0])+'</td><td>'+esc(x[1])+'</td></tr>').join('')+'</table>'+
      '<nav class="row">'+btn('fight','Rematch','primary')+btn('teams','Change teams')+btn('title','Title')+'</nav></div>';}

  const SCREENS={title,teams,settings:settingsScr,controls,pause,results};

  /* ---------- actions ---------- */
  function act(id){
    switch(id){
    case'fight':begin();break;
    case'teams':show('teams');break;
    case'settings':show('settings');break;
    case'controls':show('controls');break;
    case'back':back();break;
    case'resume':setPaused(false);break;
    case'restart':begin();break;
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
    else if(c==='pace'){setPace(clamp(settings.pace+step*5,25,100));render(el);}}
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
    root.querySelectorAll('[data-cyc="team"]').forEach(el=>el.querySelectorAll('[data-step]').forEach(b=>b.addEventListener('click',ev=>{ev.stopPropagation();cycle(el,+b.dataset.step);})));
    root.querySelectorAll('[data-cyc="seg"]').forEach(el=>el.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{setSeg(el.dataset.key,b.dataset.v);render(el);})));
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
    if((ev.code==='Enter'||ev.code==='Space')&&i>=0){const el=items[i];if(el.dataset.cyc){ev.preventDefault();if(el.dataset.cyc!=='pace')cycle(el,1);}}
  },true);

  /* ---------- API ---------- */
  function show(name,reset){if(reset)stack=[];else if(cur&&cur!==name)stack.push(cur);cur=name;render();}
  function back(){cur=stack.length?stack.pop():null;if(!cur&&running&&!ended){paused=false;host.focus();}render();}
  function close(){cur=null;stack=[];render();}
  return {show,back,close,isOpen:()=>cur!=null,results:(win,rows)=>{result={win,rows};show('results',true);},current:()=>cur};
})();
