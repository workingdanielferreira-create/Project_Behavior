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
  gravity:true,               // speed sets how high fighters may fly (gravity.js)
  teams:[['blades','sueko','puck'],['ronin','tough','gunner']]
};
function loadSettings(){
  const out=JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
  try{const s=JSON.parse(localStorage.getItem(SETTINGS_KEY)||'{}');
    for(const k in out)if(s[k]!==undefined&&typeof s[k]===typeof out[k])out[k]=s[k];}catch(e){}
  return out;}
const settings=loadSettings();
function saveSettings(){try{localStorage.setItem(SETTINGS_KEY,JSON.stringify(settings));}catch(e){}}
