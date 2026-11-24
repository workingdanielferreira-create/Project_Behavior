'use strict';
/* ================= settings =================
   Everything the Settings / Teams screens change, kept between sessions in
   localStorage (the app window has its own profile, see run_v3.bat). If
   storage is blocked the game still runs on the defaults. */
const SETTINGS_KEY='pb3.settings.v1';
const DEFAULT_SETTINGS={
  level:'commander',          // watch | commander | handson
  pace:100,                   // game speed %, 25..100
  cam:'shoulder',             // shoulder | dynamic | wide
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
  teams:[['blades','sueko','puck'],['ronin','tough','gunner']]
};
function loadSettings(){
  const out=JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
  try{const s=JSON.parse(localStorage.getItem(SETTINGS_KEY)||'{}');
    for(const k in out)if(s[k]!==undefined&&typeof s[k]===typeof out[k])out[k]=s[k];}catch(e){}
  return out;}
const settings=loadSettings();
function saveSettings(){try{localStorage.setItem(SETTINGS_KEY,JSON.stringify(settings));}catch(e){}}
