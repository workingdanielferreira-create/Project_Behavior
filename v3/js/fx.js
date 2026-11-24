'use strict';
/* FX design: the primitives every effect is built from (temp tween list, ghost, streak, slash, ring, dome, sparks, dust, star, crack, moons, portal / heaven blades). */
/* ================= fx ================= */
const fxs=[];
function temp(o,dur,upd){scene.add(o);fxs.push({o,t:0,dur,upd});}
function stepFx(dt){for(let i=fxs.length-1;i>=0;i--){const f=fxs[i];f.t+=dt;const u=Math.min(1,f.t/f.dur);f.upd(u,dt);if(u>=1){scene.remove(f.o);fxs.splice(i,1);f.done&&f.done();}}}
function fx_ghost(f,x,y){const m=new THREE.MeshBasicMaterial({color:f.k.fx,transparent:true,opacity:.5,depthWrite:false});const g=new THREE.Group();
  const b=new THREE.Mesh(new THREE.CylinderGeometry(.22,.3,1.3,8),m);b.position.y=.85;g.add(b);const h=new THREE.Mesh(new THREE.SphereGeometry(.2,8,6),m);h.position.y=1.58;g.add(h);
  g.position.copy(VA(x,y,f.gz!=null?f.gz:f.z));f.gz=null;g.rotation.y=f.face3;temp(g,.3,u=>{m.opacity=.5*(1-u);});}
function fx_streak(a,b,col,w){const d=new THREE.Vector3().subVectors(b,a);const len=d.length();if(len<.2)return;const m=new THREE.Mesh(new THREE.CylinderGeometry(w||.05,w||.05,1,6,1,true),add(col,.9));
  m.position.copy(a).addScaledVector(d,.5);m.scale.y=len;m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());temp(m,.22,u=>{m.material.opacity=.9*(1-u);m.scale.x=m.scale.z=1-u*.8;});}
function fx_slash(f,rBodies,col,big,dark){const mk=(c,o)=>dark?new THREE.MeshBasicMaterial({color:c,transparent:true,opacity:o,depthWrite:false,side:THREE.DoubleSide}):add(c,o);const r=rBodies*1.8*.5;const g=new THREE.Group();const p=V(f.x,f.y,1.05);g.position.copy(p);g.rotation.y=f.face3;const mid=new THREE.Group();const tilt=(Math.random()<.5?1:-1)*rnd(.15,.85);mid.rotation.z=tilt;g.add(mid);
  const ring=new THREE.Mesh(new THREE.RingGeometry(r*.6,r,40,1,-Math.PI/2-1.3,2.6),mk(col||f.k.fx,.95));ring.rotation.x=-Math.PI/2;mid.add(ring);
  const core=new THREE.Mesh(new THREE.RingGeometry(r*.94,r,40,1,-Math.PI/2-1.3,2.6),mk(dark?0x150a30:0xffffff,.95));core.rotation.x=-Math.PI/2;mid.add(core);
  temp(g,big?.3:.2,u=>{ring.material.opacity=.95*(1-u);core.material.opacity=.95*(1-u);mid.rotation.y=(tilt>0?1:-1)*u*.9;g.scale.setScalar(1+u*.25);});}
function fx_ring(x,y,col,r,dur,h){const m=new THREE.Mesh(new THREE.RingGeometry(.9,1,48),add(col,.9));m.rotation.x=-Math.PI/2;m.position.copy(V(x,y,h||.05));temp(m,dur||.3,u=>{const s=.2+u*r;m.scale.set(s,s,s);m.material.opacity=.9*(1-u);});}
function fx_dome(x,y,col,r){const m=new THREE.Mesh(new THREE.SphereGeometry(1,24,12,0,TAU,0,Math.PI/2),add(col,.35));m.position.copy(V(x,y));temp(m,.55,u=>{m.scale.setScalar(.3+u*r);m.material.opacity=.35*(1-u);});fx_ring(x,y,0xffffff,r*1.2,.5);}
function fx_sparks(x,y,col,n,sp,h){const N=Math.round(n),p=new Float32Array(N*3),v=[];const o=V(x,y,h||1.1);for(let k=0;k<N;k++){p[k*3]=o.x;p[k*3+1]=o.y;p[k*3+2]=o.z;v.push(new THREE.Vector3(Math.random()-.5,Math.random()*.8-.1,Math.random()-.5).normalize().multiplyScalar(sp*rnd(.4,1)));}
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(p,3));const m=new THREE.PointsMaterial({color:col,size:.2,transparent:true,blending:THREE.AdditiveBlending,depthWrite:false});
  let last=0;temp(new THREE.Points(g,m),.4,u=>{const dt=(u-last)*.4;last=u;const a=g.attributes.position.array;for(let k=0;k<N;k++){a[k*3]+=v[k].x*dt;a[k*3+1]+=v[k].y*dt;a[k*3+2]+=v[k].z*dt;v[k].y-=12*dt;}g.attributes.position.needsUpdate=true;m.opacity=1-u;});}
