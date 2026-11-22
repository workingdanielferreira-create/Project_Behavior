'use strict';
/* Core: shared constants (tick, arena W x H in 2D px, BODY = 88 px, K = 2D px -> 3D units, ZMAX air) and maths helpers. */
const $=id=>document.getElementById(id);
const TAU=Math.PI*2, TICK=16, DT=TICK/1000;
const rnd=(a,b)=>a+Math.random()*(b-a);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const W=4200,H=2600,BODY=88,K=1.8/BODY,ZMAX=1500; // a bigger ground plane + 1,500 px (about 17 bodies) of air
