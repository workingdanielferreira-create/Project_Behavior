'use strict';
/* Core: shared constants (tick, arena W x H in 2D px, BODY = 88 px, K = 2D px -> 3D units, ZMAX air, world settings / planet flag) and maths helpers. */
const $=id=>document.getElementById(id);
const TAU=Math.PI*2, TICK=16, DT=TICK/1000;
const rnd=(a,b)=>a+Math.random()*(b-a);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
// World settings (World Studio 3D -> characters/world3d.json -> data/world.gen.js). Planet on = the fight runs on a little
// globe (world3d.js / planet.js): the sim plane has no walls, so W / H are huge; MAPW x MAPH round the centre = the old arena
// (training map, start spots). Planet off = the flat walled arena exactly as before (MX0 = MY0 = 0).
const WORLD_CFG=World3D.merge(window.PB3_WORLD),PLANET=!!WORLD_CFG.planet.enabled;
const MAPW=4200,MAPH=2600;
const W=PLANET?400000:MAPW,H=PLANET?400000:MAPH,BODY=88,K=1.8/BODY,ZMAX=4500; // a bigger ground plane + 4,500 px (about 51 bodies) of air (tripled from 1,500, Daniel 2026-11-26)
const MX0=(W-MAPW)/2,MY0=(H-MAPH)/2;