function fx_dust(x,y,n){for(let i=0;i<n;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(rnd(.25,.5),8,6),new THREE.MeshBasicMaterial({color:0x7a80a8,transparent:true,opacity:.3,depthWrite:false}));
  const a=rnd(0,TAU);const d=new THREE.Vector3(Math.cos(a),0,Math.sin(a));const p=V(x,y,.25);m.position.copy(p);const sp=rnd(1.5,4);
  temp(m,rnd(.4,.8),(u,dt)=>{m.position.addScaledVector(d,sp*dt);m.scale.setScalar(1+u*2);m.material.opacity=.3*(1-u);});}}
function fx_star(t,a,wv){const g=new THREE.Group();const n=6+wv*2;const mat=add(0xffffff,1);const mat2=add(a.k.fx,.9);
  for(let i=0;i<n;i++){const ang=i/n*TAU+rnd(-.2,.2);const len=rnd(.5,1)*(.5+wv*.32);const m=new THREE.Mesh(new THREE.PlaneGeometry(.06+wv*.015,len),i%2?mat:mat2);
    m.position.set(Math.cos(ang)*len*.5,Math.sin(ang)*len*.5,0);m.rotation.z=ang-Math.PI/2;g.add(m);}
  g.position.copy(V(t.x,t.y,1.15));g.quaternion.copy(cam.quaternion);temp(g,.13+wv*.03,u=>{g.scale.setScalar(.4+u*1.1);mat.opacity=1-u;mat2.opacity=.9*(1-u);});}
function fx_crack(x,y,wv){const g=new THREE.Group();const mat=new THREE.MeshBasicMaterial({color:0x05060c,transparent:true,opacity:.85,depthWrite:false});
  for(let i=0;i<5+wv;i++){const a=rnd(0,TAU),len=rnd(.6,1.4)*wv*.5;const m=new THREE.Mesh(new THREE.PlaneGeometry(.07,len),mat);m.rotation.x=-Math.PI/2;m.rotation.z=a;m.position.set(Math.sin(a)*len*.5*-1,0,Math.cos(a)*len*.5*-1);g.add(m);}
  const ring=new THREE.Mesh(new THREE.RingGeometry(.3*wv,.36*wv,20),mat);ring.rotation.x=-Math.PI/2;g.add(ring);
  g.position.copy(V(x,y,.03));temp(g,2.2,u=>{mat.opacity=.85*(u<.7?1:(1-u)/.3);});if(wv>=3)planetCrater(x,y,wv*.35);}
function fx_moons(f,n,r,out){const g=new THREE.Group();g.position.copy(V(f.x,f.y,1.1));for(let i=0;i<n;i++){const m=new THREE.Mesh(new THREE.RingGeometry(.28,.4,16,1,0,Math.PI*.9),add(i%2?0x6a3fd0:0xf4f8ff,.95));m.rotation.x=-Math.PI/2;const a=i/n*TAU;m.userData.a=a;g.add(m);}
  temp(g,out?.4:.3,u=>{g.children.forEach(m=>{const a=m.userData.a+u*(out?1:3.5);const rr=out?r*u:r*(.6+.4*u);m.position.set(Math.cos(a)*rr,0,Math.sin(a)*rr);m.rotation.z=a+u*8;m.material.opacity=.95*(1-u);});});}
