'use strict';
/* Arena: floor, sky dome, floating rocks, outer pillars, clouds, grid, rim stones, stars. */
// ground
const floor=new THREE.Mesh(new THREE.PlaneGeometry(400,300),toon(0x0f1430));floor.rotation.x=-Math.PI/2;scene.add(floor);
(function(){const g=new THREE.SphereGeometry(380,32,16);const c=[];const pos=g.attributes.position;for(let i=0;i<pos.count;i++){const y=pos.getY(i)/380;const t=Math.max(0,y);const top=new THREE.Color(0x0a0d24),hz=new THREE.Color(0x3a2f6a);const col=hz.clone().lerp(top,Math.pow(t,.55));c.push(col.r,col.g,col.b);}
  g.setAttribute('color',new THREE.Float32BufferAttribute(c,3));scene.add(new THREE.Mesh(g,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.BackSide,fog:false})));})();
const floaters=[];
(function(){const rockMat=toon(0x2a3160);for(let i=0;i<22;i++){const r=rnd(.8,3.6);const m=inked(new THREE.DodecahedronGeometry(r,0),rockMat,1.04);const x=rnd(.05,.95)*W,y=rnd(.05,.95)*H,z=rnd(250,ZMAX+400);
    m.position.copy(VA(x,y,z));m.scale.y=.7;const tip=inked(new THREE.ConeGeometry(r*.8,r*1.6,6),rockMat,1.04);tip.position.y=-r*1.1;tip.rotation.x=Math.PI;m.add(tip);scene.add(m);floaters.push({m,ph:rnd(0,TAU),y:m.position.y});}
  for(let i=0;i<14;i++){const a=i/14*TAU,R0=rnd(120,150);const h=rnd(25,60);const m=inked(new THREE.CylinderGeometry(rnd(1.5,3),rnd(4,7),h,7),toon(0x1c2248),1.02);m.position.set(Math.cos(a)*R0,h/2,Math.sin(a)*R0*.75);scene.add(m);}
  const cm=new THREE.MeshBasicMaterial({color:0x8a86c8,transparent:true,opacity:.12,depthWrite:false});for(let i=0;i<26;i++){const c=new THREE.Mesh(new THREE.SphereGeometry(rnd(4,9),10,6),cm);c.scale.y=.25;c.position.set(rnd(-110,110),rnd(36,46),rnd(-80,80));scene.add(c);}})();
const grid=new THREE.GridHelper(240,160,0x24305c,0x161c3a);grid.position.y=.01;scene.add(grid);
const rimMat=toon(0x1c2346);
for(let i=0;i<150;i++){const t=i/150;let x,y;if(t<.25){x=t*4*W;y=-30}else if(t<.5){x=W+30;y=(t-.25)*4*H}else if(t<.75){x=W-(t-.5)*4*W;y=H+30}else{x=-30;y=H-(t-.75)*4*H}
  const h=rnd(.12,.35);const m=inked(new THREE.BoxGeometry(1.1,h,1.1),rimMat,1.04);const p=V(x,y);m.position.set(p.x,h/2,p.z);m.rotation.y=rnd(0,1);scene.add(m);}
(function(){const n=600,p=new Float32Array(n*3);for(let i=0;i<n;i++){const a=Math.random()*TAU,e=rnd(.05,1.2),r=rnd(100,130);p[i*3]=Math.cos(a)*Math.cos(e)*r;p[i*3+1]=Math.sin(e)*r-12;p[i*3+2]=Math.sin(a)*Math.cos(e)*r;}
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(p,3));scene.add(new THREE.Points(g,new THREE.PointsMaterial({color:0x9fb0e8,size:.5,fog:false})));})();
