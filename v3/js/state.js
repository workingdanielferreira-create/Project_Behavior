'use strict';
/* World state: tick, flags, sides, shots, director, metrics, later() timers. */
/* ================= world state ================= */
let tick=0,running=false,paused=false,ended=false,hitstopMs=0,camPunch=0,shakeDir=[0,0],slowmo=0,shake=0,acc=0,pace=1,level='commander';
const sides=[{team:[],on:0,tagCd:0},{team:[],on:0,tagCd:0}];
const shots=[];const lat=[];
const director={I:0,phase:'calm',left:0,at:.8,quiet:0,hits:0,dmg:0,cnt:0,taken:0,ko:0};
const metr={hits:[],dist:[],both:[],burst:[],snaps:[],starts:[]};
let stats;
function later(ms,fn){lat.push({t:tick+Math.round(ms/TICK),fn});}
const ms2t=ms=>Math.max(1,Math.round(ms/TICK));
