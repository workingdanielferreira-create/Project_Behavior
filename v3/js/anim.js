'use strict';
/* Animation: per-frame sync of models to the sim (position, facing, lean, legs, swing, recoil, hit flash, shadows, aura, guard).
   A .glb body (f.glb) plays its rig clips instead of the stand-in lean / legs / swing (glbody.js glbAnim). */
/* ================= render sync ================= */
function sync(f,rdt){if(!f.on)return;const vis=!f.ko&&f.gone<=0;f.g.visible=vis||f.ko;const p=VA(f.x,f.y,f.z,f.h||0);
  if(f.jitT>0){f.jitT-=rdt;if(hitstopMs>0){p.x+=(Math.random()-.5)*.16;p.z+=(Math.random()-.5)*.16;}}
  const mvx=(f.x-f.lx),mvy=(f.y-f.ly);f.lx=f.x;f.ly=f.y;const spd=Math.min(1,Math.hypot(mvx,mvy)/12);f.lean+=(spd-f.lean)*Math.min(1,rdt*14);
  f.g.position.copy(p);if(f.ko&&!f.glb){f.pose.rotation.x=Math.max(-1.45,f.pose.rotation.x-rdt*5);}
  f.face3=Math.PI/2-f.face;f.g.rotation.y=f.face3;f.sh.position.set(f.g.position.x,.02,f.g.position.z);f.sh.visible=vis;{const hz=f.z*K;f.sh.scale.setScalar(Math.max(.35,1-hz*.035));f.sh.material.opacity=Math.max(.12,.42-hz*.012);f.aline.visible=vis&&hz>.8;if(f.aline.visible){f.aline.scale.y=hz;f.aline.position.set(f.g.position.x,hz/2,f.g.position.z);}}
  const mv=!f.act&&f.stun<=0&&f.lean>.15;const ph=f.stepT/.24*TAU;f.legs[0].rotation.x=mv?Math.sin(ph)*.6:0;f.legs[1].rotation.x=-f.legs[0].rotation.x;
  // swing: slow wind-up, then a snap through the hit frame and a held follow-through
  let sw=0,twist=0;if(f.act&&f.act.kind!=='react'){const d=f.act.def;const hitAt=(d.hits&&d.hits.length?d.hits[0][0]:d.fx.length?d.fx[0][0]:d.dur*.4)||60;const tms=f.act.t*TICK;const sg=(f.ni%2?1:-1);
    if(tms<hitAt){const u=tms/hitAt;sw=-1.5*u*u*sg;twist=-.35*u*sg;}else{const u=Math.min(1,(tms-hitAt)/60);sw=(-1.5+3.3*u)*sg;twist=.45*u*sg;}}
  f.wp.rotation.y+= (sw-f.wp.rotation.y)*Math.min(1,rdt*(Math.abs(sw)>1?60:20));
  f.recoil=Math.max(0,f.recoil-rdt*4);
  if(f.glb){f.pose.rotation.set(0,0,0);f.pose.position.y=0;glbAnim(f,rdt);}   // the .glb body's own clips do the posing
  else if(!f.ko){let rx=f.lean*.28-f.recoil*.55;if(f.antic>0)rx=.35;if(f.stun>0)rx=f.stunKind==='down'?-1:-.3-f.recoil*.4;f.pose.rotation.x+=(rx-f.pose.rotation.x)*Math.min(1,rdt*24);f.pose.rotation.y+=(twist-f.pose.rotation.y)*Math.min(1,rdt*30);
    f.pose.position.y=f.antic>0?-.1:0;}
  if(f.flashT>0){f.flashT-=rdt;f.mat.emissive.setHex(0xffffff);f.mat.emissiveIntensity=Math.max(0,f.flashT/.11);}else f.mat.emissive.setHex(f.form?0x3a2a00:0);
  if(f.aura.visible){f.aura.rotation.y+=rdt*6;f.aura.children.forEach((c,i)=>{c.scale.y=.8+Math.random()*.6;});}
  f.guard.visible=f.parry>0||f.block>0;if(f.guard.visible)f.guard.material.opacity=f.parry>0?.35:.22;}
