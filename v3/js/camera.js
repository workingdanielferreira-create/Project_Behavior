'use strict';
/* Camera: over the shoulder / dynamic cuts / wide, shake, punch-in, knockback tracking shot. */
/* ================= camera ================= */
const camPos=new THREE.Vector3(0,20,26),camLook=new THREE.Vector3();
cam.fov=56;cam.updateProjectionMatrix();
const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
let camMode='shoulder';const cut={t:0,kind:'shoulder',snap:false,hold:0};
function camEvent(kind){if(camMode!=='dynamic')return;const now=performance.now()/1000;if(now<cut.hold)return;
  cut.kind=kind==='ult'?(Math.random()<.5?'low':'side'):kind==='launch'?'side':kind==='ko'?'side':cut.kind;cut.t=now+rnd(1.6,2.6);cut.hold=now+.9;cut.snap=true;}
function camShot(mode,pa,pb,sep){const dir=new THREE.Vector3().subVectors(pb,pa);dir.y*=.35;if(dir.lengthSq()<1e-4)dir.set(0,0,-1);dir.normalize();const right=new THREE.Vector3(-dir.z,0,dir.x).normalize();
  if(mode==='shoulder'||mode==='reverse'){const A=mode==='shoulder'?pa:pb,B=mode==='shoulder'?pb:pa,dd=mode==='shoulder'?dir:dir.clone().negate();const r2=mode==='shoulder'?right:right.clone().negate();
    const back=3.6+sep*.24;const t=A.clone().addScaledVector(dd,-back).addScaledVector(r2,1.25+sep*.05);t.y=A.y+.9+sep*.1;return [t,A.clone().lerp(B,.6).add(new THREE.Vector3(0,.35,0))];}
  if(mode==='side'){const m=pa.clone().lerp(pb,.5);const t=m.clone().addScaledVector(right,5.5+sep*.75);t.y=m.y+1.2+sep*.12;return [t,m];}
  if(mode==='low'){const t=pa.clone().addScaledVector(dir,-2.6).addScaledVector(right,1.9);t.y=Math.max(.35,pa.y-1.3);return [t,pb.clone().add(new THREE.Vector3(0,.8,0))];}
  const m=pa.clone().lerp(pb,.5);const t=m.clone().add(new THREE.Vector3(0,13+sep*.35,19+sep*.4));return [t,m];}
/* Knockback tracking shot (Daniel 2026-11-24; over the shoulder + dynamic, either on-field fighter):
   a single hit that will carry a fighter at least settings.trackMinPx -> ONE continuous move: the camera swoops from
   where it is to just behind the flying fighter, facing the way it travels, and zooms in (fov); then it rides rigidly
   with it (same speed, the fighter stays in frame) until it lands and stops sliding (or trackMaxS), then glides back
   to the normal shot. View only: never touches the sim. Cooldown trackCdS between two shots. */
const track={f:null,ph:0,side:1,frozen:false,t:0,p0:new THREE.Vector3(),l0:new THREE.Vector3(),f0:56,dir:new THREE.Vector3(0,0,-1),p:new THREE.Vector3(),l:new THREE.Vector3(),fov:56,next:0};
const BASE_FOV=56;
// combat.js damage(): the knockback this hit added (px/s). Predicts the carry (speed / slide friction) and starts the shot.
function camKnock(f,dvx,dvy){if(!settings.trackOn||!running||ended||(camMode!=='shoulder'&&camMode!=='dynamic'))return;
  const [a,b]=onField();if((f!==a&&f!==b)||f.phantom||!f.on)return;
  const s=Math.hypot(dvx,dvy),air=f.vz>0||f.z>25,carry=s/(air?GRAV.airFric:GRAV.groundFric);if(carry<settings.trackMinPx)return;
  const now=performance.now()/1000;
  if(track.f===f&&(track.ph===1||track.ph===2)){if(track.ph===2)track.t=0;return;}   // hit again while tracked: keep riding
  if(track.ph||now<track.next)return;
  track.f=f;track.ph=1;track.t=0;track.p0.copy(camPos);track.l0.copy(camLook);track.f0=cam.fov;
  track.dir.set(f.vx,0,f.vy);if(track.dir.lengthSq()<1e-6)track.dir.set(dvx,0,dvy);track.dir.normalize();
  // 3/4 side (Daniel 2026-11-24: "the right quarter"): settings.trackSide, right of the flight line by default
  track.side=settings.trackSide==='left'?1:-1;}
// the chase pose: behind the fighter along its travel, swung trackAngle deg to its right (side -1) or left (+1) (3/4 view, Daniel 2026-11-24:
// a thrown fighter flies backwards, so straight behind its travel = full face), looking the way it moves
function trackPose(rdt){const f=track.f;const fp=VA(f.x,f.y,f.z,1);const h=Math.hypot(f.vx,f.vy);
  if(h>60){const d=new THREE.Vector3(f.vx,0,f.vy).normalize();track.dir.lerp(d,1-Math.exp(-6*rdt)).normalize();}
  const th=settings.trackAngle*Math.PI/180*(track.side||1),bx=-track.dir.x,bz=-track.dir.z,c=Math.cos(th),sn=Math.sin(th);
  const ox=bx*c-bz*sn,oz=bx*sn+bz*c;   // the back direction turned round the fighter
  track.p.set(fp.x+ox*settings.trackDist,fp.y+settings.trackHeight,fp.z+oz*settings.trackDist);if(track.p.y<.4)track.p.y=.4;
  track.l.copy(fp).addScaledVector(track.dir,1.6);track.l.y=fp.y+.15;
  track.fov=BASE_FOV*(1-settings.trackZoom/100);}
