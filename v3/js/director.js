'use strict';
/* Director: one heat value for the fight, calm -> build -> burst. */
/* ================= director (port) ================= */
function stepDirector(){const D=director;const pair=onField();const ref=(pair[0].max+pair[1].max)/2;let add=0;
  add+=D.hits*.03+D.dmg/ref*.6+D.cnt*.05+D.taken/ref*.5+D.ko*.45;D.hits=D.dmg=D.cnt=D.taken=D.ko=0;
  const dm=Math.hypot(pair[0].x-pair[1].x,pair[0].y-pair[1].y);add+=Math.max(0,1-dm/260)*.10*DT;
  if(pair.some(f=>f.hp/f.max<=.3))add+=.06*DT;
  if(D.lastHitTick===tick)D.quiet=0;else D.quiet++;if(D.quiet*DT>=2.5)add+=.05*DT;
  if(D.phase==='burst'){D.left--;D.I=Math.min(1,D.I+add*.25);if(D.left<=0){D.I=.08;D.phase='calm';D.at=.8*(1+rnd(-.12,.12));}}
  else{D.I=clamp(D.I+add-.12*DT,0,1);if(D.I>=D.at){D.phase='burst';D.left=ms2t(rnd(2500,4500));callout('BURST','Director: everything speeds up','#ffc857',.8);}else D.phase=D.I>=.35?'build':'calm';}}
