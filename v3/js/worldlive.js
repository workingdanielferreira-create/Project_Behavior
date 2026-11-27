'use strict';
/* Live world link (Daniel 2026-11-27: "make World Studio 3D auto save and load updates in real time with the game").
   World Studio 3D auto-saves characters/world3d.json ~0.5 s after each edit (its characters folder must be picked once).
   The game reads that file every second (XMLHttpRequest on file://: run_v3.bat starts the game window with
   --allow-file-access-from-files, only for its own profile) and, when it changed:
   - copies the new settings into WORLD_CFG (in place) and the gravity numbers into GRAV / JUMP (apply at once);
   - rebuilds the planet right away round the fight (planet.js planetReset with the CURRENT world's seed, so the layout
     stays the same unless the World seed itself changed). Fighters, HP and the fight carry on; craters, trenches and
     broken scenery start fresh;
   - Planet on / off can't switch while running (the sim plane size depends on it): a callout says to restart.
   No flag / no file = it quietly does nothing (the game keeps the settings packed at start by run_v3.bat). */
const WORLD_LIVE={url:'../characters/world3d.json',last:null,fails:0,warned:false,next:0};
function worldLiveRead(){const now=performance.now();if(now<WORLD_LIVE.next)return;let txt=null;
  try{const x=new XMLHttpRequest();x.open('GET',WORLD_LIVE.url,false);x.overrideMimeType('application/json');x.send();
    if((x.status===0||x.status===200)&&x.responseText)txt=x.responseText;}catch(e){}
  // not readable (no flag / no file yet): after 3 misses, look only every 15 s (the browser logs each blocked read)
  if(txt==null){if(++WORLD_LIVE.fails>=3)WORLD_LIVE.next=now+15000;if(WORLD_LIVE.fails===3&&!WORLD_LIVE.warned){WORLD_LIVE.warned=true;console.info('World Studio 3D live link off: characters/world3d.json not readable (restart the game with run_v3.bat to turn it on).');}return;}
  WORLD_LIVE.fails=0;if(txt===WORLD_LIVE.last)return;const first=WORLD_LIVE.last===null;WORLD_LIVE.last=txt;
  let src;try{src=JSON.parse(txt);}catch(e){return;}   // caught mid-write: the next read gets it
  const cfg=World3D.merge(src);
  const strip=c=>{const o=JSON.parse(JSON.stringify(c));o.planet.enabled=PLANET;return JSON.stringify(o);};
  if(strip(cfg)===strip(WORLD_CFG))return;   // same as what is running (e.g. the first read = the packed file)
  worldLiveApply(cfg,first);}
function worldLiveApply(cfg,quiet){
  const oldSeed=WORLD_CFG.planet.seed,wantPlanet=!!cfg.planet.enabled;
  for(const s of World3D.SECTIONS){const d=WORLD_CFG[s.id],v=cfg[s.id];for(const k in v)d[k]=Array.isArray(v[k])?v[k].slice():v[k];}
  WORLD_CFG.planet.enabled=PLANET;   // planet on / off needs a restart
  Object.assign(GRAV,World3D.gravityOf(WORLD_CFG));
  JUMP.h1=300*GRAV.jump;JUMP.h2=240*GRAV.jump;JUMP.gravity=GRAV.gravity;JUMP.maxJumps=GRAV.maxJumps;JUMP.fastFall=GRAV.fastFall;
  if(PLANET&&world){const seed=WORLD_CFG.planet.seed!==oldSeed?WORLD_CFG.planet.seed:world.seed,A=world.A.clone();
    sides.forEach(s=>s.team.forEach(f=>{if(f)f.trL=null;}));   // knockback trenches belonged to the old world
    planetReset(seed,A.x,A.z);}
  if(!quiet&&typeof callout==='function'&&running&&!ended)
    callout(wantPlanet!==PLANET?'World updated · restart for planet on / off':'World updated','World Studio 3D','#9fe0ff',.6,true);}
setInterval(()=>{try{worldLiveRead();}catch(e){console.error(e);}},1000);
