'use strict';
/* 2D FX in the 3D world. A real kit's FX are played by FX Studio's own runtime (tools/fx/studio/fxkit.js + its
   style files, loaded unchanged by index.html): same look, timing, damage, knockback and re-hit rules as the
   2D game. Each fighter gets an FXK.Player and a host, exactly like the Studio preview.
   Where the 2D happens: a flat 2D space centred on the fighter's body, x = camera right, y = camera down, in 2D
   game px (a fighter stands 28 px = its 1.8-unit 3D body). The enemy is placed in that space where it appears
   from the camera, so shots fly at it and hits land where they are seen to touch (host.hurt, onHit -> damage()).
   How it respects 3D: the 2D drawing is painted onto two camera-facing cards in the scene at the fighter (the
   2D "behind" layer just behind the body, "front" just in front), so perspective, fog and anything standing in
   front of it (rocks, pillars, the other fighter) apply. Each card covers only the live FX, at about screen
   resolution. */
const FX2D_UNITS=1.8/(window.FXK?FXK.STAND_HEIGHT_PX:28);   // 3D units per 2D px
const FX2D_HURT=16;                                          // 2D hurt radius (PROJ_HIT_RADIUS)
const FX2D_MAX_TEX=2048;
const _R=new THREE.Vector3(),_U=new THREE.Vector3(),_Fw=new THREE.Vector3(),_d=new THREE.Vector3(),_o=new THREE.Vector3();

function fx2dState(f){if(f.fx2)return f.fx2;if(!f.k.fx2d||!window.FXK)return null;
  const F=f.k.src.fxkit||{};const by={};
  for(const raw of F.effects||[]){if(raw.enabled===false||!raw.action)continue;let e;try{e=FXK.normalize(JSON.parse(JSON.stringify(raw)));}catch(err){continue;}(by[e.action]||(by[e.action]=[])).push(e);}
  const pal=f.k.src.palette||{};const rgb=h=>FXK.hexRgb(h||'#ffffff',[255,255,255]);
  const sp=F.space||{};const st={player:new FXK.Player(),by,t:0,act:null,frame:0,action:'idle',
    lut:FXK.buildLut([rgb(pal.body),rgb(pal.accent)]),anchors:F.anchors||{},origin:sp.image_origin_px||[240,240],
    kImg:(+sp.game_px_per_image_px||.27)*(+F.character_scale||1),lib:{entry_sets:F.entry_sets||[],paths:F.paths||[]},
    target:[40,0],facing:1,hurt:null,cards:[]};
  st.host=fx2dHost(f,st);f.fx2=st;return st;}

function fx2dHost(f,st){return {
  get facing(){return st.facing;},get target(){return st.target;},get hurt(){return st.hurt;},
  get wang(){return 90;},get lut(){return st.lut;},get pscale(){return 1;},get lib(){return st.lib;},
  get showHitboxes(){return false;},get solo(){return !st.hurt;},get shots(){return [];},
  anchor(n){if(n==='figure')return [0,0];if(n==='target')return st.target.slice();
    const row=(st.anchors[st.action]||{})[n];if(!row)return [0,0];let p=null;
    for(let i=Math.min(st.frame,row.length-1);i>=0&&!p;i--)p=row[i];for(let j=st.frame+1;j<row.length&&!p;j++)p=row[j];
    return p?[(p[0]-st.origin[0])*st.kImg*st.facing,(p[1]-st.origin[1])*st.kImg]:[0,0];},
  blinkPoint(){return null;},snapshot(){return {};},outline(){return null;},drawGhost(){},
  hitstop(n){hitstopMs=Math.max(hitstopMs,n*TICK);},shake(px){shake=Math.max(shake,Math.min(1.2,px*.05));},
  onIntercept(){},onDrag(){},
  onHit(inst,dmg,dx,dy,kb){const e=enemyOf(f);if(!e||e.ko||!e.on)return;const fx=inst.fx||{};
    const w=kb>=20?'B':kb>=13?'H':kb>=7?'M':'L';const shot=fx.motion&&fx.motion.kind!=='attached'&&fx.motion.kind!=='orbit';
    damage(f,e,dmg,w,shot,null,kb>0?kb*PX2D*.35:0);}};}

// Camera-space frame of a fighter: origin at its body centre, R / U = camera right / up.
function fx2dFrame(f,out){out.copy(VA(f.x,f.y,f.z,.9+(f.h||0)));return out;}
function fx2dToLocal(f,g){// enemy body centre -> f's 2D space (2D px, y down)
  fx2dFrame(f,_o);_d.copy(VA(g.x,g.y,g.z,.9+(g.h||0))).sub(_o);return [_d.dot(_R)/FX2D_UNITS,-_d.dot(_U)/FX2D_UNITS];}
function fx2dCamAxes(){_R.set(1,0,0).applyQuaternion(cam.quaternion);_U.set(0,1,0).applyQuaternion(cam.quaternion);_Fw.set(0,0,1).applyQuaternion(cam.quaternion);}

