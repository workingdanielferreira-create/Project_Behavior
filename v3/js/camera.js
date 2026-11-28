'use strict';
/* Camera: over the shoulder / dynamic cuts / wide, shake, punch-in, knockback tracking shot. */
/* ================= camera ================= */
const camPos=new THREE.Vector3(0,20,26),camLook=new THREE.Vector3();
cam.fov=56;cam.updateProjectionMatrix();
const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
let camMode='shoulder';const cut={t:0,kind:'shoulder',snap:false,hold:0};
function camEvent(kind,f,by){if(camMode==='cinematic'){cineEvent(kind,f,by);return;}if(camMode!=='dynamic'||kind==='heavy')return;const now=performance.now()/1000;if(now<cut.hold)return;
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
function camKnock(f,dvx,dvy){if(!settings.trackOn||lockBlocksTrack()||!running||ended||(camMode!=='shoulder'&&camMode!=='dynamic'&&camMode!=='cinematic'))return;
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
  track.fov=BASE_FOV*(1-settings.trackZoom/100);
  if(settings.trackGolden){if(PLANET){goldenLook(bendP(track.p),bendP(fp),track.fov,track.l);track.l.copy(unbendP(track.l));}   // frame in drawn (curved) space
    else goldenLook(track.p,fp,track.fov,track.l);}
  else{track.l.copy(fp).addScaledVector(track.dir,1.6);track.l.y=fp.y+.15;}}
/* Golden-ratio framing (Daniel 2026-11-24): aim from p so the point fp lands on the top-right crossing of the phi grid
   (x = 61.8 % across, y = 38.2 % down = NDC (0.236, 0.236)) with view fov / the camera's aspect. Writes the look point. */
const _gc=new THREE.PerspectiveCamera(),_gf=new THREE.Vector3(),PHI_NDC=2/1.6180339887-1;
function goldenLook(p,fp,fov,out){_gc.position.copy(p);_gc.up.set(0,1,0);_gc.lookAt(fp);
  const tv=Math.tan(fov*Math.PI/360),th=tv*cam.aspect;
  _gc.rotateY(Math.atan(PHI_NDC*th));_gc.rotateX(-Math.atan(PHI_NDC*tv));   // turn left / tilt down: the fighter moves right / up in frame
  _gf.set(0,0,-1).applyQuaternion(_gc.quaternion);out.copy(p).addScaledVector(_gf,Math.max(1,p.distanceTo(fp)));}
// seconds until the knockback is over: fall to the ground (stunned gravity), then the ground slide down to 220 px/s
function trackLeft(f){const g=JUMP.gravity;let t=0,s=Math.hypot(f.vx,f.vy);
  if(f.z>1){const tl=(f.vz+Math.sqrt(Math.max(0,f.vz*f.vz+2*g*f.z)))/g;t+=tl;s*=Math.exp(-GRAV.airFric*tl);}
  if(s>220)t+=Math.log(s/220)/GRAV.groundFric;return t;}
const ease=u=>u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;
// returns true while the shot owns the camera (camStep then skips its own placement)
function trackStep(rdt){if(!track.ph)return false;const f=track.f;track.t+=rdt*1000;
  const gone=!f||!f.on||(camMode!=='shoulder'&&camMode!=='dynamic'&&camMode!=='cinematic')||!settings.trackOn||lockBlocksTrack();
  if(gone&&track.ph<3){track.ph=3;track.t=0;track.frozen=true;track.f0=cam.fov;}
  if(!track.frozen&&f&&f.on)trackPose(rdt);   // live chase pose in every phase (the glide back leaves from it, no freeze)
  if(track.ph===1){const u=ease(Math.min(1,track.t/Math.max(1,settings.trackInMs)));
    cam.position.lerpVectors(track.p0,track.p,u);camLookT.lerpVectors(track.l0,track.l,u);cam.fov=track.f0+(track.fov-track.f0)*u;
    if(u>=1){track.ph=2;track.t=0;}}
  else if(track.ph===2){cam.position.copy(track.p);camLookT.copy(track.l);cam.fov=track.fov;
    // ease out JUST BEFORE the knockback ends (trackLeadMs ahead of the predicted stop), or at the longest track
    if(trackLeft(f)*1000<=settings.trackLeadMs||track.t>settings.trackMaxS*1000){track.ph=3;track.t=0;track.f0=cam.fov;}}
  if(track.ph===3){const u=ease(Math.min(1,track.t/Math.max(1,settings.trackOutMs)));
    cam.position.lerpVectors(track.p,camPos,u);camLookT.lerpVectors(track.l,camLook,u);cam.fov=track.f0+(camBaseFov-track.f0)*u;
    if(u>=1){track.ph=0;track.f=null;track.frozen=false;cam.fov=camBaseFov;track.next=performance.now()/1000+settings.trackCdS;}}
  cam.updateProjectionMatrix();return true;}
const camLookT=new THREE.Vector3();
let camBaseFov=BASE_FOV;   // the fov the shot underneath wants (cinecam.js sets it in the Cinematic mode); the tracking shot glides back to it
function trackReset(){track.ph=0;track.f=null;track.frozen=false;track.next=0;skyReset();cam.fov=BASE_FOV;cam.updateProjectionMatrix();}
/* Sky shot (Daniel 2026-11-28): one fighter high in the sky AND far from the other -> over the HIGH fighter's shoulder,
   looking down at the lower one. Over the shoulder, Dynamic and Cinematic; owns the camera over everything (tracking
   shot, lock-on, cinematic event shots keep running underneath for the glide back). Entry = a gradual pull away that
   orbits round the high fighter (the short way, up to 180 deg) and ends behind it; exit = a glide back to the shot
   underneath. Starts when the height gap >= skyGapM and the distance >= skyDistM; ends once either drops under
   skyEndPct % of its start value for skyEndMs (no flicker on a bobbing jump). View only: never touches the sim. */
const sky={ph:0,t:0,hi:null,lo:null,off:0,a0:0,r0:0,y0:0,da:0,p0:new THREE.Vector3(),l0:new THREE.Vector3(),f0:56,
  h:new THREE.Vector3(0,0,-1),p:new THREE.Vector3(),l:new THREE.Vector3(),fov:56};
function skyReset(){sky.ph=0;sky.t=0;sky.hi=sky.lo=null;sky.off=0;}
function skyModeOk(){return settings.skyOn&&(camMode==='shoulder'||camMode==='dynamic'||camMode==='cinematic');}
// the finished pose: behind the high fighter (away from the low one), skyShoulder to its right, skyUp above, looking at the low one
// drawn (globe-bent) space <-> flat: the pose is worked out where it is SEEN (high up, the bend stretches sideways offsets ~ (R+h)/R)
const skyBd=q=>PLANET?bendP(q):q.clone(),skyUb=q=>PLANET?unbendP(q):q.clone();
function skyPose(rdt){const A=skyBd(VA(sky.hi.x,sky.hi.y,sky.hi.z,1.2)),B=skyBd(VA(sky.lo.x,sky.lo.y,sky.lo.z,1.2));
  const hx=B.x-A.x,hz=B.z-A.z,hl=Math.hypot(hx,hz);
  if(hl>1){const k=rdt>0?1-Math.exp(-5*rdt):1;sky.h.x+=(hx/hl-sky.h.x)*k;sky.h.z+=(hz/hl-sky.h.z)*k;sky.h.y=0;sky.h.normalize();}   // straight above: keep the last line
  // Fix (Daniel 2026-11-28, "the character ends up past the camera"): the camera sat behind A on the FLAT plane at A's
  // height, so looking steeply down at B pushed A out above / behind the frame. Now it sits on the 3D line B -> A,
  // past A: A is always between the camera and B; shoulder / up offsets are across that line.
  const d=new THREE.Vector3().subVectors(B,A);if(d.lengthSq()<1e-6)d.copy(sky.h);d.normalize();   // view direction (camera -> B)
  const W=new THREE.Vector3(0,1,0),up=W.clone().addScaledVector(d,-d.dot(W));
  if(up.lengthSq()<.04)up.copy(sky.h).multiplyScalar(-1).addScaledVector(d,-d.dot(sky.h)*-1);   // looking straight down: screen up = away from the line
  up.normalize();const right=new THREE.Vector3().crossVectors(d,up).normalize(),sd=settings.skySide==='left'?-1:1;
  sky.p.copy(A).addScaledVector(d,-settings.skyBack).addScaledVector(right,sd*settings.skyShoulder).addScaledVector(up,settings.skyUp);
  sky.p.copy(skyUb(sky.p));sky.l.copy(skyUb(B.addScaledVector(up,.4)));
  sky.fov=BASE_FOV*(1-settings.skyZoom/100);}
// keep the high fighter in the frame: if the aim from cam.position puts A further off than 75 % of the half view,
// turn the aim toward A just enough
const _sA=new THREE.Vector3(),_sL=new THREE.Vector3();
function skyKeep(fov){if(!sky.hi)return;const c=skyBd(cam.position),A=skyBd(VA(sky.hi.x,sky.hi.y,sky.hi.z,1.2)),L=skyBd(camLookT);
  _sA.subVectors(A,c);const dA=_sA.length();if(dA<.3)return;_sA.divideScalar(dA);
  _sL.subVectors(L,c);const dL=_sL.length();if(dL<1e-3)return;_sL.divideScalar(dL);
  const lim=.75*Math.atan(Math.tan(fov*Math.PI/360)*Math.min(1,cam.aspect||1)),ang=Math.acos(Math.max(-1,Math.min(1,_sA.dot(_sL))));
  if(ang<=lim)return;const t=(ang-lim)/ang;_sL.lerp(_sA,t).normalize();camLookT.copy(skyUb(c.addScaledVector(_sL,dL)));}
// is the gap wide enough? (m) -> [height gap, distance, high fighter, low fighter]
function skyGap(a,b){if(!a||!b||a===b||!a.on||!b.on||a.phantom||b.phantom)return null;
  const hi=a.z>=b.z?a:b,lo=hi===a?b:a,pa=VA(a.x,a.y,a.z,0),pb=VA(b.x,b.y,b.z,0);return [Math.abs(a.z-b.z)*K,pa.distanceTo(pb),hi,lo];}
// runs after the normal shot / tracking shot placed cam.position + camLookT; under = the fov the shot underneath wants.
// Returns true while the sky shot owns the camera.
function skyStep(rdt,a,b,under){const g=skyGap(a,b);sky.t+=rdt*1000;
  const ok=skyModeOk()&&running&&!ended;
  if(!sky.ph){if(!ok||!g||g[0]<settings.skyGapM||g[1]<settings.skyDistM)return false;
    sky.ph=1;sky.t=0;sky.off=0;sky.hi=g[2];sky.lo=g[3];sky.p0.copy(cam.position);sky.l0.copy(camLookT);sky.f0=cam.fov;
    const A=VA(sky.hi.x,sky.hi.y,sky.hi.z,1.2);sky.h.set(sky.lo.x-sky.hi.x,0,sky.lo.y-sky.hi.y);if(sky.h.lengthSq()<1e-6)sky.h.set(Math.cos(sky.hi.face),0,Math.sin(sky.hi.face));sky.h.normalize();
    const dx=sky.p0.x-A.x,dz=sky.p0.z-A.z;sky.a0=Math.atan2(dz,dx);sky.r0=Math.max(.5,Math.hypot(dx,dz));sky.y0=sky.p0.y-A.y;}
  // still the same pair? (a tag-in / K.O. swaps who is on the field) -> glide back
  const same=g&&((g[2]===sky.hi&&g[3]===sky.lo)||(g[2]===sky.lo&&g[3]===sky.hi));
  if(sky.ph<3){const k=settings.skyEndPct/100;
    if(!ok||!same)sky.off=1e9;else if(g[0]<settings.skyGapM*k||g[1]<settings.skyDistM*k)sky.off+=rdt*1000;else sky.off=0;
    if(sky.off>=settings.skyEndMs){sky.ph=3;sky.t=0;sky.f0=cam.fov;}}
  if(sky.ph<3||same)skyPose(rdt);   // live pose (the glide back leaves from it)
  if(sky.ph===1){const u=Math.min(1,sky.t/Math.max(1,settings.skyInMs)),e=ease(u);
    // orbit round the high fighter: bearing from where the camera was to behind it (short way), pulling away mid-swing
    const A=VA(sky.hi.x,sky.hi.y,sky.hi.z,1.2),a1=Math.atan2(sky.p.z-A.z,sky.p.x-A.x),r1=Math.hypot(sky.p.x-A.x,sky.p.z-A.z);
    let da=((a1-sky.a0+Math.PI)%TAU+TAU)%TAU-Math.PI;const ang=sky.a0+da*e,pull=settings.skyPull*Math.sin(Math.PI*e);
    const r=sky.r0+(r1-sky.r0)*e+pull;
    cam.position.set(A.x+Math.cos(ang)*r,A.y+sky.y0+(sky.p.y-A.y-sky.y0)*e+pull*.35,A.z+Math.sin(ang)*r);
    camLookT.lerpVectors(sky.l0,sky.l,e);cam.fov=sky.f0+(sky.fov-sky.f0)*e;skyKeep(cam.fov);if(u>=1){sky.ph=2;sky.t=0;}}
  else if(sky.ph===2){cam.position.copy(sky.p);camLookT.copy(sky.l);cam.fov=sky.fov;skyKeep(cam.fov);}
  else if(sky.ph===3){const u=Math.min(1,sky.t/Math.max(1,settings.skyOutMs)),e=ease(u);
    cam.position.lerpVectors(sky.p,cam.position,e);camLookT.lerpVectors(sky.l,camLookT,e);cam.fov=sky.f0+(under-sky.f0)*e;
    if(u>=1){skyReset();cam.fov=under;}}
  if(cam.position.y<.4)cam.position.y=.4;
  cam.updateProjectionMatrix();return !!sky.ph;}
function camStep(rdt,idle){sightFrame++;
  if(idle){sightClear();cineReset();skyReset();camBaseFov=BASE_FOV;if(cam.fov!==BASE_FOV){cam.fov=BASE_FOV;cam.updateProjectionMatrix();}cam.up.set(0,1,0);
    if(PLANET&&world){planetIdleCam();return;}const t=performance.now()/1000*.1;cam.position.set(Math.sin(t)*40,24,Math.cos(t)*40);cam.lookAt(0,6,0);return;}
  const [a,b]=onField();const pa=VA(a.x,a.y,a.z,1.2),pb=VA(b.x,b.y,b.z,1.2);const sep=pa.distanceTo(pb);
  // Cinematic (cinecam.js, Daniel 2026-11-26): its own director + spring rig write camPos / camLook; lock-on still wins
  const cineOn=camMode==='cinematic'&&!lockTarget();
  if(cineOn){cineStep(rdt,a,b,pa,pb,sep);}else{cineReset();camBaseFov=BASE_FOV;
  let mode=camMode;const now=performance.now()/1000;
  if(camMode==='dynamic'&&!lockTarget()){if(now>cut.t){const r=Math.random();cut.kind=sep>28?(r<.6?'side':'wide'):(r<.45?'shoulder':r<.7?'side':r<.85?'reverse':'low');cut.t=now+rnd(2.4,4.8);cut.snap=true;}mode=cut.kind;}
  mode=lockCamMode(mode);   // combo.js: locked on = the over-the-shoulder shot on the target
  let [tgt,look]=camShot(mode,pa,pb,sep);if(tgt.y<.4)tgt.y=.4;
  const snap=(PLANET&&planetWrapped)||(cut.snap&&!track.ph);
  tgt=sightAdjust(tgt,look,rdt,snap);   // cinecam.js: swing / rise / pull in to a clear line past trees, pillars, landmarks
  if(PLANET&&planetWrapped){planetWrapped=false;camPos.copy(tgt);camLook.copy(look);}   // a fighter came round the globe: re-frame at once
  if(cut.snap&&!track.ph){camPos.copy(tgt);camLook.copy(look);cut.snap=false;}
  else{camPos.lerp(tgt,1-Math.exp(-(mode==='wide'?3:5.5)*rdt));camLook.lerp(look,1-Math.exp(-9*rdt));}}
  // the knockback tracking shot owns the camera while it runs (the normal shot keeps updating underneath, for the glide back)
  const tracked=trackStep(rdt);if(!tracked){cam.position.copy(camPos);camLookT.copy(camLook);}
  // the sky shot owns the camera over everything (Daniel 2026-11-28)
  const skyed=skyStep(rdt,a,b,tracked?cam.fov:cineOn?camBaseFov:BASE_FOV);
  if(!reduce&&shake>0){const j=(Math.random()-.5);cam.position.x+=shakeDir[0]*j*shake*.9+(Math.random()-.5)*shake*.3;cam.position.z+=shakeDir[1]*j*shake*.9;cam.position.y+=(Math.random()-.5)*shake*.35;}
  if(camPunch>0){cam.position.lerp(camLookT,camPunch);camPunch=Math.max(0,camPunch-rdt*.6);}
  cam.up.set(0,1,0);cam.lookAt(camLookT);if(PLANET)planetCam(camLookT);
  if(!track.ph&&!skyed){if(cineOn)cineFinish(rdt,sep);else if(cam.fov!==BASE_FOV){cam.fov=BASE_FOV;cam.updateProjectionMatrix();}}
  sightFade(rdt);   // cinecam.js: anything still between the camera and the fighters dithers out; X-ray gate
  shake=Math.max(0,shake-rdt*3.2);}