// seconds until the knockback is over: fall to the ground (stunned gravity), then the ground slide down to 220 px/s
function trackLeft(f){const g=JUMP.gravity;let t=0,s=Math.hypot(f.vx,f.vy);
  if(f.z>1){const tl=(f.vz+Math.sqrt(Math.max(0,f.vz*f.vz+2*g*f.z)))/g;t+=tl;s*=Math.exp(-GRAV.airFric*tl);}
  if(s>220)t+=Math.log(s/220)/GRAV.groundFric;return t;}
const ease=u=>u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;
// returns true while the shot owns the camera (camStep then skips its own placement)
function trackStep(rdt){if(!track.ph)return false;const f=track.f;track.t+=rdt*1000;
  const gone=!f||!f.on||(camMode!=='shoulder'&&camMode!=='dynamic')||!settings.trackOn;
  if(gone&&track.ph<3){track.ph=3;track.t=0;track.frozen=true;track.f0=cam.fov;}
  if(!track.frozen&&f&&f.on)trackPose(rdt);   // live chase pose in every phase (the glide back leaves from it, no freeze)
  if(track.ph===1){const u=ease(Math.min(1,track.t/Math.max(1,settings.trackInMs)));
    cam.position.lerpVectors(track.p0,track.p,u);camLookT.lerpVectors(track.l0,track.l,u);cam.fov=track.f0+(track.fov-track.f0)*u;
    if(u>=1){track.ph=2;track.t=0;}}
  else if(track.ph===2){cam.position.copy(track.p);camLookT.copy(track.l);cam.fov=track.fov;
    // ease out JUST BEFORE the knockback ends (trackLeadMs ahead of the predicted stop), or at the longest track
    if(trackLeft(f)*1000<=settings.trackLeadMs||track.t>settings.trackMaxS*1000){track.ph=3;track.t=0;track.f0=cam.fov;}}
  if(track.ph===3){const u=ease(Math.min(1,track.t/Math.max(1,settings.trackOutMs)));
    cam.position.lerpVectors(track.p,camPos,u);camLookT.lerpVectors(track.l,camLook,u);cam.fov=track.f0+(BASE_FOV-track.f0)*u;
    if(u>=1){track.ph=0;track.f=null;track.frozen=false;cam.fov=BASE_FOV;track.next=performance.now()/1000+settings.trackCdS;}}
  cam.updateProjectionMatrix();return true;}
const camLookT=new THREE.Vector3();
function trackReset(){track.ph=0;track.f=null;track.frozen=false;track.next=0;cam.fov=BASE_FOV;cam.updateProjectionMatrix();}
function camStep(rdt,idle){if(idle){if(PLANET&&world){planetIdleCam();return;}const t=performance.now()/1000*.1;cam.position.set(Math.sin(t)*40,24,Math.cos(t)*40);cam.lookAt(0,6,0);return;}
  const [a,b]=onField();const pa=VA(a.x,a.y,a.z,1.2),pb=VA(b.x,b.y,b.z,1.2);const sep=pa.distanceTo(pb);
  let mode=camMode;const now=performance.now()/1000;
  if(camMode==='dynamic'){if(now>cut.t){const r=Math.random();cut.kind=sep>28?(r<.6?'side':'wide'):(r<.45?'shoulder':r<.7?'side':r<.85?'reverse':'low');cut.t=now+rnd(2.4,4.8);cut.snap=true;}mode=cut.kind;}
  const [tgt,look]=camShot(mode,pa,pb,sep);if(tgt.y<.4)tgt.y=.4;
  if(PLANET&&planetWrapped){planetWrapped=false;camPos.copy(tgt);camLook.copy(look);}   // a fighter came round the globe: re-frame at once
  if(cut.snap&&!track.ph){camPos.copy(tgt);camLook.copy(look);cut.snap=false;}
  else{camPos.lerp(tgt,1-Math.exp(-(mode==='wide'?3:5.5)*rdt));camLook.lerp(look,1-Math.exp(-9*rdt));}
  // the knockback tracking shot owns the camera while it runs (the normal shot keeps updating underneath, for the glide back)
  if(trackStep(rdt)){}else{cam.position.copy(camPos);camLookT.copy(camLook);}if(!reduce&&shake>0){const j=(Math.random()-.5);cam.position.x+=shakeDir[0]*j*shake*.9+(Math.random()-.5)*shake*.3;cam.position.z+=shakeDir[1]*j*shake*.9;cam.position.y+=(Math.random()-.5)*shake*.35;}
  if(camPunch>0){cam.position.lerp(camLookT,camPunch);camPunch=Math.max(0,camPunch-rdt*.6);}
  cam.lookAt(camLookT);if(PLANET)planetCam(camLookT);shake=Math.max(0,shake-rdt*3.2);}