// Sim tick (main.js), each fielded fighter: advance its FX one 16 ms tick.
function fx2dTick(f){const st=fx2dState(f);if(!st)return;
  if(!f.on||f.ko){st.player.reset();st.act=null;return;}
  fx2dCamAxes();const e=enemyOf(f);
  if(e&&e.on&&!e.ko&&e.gone<=0){st.target=fx2dToLocal(f,e);st.hurt={x:st.target[0],y:st.target[1],r:FX2D_HURT};}else st.hurt=null;
  st.facing=st.target[0]<0?-1:1;
  const a=f.act;if(a!==st.act){st.act=a;st.t=0;}
  if(a&&a.def.fx2d){st.action=a.def.n2d;st.frame=Math.min(a.def.frames-1,Math.floor(st.t*TICK/a.def.frameMs));
    st.player.tick(st.by[a.def.n2d]||[],st.host,st.t,a.def.frames,a.def.frameMs,{});}
  else{st.action=f.snap||f.lean>.2?'run':'idle';st.frame=0;st.player.tick([],st.host,st.t,1,TICK,{});}
  st.t++;}

// Render frame (main.js): paint each fighter's live 2D FX onto its two cards and place them in 3D.
function fx2dDraw(){fx2dCamAxes();const H=renderer.domElement.height,tanH=Math.tan(cam.fov*Math.PI/360);
  for(const s of sides)for(const f of s.team){const st=f.fx2;if(!st)continue;
    const live=f.on&&!f.ko&&st.player.insts.length;
    if(!live){st.cards.forEach(c=>c.mesh.visible=false);continue;}
    // the 2D box the live FX cover
    let x0=-40,y0=-40,x1=40,y1=40;
    for(const i of st.player.insts){const P=i.fx.params||{};const m=Math.min(1400,Math.max(60,+P.length||0,+P.radius||0,+P.r_end||0,+P.span||0)+30);
      x0=Math.min(x0,i.x-m);x1=Math.max(x1,i.x+m);y0=Math.min(y0,i.y-m);y1=Math.max(y1,i.y+m);
      if(i.x2!=null){x0=Math.min(x0,i.x2-m);x1=Math.max(x1,i.x2+m);y0=Math.min(y0,i.y2-m);y1=Math.max(y1,i.y2+m);}}
    x0=Math.max(x0,-1600);y0=Math.max(y0,-1600);x1=Math.min(x1,1600);y1=Math.min(y1,1600);
    const bw=x1-x0,bh=y1-y0;fx2dFrame(f,_o);
    const dist=Math.max(.5,_d.copy(_o).sub(cam.position).dot(_Fw)*-1);
    let dens=clamp(H/(2*tanH*dist)*FX2D_UNITS,.4,3);dens=Math.min(dens,FX2D_MAX_TEX/bw,FX2D_MAX_TEX/bh);
    const cw=Math.ceil(bw*dens),ch=Math.ceil(bh*dens);
    ['behind','front'].forEach((layer,li)=>{const c=fx2dCard(st,li,cw,ch);const g=c.ctx;
      g.setTransform(1,0,0,1,0,0);g.clearRect(0,0,c.cv.width,c.cv.height);g.globalAlpha=1;g.globalCompositeOperation='source-over';
      g.setTransform(dens,0,0,dens,-x0*dens,-y0*dens);
      try{st.player.draw(g,st.host,layer,1,f.gone>0);}catch(err){console.error('fx2d draw',err);}
      c.tex.repeat.set(cw/c.cv.width,ch/c.cv.height);c.tex.offset.set(0,1-ch/c.cv.height);c.tex.needsUpdate=true;
      const m=c.mesh;m.visible=true;m.quaternion.copy(cam.quaternion);m.scale.set(bw*FX2D_UNITS,bh*FX2D_UNITS,1);
      m.position.copy(_o).addScaledVector(_R,(x0+bw/2)*FX2D_UNITS).addScaledVector(_U,-(y0+bh/2)*FX2D_UNITS).addScaledVector(_Fw,li?.38:-.38);});}}
function fx2dCard(st,li,w,h){const pw=v=>Math.min(FX2D_MAX_TEX,Math.max(256,1<<Math.ceil(Math.log2(Math.max(1,v)))));
  let c=st.cards[li];const W2=pw(w),H2=pw(h);
  if(c&&(c.cv.width<W2||c.cv.height<H2||c.cv.width>W2*4||c.cv.height>H2*4)){scene.remove(c.mesh);c.tex.dispose();c.mesh.material.dispose();c=null;}
  if(!c){const cv=document.createElement('canvas');cv.width=W2;cv.height=H2;const tex=new THREE.CanvasTexture(cv);tex.premultiplyAlpha=true;tex.minFilter=THREE.LinearFilter;tex.generateMipmaps=false;
    const mat=new THREE.MeshBasicMaterial({map:tex,transparent:true,depthWrite:false,premultipliedAlpha:true,side:THREE.DoubleSide});
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(1,1),mat);mesh.renderOrder=li?3:1;scene.add(mesh);c=st.cards[li]={cv,ctx:cv.getContext('2d'),tex,mesh};}
  return c;}
function fx2dClear(f){const st=f.fx2;if(!st)return;st.cards.forEach(c=>{scene.remove(c.mesh);c.tex.dispose();c.mesh.material.dispose();});f.fx2=null;}
