'use strict';
/* Fighter rigs and models: buildBody makes each character's toon / ink body (the shared .glb body from glbody.js when loaded, else a stand-in), accessories, weapon pivot, shadow, guard bubble and aura. */
function buildBody(k,key){const root=new THREE.Group();const g=new THREE.Group();root.add(g);
  if(useGlb(k))return finishBody(k,root,g,glbBuild(k,g));
  const mat=toon(k.col);
  const body=inked(new THREE.CylinderGeometry(.22,.3,.9,8),mat);body.position.y=.95;g.add(body);
  const head=inked(new THREE.SphereGeometry(.2,12,8),toon(0xf0d6c2));head.position.y=1.58;g.add(head);
  if(key==='blades'){const h=inked(new THREE.ConeGeometry(.27,.42,10),toon(k.acc));h.position.y=1.76;g.add(h);}
  if(key==='ronin'){const h=inked(new THREE.ConeGeometry(.52,.22,14),toon(k.acc));h.position.y=1.74;g.add(h);}
  if(key==='tough'){for(const x of[-.3,.3]){const s=inked(new THREE.BoxGeometry(.24,.2,.3),toon(k.acc));s.position.set(x,1.32,0);g.add(s);}}
  if(key==='gunner'){const v=inked(new THREE.BoxGeometry(.32,.08,.1),toon(0x9fe0ff));v.position.set(0,1.6,.17);g.add(v);}
  if(key==='sueko'){const hair=inked(new THREE.SphereGeometry(.22,10,8,0,TAU,0,Math.PI/2),toon(0x1a1a24));hair.position.y=1.62;g.add(hair);
    const belt=inked(new THREE.CylinderGeometry(.31,.31,.08,10),toon(k.acc));belt.position.y=.82;g.add(belt);}
  if(key==='puck'){for(let i=0;i<5;i++){const c=inked(new THREE.ConeGeometry(.09,.32,6),toon(0xffd84a));const a=i/5*TAU;c.position.set(Math.cos(a)*.1,1.8,Math.sin(a)*.1);c.rotation.set(Math.sin(a)*.6,0,-Math.cos(a)*.6);g.add(c);}
    const belt=inked(new THREE.CylinderGeometry(.31,.31,.08,10),toon(k.acc));belt.position.y=.82;g.add(belt);}
  const legs=[];for(const x of[-.11,.11]){const l=inked(new THREE.CylinderGeometry(.08,.07,.55,6),toon(0x1b1f33));l.position.set(x,.28,0);g.add(l);legs.push(l);}
  const wp=new THREE.Group();wp.position.set(.28,1.05,0);g.add(wp);
  const w=key==='sueko'?inked(new THREE.SphereGeometry(.13,8,6),toon(0xf0d6c2)):key==='gunner'?inked(new THREE.BoxGeometry(.1,.12,.5),toon(0x3a4466)):key==='tough'?inked(new THREE.SphereGeometry(.17,8,6),toon(k.acc)):new THREE.Mesh(new THREE.BoxGeometry(.04,.04,key==='ronin'?1.3:1.0),new THREE.MeshBasicMaterial({color:0xe8f4ff}));
  w.position.z=key==='gunner'?.25:(key==='tough'||key==='sueko')?.2:.5;wp.add(w);
  return finishBody(k,root,g,null,{mat,body,legs,wp});}
/* shadow, guard bubble, aura, altitude line: the same for stand-in and .glb bodies */
function finishBody(k,root,g,glb,parts){if(glb)parts={mat:glb.mat,body:glb.model,legs:[new THREE.Object3D(),new THREE.Object3D()],wp:new THREE.Group()};
  const sh=new THREE.Mesh(new THREE.CircleGeometry(.45,18),new THREE.MeshBasicMaterial({color:0,transparent:true,opacity:.42,depthWrite:false}));sh.rotation.x=-Math.PI/2;
  const guard=new THREE.Mesh(new THREE.SphereGeometry(.9,16,10),add(k.fx,.2));guard.position.y=1;guard.visible=false;g.add(guard);
  const aura=new THREE.Group();for(let i=0;i<7;i++){const c=new THREE.Mesh(new THREE.ConeGeometry(.16,.9,6,1,true),add(0xffd24a,.4));const a=i/7*TAU;c.position.set(Math.cos(a)*.34,1.05,Math.sin(a)*.34);aura.add(c);}aura.visible=false;g.add(aura);
  const aline=new THREE.Mesh(new THREE.CylinderGeometry(.025,.025,1,6),new THREE.MeshBasicMaterial({color:k.fx,transparent:true,opacity:.35,depthWrite:false}));scene.add(aline);
  scene.add(root);scene.add(sh);return {aline,g:root,pose:g,body:parts.body,legs:parts.legs,wp:parts.wp,sh,mat:parts.mat,guard,aura,glb};}