function portalBlade(f,x,y,life,last){const e=enemyOf(f);const top=V(x,y,5.5),bot=V(x,y,.45);const ring=new THREE.Mesh(new THREE.RingGeometry(.5,.62,24),add(0x9a7aff,.9));ring.position.copy(top);ring.rotation.x=-Math.PI/2;temp(ring,.45,u=>{ring.material.opacity=.9*(1-u);ring.scale.setScalar(1+u);});
  const m=new THREE.Mesh(new THREE.BoxGeometry(.07,1.3,.07),new THREE.MeshBasicMaterial({color:0xe8f0ff}));const gl=new THREE.Mesh(new THREE.BoxGeometry(.2,1.4,.2),add(0x9fd0ff,.35));m.add(gl);m.position.copy(top);scene.add(m);
  const b={x,y,m,side:f.side,until:tick+ms2t(life),thrown:false};fx_tween(.26,u=>{m.position.lerpVectors(top,bot,u);},()=>{m.rotation.z=rnd(-.2,.2);fx_ring(x,y,0x9fd0ff,1.2,.2);if(!e.ko&&Math.hypot(e.x-x,e.y-y)<60)damage(f,e,1,'L');fieldBlades.push(b);if(last)shake=Math.max(shake,.4);});}
function fx_tween(dur,upd,done){fxs.push({o:new THREE.Group(),t:0,dur,upd:(u)=>upd(u),done});}
function throwHopBlade(f,b,last){const e=enemyOf(f);const i=fieldBlades.indexOf(b);if(i<0||!f.on||f.ko)return;fieldBlades.splice(i,1);
  const sx=b.x,sy=b.y,a=Math.atan2(e.y-sy,e.x-sx);const ex=e.x+Math.cos(a)*195,ey=e.y+Math.sin(a)*195;let hit=false;const m=b.m;
  fx_tween(.18,u=>{const x=sx+(ex-sx)*u,y=sy+(ey-sy)*u;m.position.copy(V(x,y,1.1));m.rotation.set(Math.PI/2,0,-a+Math.PI/2);if(!hit&&!e.ko&&Math.hypot(e.x-x,e.y-y)<70){hit=true;damage(f,e,15,'M',true);}},
    ()=>{fx_sparks(ex,ey,0x9fd0ff,14,6);fx_ring(ex,ey,0xe8f0ff,1.6,.2,1.1);scene.remove(m);
      if(!f.ko&&f.on){const ba=Math.atan2(f.y-e.y,f.x-e.x)+Math.PI;f.snapCd=0;f.gone=ms2t(40);snapTo(f,clamp(e.x+Math.cos(ba)*70,30,W-30),clamp(e.y+Math.sin(ba)*70,30,H-30),true);later(60,()=>{fx_slash(f,3.4,0xf4f8ff,true);if(last){const b2=Math.atan2(f.y-e.y,f.x-e.x);f.snapCd=0;snapTo(f,f.x+Math.cos(b2)*150,f.y+Math.sin(b2)*150,false,true);}});}});
  fx_streak(V(sx,sy,1.1),V(ex,ey,1.1),0x9fd0ff,.05);}
function heavenBlade(f,e){const x=e.x+rnd(-40,40),y=e.y+rnd(-40,40);const top=V(x,y,9),bot=V(x,y,.6);const ring=new THREE.Mesh(new THREE.RingGeometry(1.2,1.45,32),add(0xf4f8ff,.9));ring.position.copy(top);ring.rotation.x=-Math.PI/2;temp(ring,.4,u=>{ring.material.opacity=.9*(1-u);});
  const m=new THREE.Mesh(new THREE.BoxGeometry(.18,3.2,.18),new THREE.MeshBasicMaterial({color:0xffffff}));const gl=new THREE.Mesh(new THREE.BoxGeometry(.5,3.4,.5),add(0xbfe0ff,.4));m.add(gl);m.position.copy(top);scene.add(m);
  fx_tween(.22,u=>{m.position.lerpVectors(top,bot,u*u);},()=>{fx_ring(x,y,0xf4f8ff,3,.3);fx_ring(x,y,0x9fd0ff,4.5,.45);fx_dust(x,y,6);if(!e.ko&&Math.hypot(e.x-x,e.y-y)<80)damage(f,e,10,'M',true,null,40);later(2200,()=>scene.remove(m));});}
