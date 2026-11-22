'use strict';
/* FX animation: runFx(fighter, type, arg) = every action effect a kit names. */
/* ---- action effects ---- */
function runFx(f,type,arg){FXF=f;const e=enemyOf(f);const fwd=[Math.cos(f.face),Math.sin(f.face)];
  switch(type){
  case'slash':fx_slash(f,arg);break;
  case'punch':fx_slash(f,arg,f.k.fx);fx_sparks(f.x+fwd[0]*40,f.y+fwd[1]*40,f.k.fx,8,4);break;
  case'slam':fx_slash(f,arg,f.k.fx,true);fx_ring(f.x+fwd[0]*50,f.y+fwd[1]*50,f.k.fx,3,.35);fx_dust(f.x,f.y,6);shake=Math.max(shake,.3);break;
  case'blinkbehind':{const a=Math.atan2(f.y-e.y,f.x-e.x)+Math.PI+rnd(-.6,.6);snapTo(f,e.x+Math.cos(a)*60,e.y+Math.sin(a)*60,true);break;}
  case'hop':{const a=rnd(0,TAU);f.snapCd=0;snapTo(f,e.x+Math.cos(a)*70,e.y+Math.sin(a)*70,true);break;}
  case'crescent':{const g=new THREE.Group();const p=V(f.x,f.y,1);g.position.copy(p);g.rotation.y=f.face3;const r=3.6*.9;
    const ring=new THREE.Mesh(new THREE.RingGeometry(r*.78,r,48,1,-Math.PI/2-1.1,2.2),add(f.k.fx,.9));ring.rotation.x=-Math.PI/2;g.add(ring);
    const core=new THREE.Mesh(new THREE.RingGeometry(r*.95,r,48,1,-Math.PI/2-1.1,2.2),add(0xffffff,.95));core.rotation.x=-Math.PI/2;g.add(core);
    const sx=f.x,sy=f.y,dx=fwd[0],dy=fwd[1];let hit=false;
    temp(g,.5,u=>{const px=sx+dx*arg*u,py=sy+dy*arg*u;g.position.copy(V(px,py,1));ring.material.opacity=.9*(1-u*u);core.material.opacity=.95*(1-u*u);
      if(!hit&&!e.ko&&Math.hypot(px-e.x,py-e.y)<120){hit=true;damage(f,e,85,'M');}});break;}
  case'rain':{for(let i=0;i<arg;i++)later(i*80,()=>{if(e.ko||!f.on)return;const tx=e.x+rnd(-90,90),ty=e.y+rnd(-90,90);const top=V(tx,ty,9),bot=V(tx,ty,.4);
      const m=new THREE.Mesh(new THREE.BoxGeometry(.06,1.2,.06),add(0xcff1ff,1));m.position.copy(top);temp(m,.16,u=>{m.position.lerpVectors(top,bot,u);});
      later(150,()=>{fx_ring(tx,ty,0xcff1ff,1.4,.25);fx_sparks(tx,ty,0xcff1ff,6,4,.4);if(!e.ko&&Math.hypot(tx-e.x,ty-e.y)<75)damage(f,e,26,i===arg-1?'H':'L');});});break;}
  case'dashslash':{const tx=e.x+fwd[0]*140,ty=e.y+fwd[1]*140;const sx=f.x,sy=f.y;f.snapCd=0;snapTo(f,tx,ty,false,true);later(60,()=>{fx_streak(V(sx,sy,1.05),V(f.x,f.y,1.05),0xffffff,.09);fx_streak(V(sx,sy,1.05),V(f.x,f.y,1.05),f.k.fx,.25);});break;}
  case'moon':{const tx=e.x,ty=e.y;const m=new THREE.Mesh(new THREE.RingGeometry(2.2,3,48,1,0,Math.PI),add(f.k.fx,.9));const p=V(tx,ty,10);m.position.copy(p);
      temp(m,.36,u=>{m.position.y=10-9.4*u;m.rotation.y+=.2;});fx_ring(tx,ty,f.k.fx,1.2,.36);later(360,()=>{fx_dome(tx,ty,f.k.fx,5);fx_dust(tx,ty,10);shake=Math.max(shake,.5);if(!e.ko&&Math.hypot(e.x-tx,e.y-ty)<190)damage(f,e,90,'H');});break;}
  case'vanish':f.gone=ms2t(220);fx_ring(f.x,f.y,f.k.fx,3,.3,1);break;
  case'cut':{const a=rnd(0,TAU);const p1=[e.x+Math.cos(a)*230,e.y+Math.sin(a)*230],p2=[e.x-Math.cos(a)*230,e.y-Math.sin(a)*230];fx_streak(V(p1[0],p1[1],1.1),V(p2[0],p2[1],1.1),0xffffff,.08);fx_streak(V(p1[0],p1[1],1.1),V(p2[0],p2[1],1.1),f.k.fx,.22);
      f.x=p2[0];f.y=p2[1];f.gone=ms2t(160);break;}
  case'xcut':f.gone=0;f.x=e.x-Math.cos(f.face)*90;f.y=e.y-Math.sin(f.face)*90;fx_dome(e.x,e.y,f.k.fx,6);flash(.3);shake=Math.max(shake,.8);break;
  case'shot':case'bigshot':{const d=Math.hypot(e.x-f.x,e.y-f.y)||1;const sp=1500;const ang=Math.atan2(e.y-f.y,e.x-f.x)+rnd(-.06,.06);shoot(f,Math.cos(ang)*sp,Math.sin(ang)*sp,arg,type==='bigshot'?.26:.14);break;}
  case'spread':{const b=Math.atan2(e.y-f.y,e.x-f.x);for(let i=-3;i<=3;i++){const a=b+i*.12;shoot(f,Math.cos(a)*1400,Math.sin(a)*1400,arg,.14);}break;}
  case'rail':{const b=Math.atan2(e.y-f.y,e.x-f.x);const ex=f.x+Math.cos(b)*1500,ey=f.y+Math.sin(b)*1500;fx_streak(V(f.x,f.y,1.1),V(ex,ey,1.1),0xffffff,.1);fx_streak(V(f.x,f.y,1.1),V(ex,ey,1.1),f.k.fx,.35);shake=Math.max(shake,.4);
      const dd=distSeg(e.x,e.y,f.x,f.y,ex,ey);if(dd<60)damage(f,e,arg,'H',true);break;}
  case'barrage':{for(let i=0;i<arg;i++)later(i*60,()=>{if(e.ko||!f.on)return;const a=Math.atan2(e.y-f.y,e.x-f.x)+rnd(-.35,.35);shoot(f,Math.cos(a)*1700,Math.sin(a)*1700,24,.16);});break;}
  case'chain':{fx_streak(V(f.x,f.y,1.1),V(e.x,e.y,1.1),f.k.fx,.06);if(e.armor<2&&Math.hypot(e.x-f.x,e.y-f.y)<520){const dx=f.x-e.x,dy=f.y-e.y,d=Math.hypot(dx,dy)||1;e.vx+=dx/d*1100;e.vy+=dy/d*1100;}break;}
  case'nova':fx_dome(f.x,f.y,f.k.fx,arg*K*1.3);fx_dust(f.x,f.y,14);shake=Math.max(shake,.6);flash(.15);break;
  case'leap':f.leap=ms2t(560);f.leapT=0;f.leapFrom=[f.x,f.y];f.leapTo=[e.x,e.y];break;
  case'kick':fx_slash(f,arg,f.k.fx,true);fx_slash(f,arg*.7,0xffffff);break;
  case'hopback':{const b=Math.atan2(f.y-e.y,f.x-e.x)+rnd(-.5,.5);f.snapCd=0;snapTo(f,f.x+Math.cos(b)*arg,f.y+Math.sin(b)*arg,false,true);break;}
  case'charge':{const m=new THREE.Mesh(new THREE.SphereGeometry(.22,14,10),add(f.k.core,.95));const gl=new THREE.Mesh(new THREE.SphereGeometry(.5,14,10),add(f.k.fx,.35));m.add(gl);
    const rays=new THREE.Group();for(let i=0;i<10;i++){const r=new THREE.Mesh(new THREE.PlaneGeometry(.03,1.4),add(f.k.fx,.7));r.rotation.z=i/10*TAU;r.position.set(Math.sin(i/10*TAU)*.7,-Math.cos(i/10*TAU)*.7,0);rays.add(r);}m.add(rays);
    const dur=arg/1000;temp(m,dur,u=>{m.position.copy(V(f.x+Math.cos(f.face)*35,f.y+Math.sin(f.face)*35,1.15));m.scale.setScalar(.4+u*1.3);rays.quaternion.copy(cam.quaternion);rays.rotation.z+=.3;rays.scale.setScalar(1.6-u);});
    fx_ring(f.x,f.y,f.k.fx,2.5,dur,.05);shake=Math.max(shake,.15);break;}
  case'laser':{const b=f.face;const ex=f.x+Math.cos(b)*1000,ey=f.y+Math.sin(b)*1000;fx_streak(V(f.x,f.y,1.15),V(ex,ey,1.15),0xffffff,.13);fx_streak(V(f.x,f.y,1.15),V(ex,ey,1.15),f.k.fx,.42);
    shake=Math.max(shake,.45);if(distSeg(e.x,e.y,f.x,f.y,ex,ey)<60)damage(f,e,arg,'H',true);break;}
  case'kibarrage':f.strafe=ms2t(900);f.strafeDir=Math.random()<.5?1:-1;for(let i=0;i<arg;i++)later(i*65,()=>{if(e.ko||!f.on)return;const a=Math.atan2(e.y-f.y,e.x-f.x)+rnd(-.25,.25);shoot(f,Math.cos(a)*1500,Math.sin(a)*1500,13,.13);});break;
  case'kame':{const beam=new THREE.Mesh(new THREE.CylinderGeometry(.45,.45,1,16,1,true),add(f.k.fx,.85));const core=new THREE.Mesh(new THREE.CylinderGeometry(.2,.2,1,12,1,true),add(0xffffff,.95));beam.add(core);scene.add(beam);
    let n=0;const T=ms2t(950);f.beam={m:beam,left:T};shake=Math.max(shake,.6);flash(.25);
    for(let i=0;i<10;i++)later(i*95,()=>{if(e.ko||!f.on)return;const ex=f.x+Math.cos(f.face)*1100,ey=f.y+Math.sin(f.face)*1100;if(distSeg(e.x,e.y,f.x,f.y,ex,ey)<75)damage(f,e,i===9?60:18,i===9?'B':'L',true);});break;}
  case'oath':fx_slash(f,arg,0xf4f8ff,true);fx_slash(f,arg*.92,0x4a2a9a,true,true);fx_moons(f,5,arg*.8);break;
  case'starburst':{fx_moons(f,5,arg*K/1.8*3,true);fx_slash(f,arg*K/0.9,0xf4f8ff);fx_ring(f.x,f.y,0xf4f8ff,arg*K*1.4,.3,1);break;}
  case'pierce':{const ex=f.x+Math.cos(f.face)*180,ey=f.y+Math.sin(f.face)*180;fx_streak(V(f.x,f.y,1.1),V(ex,ey,1.1),0xffffff,.07);fx_streak(V(f.x,f.y,1.1),V(ex,ey,1.1),0x6a3fd0,.2);
    later(70,()=>{const g=new THREE.Group();g.position.copy(V(f.x,f.y,1.1));g.rotation.y=f.face3;const r=1.6;const m=new THREE.Mesh(new THREE.RingGeometry(r*.6,r,32,1,-Math.PI/2-1.2,2.4),add(0xf4f8ff,.95));m.rotation.y=Math.PI/2;g.add(m);temp(g,.22,u=>{m.material.opacity=.95*(1-u);m.rotation.x=-u*2;});});break;}
  case'arcmove':{const side=Math.random()<.5?1:-1;const a=Math.atan2(f.y-e.y,f.x-e.x)+side*1.4;const tx=e.x+Math.cos(a)*arg,ty=e.y+Math.sin(a)*arg;
    const mx=(f.x+tx)/2+Math.cos(a)*arg*.6,my=(f.y+ty)/2+Math.sin(a)*arg*.6;f.snapCd=0;snapTo(f,mx,my,false,true);later(90,()=>{if(f.on&&!f.ko){f.snapCd=0;snapTo(f,tx,ty,false,true);}});break;}
  case'bf':{const base=Math.atan2(f.y-e.y,f.x-e.x);const pts=[[75,-10],[70,-45]];pts.forEach((p,i)=>later(i*110,()=>{if(!f.on||f.ko)return;const a=base+p[1]*Math.PI/180;f.snapCd=0;snapTo(f,e.x+Math.cos(a)*p[0],e.y+Math.sin(a)*p[0],false,true);}));
    later(250,()=>{if(!f.on||f.ko)return;const a=Math.atan2(e.y-f.y,e.x-f.x);f.snapCd=0;snapTo(f,e.x-Math.cos(a)*-40,e.y-Math.sin(a)*-40,false,true);});break;}
  case'leapto':{const a=Math.atan2(e.y-f.y,e.x-f.x);const d=Math.hypot(e.x-f.x,e.y-f.y);const go=Math.min(arg,Math.max(0,d-60));f.leap=ms2t(Math.max(220,go*2));f.leapT=0;f.leapFrom=[f.x,f.y];f.leapTo=[f.x+Math.cos(a)*go,f.y+Math.sin(a)*go];break;}
  case'satellite':{const g=new THREE.Group();for(let i=0;i<2;i++){const b=new THREE.Mesh(new THREE.BoxGeometry(.06,.06,1.3),new THREE.MeshBasicMaterial({color:i?0x3a2a7a:0xf4f8ff}));b.position.set(Math.cos(i*Math.PI)*1.2,0,Math.sin(i*Math.PI)*1.2);g.add(b);}
    g.position.copy(V(f.x,f.y,1));temp(g,.35,u=>{g.rotation.y+=.5;g.position.copy(V(f.x,f.y,1));g.scale.setScalar(1+u*.6);});later(30,()=>{fx_dome(f.x,f.y,0xf4f8ff,3);fx_crack(f.x,f.y,3);fx_dust(f.x,f.y,10);shake=Math.max(shake,.5);});break;}
  case'starfield':{const cx=f.x,cy=f.y;fx_moons(f,5,arg*K*1.2,true);for(let i=0;i<7;i++)later(i*128,()=>{if(!f.on||f.ko)return;fx_ring(cx,cy,i%2?0x6a3fd0:0xf4f8ff,arg*K*1.3,.25,1);if(!e.ko&&Math.hypot(e.x-cx,e.y-cy)<arg+40)damage(f,e,20,'L');});break;}
  case'graveyard':{const cx=e.x,cy=e.y;for(let i=0;i<arg;i++){const a=rnd(0,TAU),r=rnd(40,200);const x=clamp(cx+Math.cos(a)*r,30,W-30),y=clamp(cy+Math.sin(a)*r,30,H-30);later(i*55,()=>portalBlade(f,x,y,10000,i===arg-1));}
    fx_ring(cx,cy,0x6a3fd0,6,1.2,.04);break;}
  case'flare':fx_ring(f.x,f.y,0xf4f8ff,7,.5);fx_ring(f.x,f.y,0x6a3fd0,9,.7);f.stateUntil=tick+ms2t(10000);if(f.on)callout('XI-SCATTER','10 s: every action calls Heaven-cleaving blades','#f4f8ff',.9,true);break;
  case'hopchain':{let list=fieldBlades.filter(b=>b.side===f.side);
    if(!list.length){for(let i=0;i<4;i++){const a=i/4*TAU+rnd(-.3,.3);portalBlade(f,clamp(e.x+Math.cos(a)*170,30,W-30),clamp(e.y+Math.sin(a)*170,30,H-30),3000,false);}list=fieldBlades.filter(b=>b.side===f.side);}
    list.sort((p,q)=>Math.hypot(q.x-f.x,q.y-f.y)-Math.hypot(p.x-f.x,p.y-f.y));const n=list.length;let t=300;
    list.forEach((b,i)=>{const gap=480+(40-480)*Math.pow(i/Math.max(1,n-1),.7);t+=gap;later(t,()=>throwHopBlade(f,b,i===n-1));});
    if(f.act){f.act.def=Object.assign({},f.act.def,{dur:t+420});}break;}
  case'impact':{const p=[f.x+Math.cos(f.face)*45,f.y+Math.sin(f.face)*45];fx_ring(p[0],p[1],0xffffff,2.2,.2,1.1);fx_sparks(p[0],p[1],f.k.fx,10,6);fx_slash(f,2.4,f.k.fx);break;}
  case'seriouscharge':{const m=new THREE.Mesh(new THREE.SphereGeometry(.25,12,10),add(0xffffff,.95));const gl=new THREE.Mesh(new THREE.SphereGeometry(.6,12,10),add(f.k.fx,.35));m.add(gl);
    temp(m,arg/1000,u=>{m.position.copy(V(f.x+Math.cos(f.face)*40,f.y+Math.sin(f.face)*40,1.2));m.scale.setScalar(.5+u*1.6);});for(let i=0;i<6;i++)later(i*80,()=>{if(f.on)fx_ring(f.x,f.y,0xffffff,1.6-i*.15,.2,1);});shake=Math.max(shake,.25);break;}
  case'serious':{const b=f.face;const ex=clamp(f.x+Math.cos(b)*2852,0,W),ey=clamp(f.y+Math.sin(b)*2852,0,H);
    const g=new THREE.Group();const st=V(f.x,f.y,1.2),en=V(ex,ey,1.2);const dir=new THREE.Vector3().subVectors(en,st);const len=dir.length();
    const cone=new THREE.Mesh(new THREE.CylinderGeometry(3.2,.4,1,24,1,true),add(0xffffff,.55));cone.scale.y=len;cone.position.copy(st).addScaledVector(dir,.5);cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,-1,0),dir.clone().normalize());g.add(cone);
    const core=new THREE.Mesh(new THREE.CylinderGeometry(1.3,.2,1,16,1,true),add(f.k.fx,.85));core.scale.y=len;core.position.copy(cone.position);core.quaternion.copy(cone.quaternion);g.add(core);
    temp(g,.36,u=>{cone.material.opacity=.55*(1-u);core.material.opacity=.85*(1-u);});flash(.5);shake=Math.max(shake,1.2);hitstopMs=Math.max(hitstopMs,120);fx_dust(f.x,f.y,16);
    for(let i=0;i<6;i++)later(i*64,()=>{fx_ring(f.x+Math.cos(b)*(150+i*200),f.y+Math.sin(b)*(150+i*200),0xffffff,3.5,.3,1.2);if(!e.ko&&distSeg(e.x,e.y,f.x,f.y,ex,ey)<130)damage(f,e,arg,'M',true,null,i===5?900:60,true);});break;}
  case'kistream':for(let i=0;i<24;i++)later(i*46,()=>{if(e.ko||!f.on)return;const a=Math.atan2(e.y-f.y,e.x-f.x)+rnd(-.2,.2);shoot(f,Math.cos(a)*1700,Math.sin(a)*1700,arg,.12);});f.strafe=ms2t(1000);f.strafeDir=Math.random()<.5?1:-1;break;
  case'meteor':{const tx=e.x,ty=e.y;const m=new THREE.Mesh(new THREE.SphereGeometry(2.2,20,14),toon(0x6a3a28));const fire=new THREE.Mesh(new THREE.SphereGeometry(2.9,20,14),add(0xff7a2a,.5));m.add(fire);
    const top=V(tx-260,ty-260,26),bot=V(tx,ty,1.6);m.position.copy(top);fx_ring(tx,ty,0xff7a2a,4,.9,.05);
    temp(m,.91,u=>{m.position.lerpVectors(top,bot,u*u);m.rotation.x+=.1;fire.scale.setScalar(1+Math.sin(u*40)*.08);});
    later(912,()=>{fx_dome(tx,ty,0xff7a2a,9);fx_crack(tx,ty,5);fx_dust(tx,ty,24);flash(.5);shake=1.3;hitstopMs=Math.max(hitstopMs,160);
      for(let i=0;i<11;i++)later(i*100,()=>{fx_ring(tx,ty,0xffb070,7,.25,.1);if(!e.ko&&Math.hypot(e.x-tx,e.y-ty)<240)damage(f,e,arg,i===0?'H':'L',true,null,0,true);});});break;}
  case'transform':{const n=f.k.forms[f.formChannel]||f.k.forms[0];f.aura.visible=true;f.aura.children.forEach(c=>c.material.color.setHex(n.aura));for(let i=0;i<10;i++)later(i*300,()=>{if(f.on&&!f.ko){fx_ring(f.x,f.y,n.aura,2.4,.3,.05);fx_sparks(f.x,f.y,n.aura,8,5);}});break;}
  case'bigslam':fx_dome(f.x,f.y,f.k.fx,arg*K*1.4);fx_dust(f.x,f.y,20);shake=1;flash(.3);break;}}
