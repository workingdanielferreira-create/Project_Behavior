'use strict';
/* Camera: over the shoulder / dynamic cuts / wide, shake, punch-in. */
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
function camStep(rdt,idle){if(idle){if(PLANET&&world){planetIdleCam();return;}const t=performance.now()/1000*.1;cam.position.set(Math.sin(t)*40,24,Math.cos(t)*40);cam.lookAt(0,6,0);return;}
  const [a,b]=onField();const pa=VA(a.x,a.y,a.z,1.2),pb=VA(b.x,b.y,b.z,1.2);const sep=pa.distanceTo(pb);
  let mode=camMode;const now=performance.now()/1000;
  if(camMode==='dynamic'){if(now>cut.t){const r=Math.random();cut.kind=sep>28?(r<.6?'side':'wide'):(r<.45?'shoulder':r<.7?'side':r<.85?'reverse':'low');cut.t=now+rnd(2.4,4.8);cut.snap=true;}mode=cut.kind;}
  const [tgt,look]=camShot(mode,pa,pb,sep);if(tgt.y<.4)tgt.y=.4;
  if(cut.snap){camPos.copy(tgt);camLook.copy(look);cut.snap=false;}
  else{camPos.lerp(tgt,1-Math.exp(-(mode==='wide'?3:5.5)*rdt));camLook.lerp(look,1-Math.exp(-9*rdt));}
  cam.position.copy(camPos);if(!reduce&&shake>0){const j=(Math.random()-.5);cam.position.x+=shakeDir[0]*j*shake*.9+(Math.random()-.5)*shake*.3;cam.position.z+=shakeDir[1]*j*shake*.9;cam.position.y+=(Math.random()-.5)*shake*.35;}
  if(camPunch>0){cam.position.lerp(camLook,camPunch);camPunch=Math.max(0,camPunch-rdt*.6);}
  cam.lookAt(camLook);if(PLANET)planetCam(camLook);shake=Math.max(0,shake-rdt*3.2);}
