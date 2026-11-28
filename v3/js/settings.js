'use strict';
/* ================= settings =================
   Everything the Settings / Teams screens change, kept between sessions in
   localStorage (the app window has its own profile, see run_v3.bat). If
   storage is blocked the game still runs on the defaults. */
const SETTINGS_KEY='pb3.settings.v1';
const DEFAULT_SETTINGS={
  level:'commander',          // watch | commander | handson
  pace:100,                   // game speed %, 25..100
  cam:'shoulder',             // shoulder | dynamic | wide | cinematic
  // sight lines (cinecam.js, every camera mode, planet): move round obstacles, then fade, X-ray what is still hidden
  sightMove:true,             // swing / rise / pull in to a clear line
  sightMaxDeg:50,             // largest swing off the shot (deg)
  sightRaise:4,               // largest rise (m)
  sightFade:true,             // what still blocks dithers out
  sightFadePct:20,            // % of a blocking object left drawn
  xrayOn:true,                // hidden fighters as team-coloured silhouettes
  xrayPct:55,                 // silhouette strength %
  // cinematic camera (cinecam.js)
  cineShotMin:2.4,            // s, shortest base shot
  cineShotMax:5.2,            // s, longest base shot
  cineCutPct:55,              // % of shot changes that are hard cuts (else a glide)
  cineWeight:45,              // spring stiffness 0..100 (heavy .. snappy)
  cineDamp:80,                // damping ratio % (below 100 = a little overshoot)
  cineLeadMs:250,             // look ahead along the fighters' movement
  cineFrame:100,              // composed framing (lead room) strength %
  cineDutch:9,                // max dutch tilt (deg)
  cineEvents:true,            // event shots (ultimate / launch / K.O.)
  cineCrash:25,               // crash zoom on heavy hits, % narrower
  cineBreakOn:true,           // destruction shots
  cineBreakMinM:3,            // least height of a broken piece (m)
  cineBreakS:1.2,             // break shot length (s)
  cineBreakSlowMs:450,        // slow-mo during it (ms of sim slowmo)
  cineBreakCdS:4,             // cooldown between two break shots (s)
  labels:true,                // rhythm intent above each fighter
  feel:true,                  // live numbers vs the 2D duel
  quality:'high',             // low | medium | high (render resolution)
  aiParry:true,               // AI fighters parry by chance (parry.js)
  // knockback tracking shot (camera.js, over the shoulder + dynamic)
  trackOn:true,               // on / off
  trackMinPx:500,             // a single hit must carry the fighter at least this far (px)
  trackDist:4.5,              // metres behind the flying fighter
  trackHeight:1.4,            // metres above it
  trackGolden:true,           // frame the flying fighter on the golden-ratio top-right crossing
  trackSide:'right',          // 3/4 view on the right / left of the flight line
  trackAngle:45,              // 3/4 view: degrees off straight behind the flight line (0 = behind = full face of a fighter flying backwards)
  trackLeadMs:250,            // start the glide back this long before the knockback is predicted to end
  trackZoom:25,               // % narrower view while tracking (zoom in)
  trackInMs:380,              // the one-move swoop in
  trackOutMs:520,             // the glide back
  trackMaxS:2.5,              // longest track (s)
  trackCdS:4,                 // cooldown between two tracking shots (s)
  // sky shot (camera.js, Daniel 2026-11-28): one fighter high + far -> over its shoulder looking down at the other
  skyOn:true,                 // on / off
  skyGapM:6,                  // starts when the height gap is at least this (m; one body = 1.8 m)
  skyDistM:10,                // ... and the two are at least this far apart (m)
  skyEndPct:75,               // ends once the gap or distance drops under this % of its start value ...
  skyEndMs:350,               // ... for this long (ms)
  skyBack:4,                  // metres behind the high fighter
  skyShoulder:1.3,            // metres to its side
  skySide:'right',            // over the right / left shoulder
  skyUp:1.1,                  // metres above its chest
  skyZoom:10,                 // % narrower view
  skyPull:6,                  // metres the camera pulls away mid-swing on the way in
  skyInMs:1400,               // the gradual pull away + orbit round to behind the high fighter
  skyOutMs:700,               // the glide back
  // knockback combos + lock-on (combo.js, Daniel 2026-11-26)
  comboOn:true,               // a fighter still stunned by a hit can be hit again: each hit redirects its flight
  comboChase:false,           // auto chase: a melee attacker snaps after the fighter it knocked back (off = snap yourself)
  comboChaseMs:120,           // auto chase: delay after the hit
  comboCap:6,                 // the hit that reaches this count still lands, then the target breaks free
  comboDecayPct:12,           // each hit already in the combo: this % less damage and stun
  comboBreakMs:400,           // break free: invulnerable until the stun ends + this
  comboReachPct:60,           // melee reach on a juggled target, % more
  comboLift:350,              // air juggle: upward speed each combo hit gives an airborne target (px/s, decays)
  lockTrack:false,            // locked on: the knockback tracking shot may still take the camera
  lockHomePx:900,             // locked on: attack keys snap in to the target from up to this far
  teams:[['blades','sueko','puck'],['ronin','tough','gunner']]
};
function loadSettings(){
  const out=JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
  try{const s=JSON.parse(localStorage.getItem(SETTINGS_KEY)||'{}');
    for(const k in out)if(s[k]!==undefined&&typeof s[k]===typeof out[k])out[k]=s[k];}catch(e){}
  return out;}
const settings=loadSettings();
function saveSettings(){try{localStorage.setItem(SETTINGS_KEY,JSON.stringify(settings));}catch(e){}}
