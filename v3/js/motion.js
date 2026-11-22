'use strict';
/* Motion: drift & snap (fast dashes and blinks between planted stances). */
/* ---- snaps (drift & snap motion) ---- */
function snapTo(f,tx,ty,blink,quick,tz){if(f.snapCd>tick||f.stun>0)return false;tx=clamp(tx,30,W-30);ty=clamp(ty,30,H-30);tz=clamp(tz==null?(f.zWant!=null?f.zWant:f.z):tz,0,ZMAX);
  const d=Math.hypot(tx-f.x,ty-f.y,tz-f.z);if(d<30)return false;
  f.snap={tx,ty,tz,v:blink?0:rnd(2800,3900)*(f.spdMul||1),blink,sx:f.x,sy:f.y,sz:f.z};if(!blink&&!quick)f.antic=ms2t(45);f.snapCd=tick+ms2t(blink?220:160);stats.snaps[f.side]++;metr.snaps.push([tick,f.side]);
  if(blink){f.gone=ms2t(rnd(50,90));fx_ring(f.x,f.y,f.k.fx,2.4,.25,1);fx_sparks(f.x,f.y,f.k.fx,10,5);}
  return true;}
function stepSnap(f){const s=f.snap;if(!s)return;
  if(s.blink){if(f.gone<=1){fx_streak(VA(s.sx,s.sy,s.sz,1),VA(s.tx,s.ty,s.tz,1),f.k.fx,.04);f.x=s.tx;f.y=s.ty;f.z=s.tz;f.vz=0;fx_ring(f.x,f.y,0xffffff,2.6,.25,1);fx_sparks(f.x,f.y,f.k.core,12,6);f.snap=null;}return;}
  if(f.antic>0){f.antic--;return;}
  const dx=s.tx-f.x,dy=s.ty-f.y,dz=s.tz-f.z,d=Math.hypot(dx,dy,dz),st=s.v*DT;
  const px=f.x,py=f.y,pz=f.z;if(d<=st){f.x=s.tx;f.y=s.ty;f.z=s.tz;f.vz=0;f.snap=null;if(d>1){f.vx+=dx/d*260;f.vy+=dy/d*260;}if(f.z<10)fx_dust(f.x,f.y,3);}else{f.x+=dx/d*st;f.y+=dy/d*st;f.z+=dz/d*st;}
  f.gz=pz;fx_ghost(f,px,py);if(Math.random()<.5)fx_streak(VA(px,py,pz,1),VA(f.x,f.y,f.z,1),f.k.fx,.03);}
