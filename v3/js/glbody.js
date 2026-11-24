'use strict';
/* .glb fighter bodies (v3/RIG_SPEC.md rig). ONE shared body mesh: characters/ual_swordsman/ual_swordsman.glb (a
   placeholder; any RIG_SPEC / Mixamo-style humanoid can replace it), packed by tools/build_kits.py into
   data/body.gen.js (window.PB3_BODY). A kit's own characters/<folder>/<folder>.glb (window.PB3_BODIES[folder]) holds
   only a skeleton + that character's clips (tools/retarget2d.py) and scene extras pb_body {weapons {R, L}}: its clips
   are retargeted onto the shared body (retarget.js; unchanged while the body is the placeholder) and merged with the
   body's own clips (hit reactions, K.O., dodges, air ...; the body's attack / locomotion clips are left out so the
   character's own play through the fallbacks). An old full own .glb (with a mesh) is still worn as its own body.
   loadGlbBody parses everything once at boot; glbBuild gives each fighter its own skinned copy, toon + ink, tinted in
   the kit colour; glbAnim picks the clip for the fighter's state every frame (anim.js sync). */
let GLB_BODY=null;          // shared body {scene, clips:{name: AnimationClip}, h: model height, name}
const GLB_OWN={};           // folder -> {scene, clips, h, name, weapons}
// body clips a character with its own clips doesn't use (its own play through the fallbacks instead)
const GLB_DROP=/^(idle|run|walk|sprint|attack_normal(_\d+)?|attack_special(_\d+)?|ultimate(_\d+)?|transform|switch_in|switch_out|defend|parry)$/;
function glbParse(b64,name,done){
  try{const bin=atob(b64),u8=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);
    new THREE.GLTFLoader().parse(u8.buffer,'',g=>{ktExpandAll(g);const clips={};g.animations.forEach(c=>{clips[c.name]=c;});   // key poses -> tweened (keytween.js)
      let mesh=false;g.scene.traverse(o=>{if(o.isSkinnedMesh)mesh=true;});
      g.scene.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(g.scene);
      done({scene:g.scene,clips,list:g.animations,mesh,h:Math.max(.5,box.max.y-box.min.y),name,
        meta:(g.scene.userData&&g.scene.userData.pb_body)||null,rig:(g.scene.userData&&g.scene.userData.pb_rig3d)||null});},
      err=>{console.error('PB3: body .glb failed',name,err);done(null);});}
  catch(err){console.error('PB3: body .glb failed',name,err);done(null);}}
function loadGlbBody(done){
  if(!THREE.GLTFLoader){done();return;}
  const B=window.PB3_BODY,own=window.PB3_BODIES||{};const parsed={};const jobs=[];
  if(B&&B.glb)jobs.push([B.glb,B.name,b=>{GLB_BODY=b;}]);
  for(const folder in own)jobs.push([own[folder],folder,b=>{if(b)parsed[folder]=b;}]);
  let left=jobs.length;if(!left){done();return;}
  const finish=()=>{for(const folder in parsed){const o=parsed[folder];
      if(o.mesh){o.anchors3d=(o.rig&&o.rig.anchors)||null;GLB_OWN[folder]=o;continue;}                   // old full .glb: its own body
      if(!GLB_BODY)continue;
      let mine;try{mine=rtClips(o.list,o.scene,GLB_BODY.scene);}
      catch(err){console.error('PB3: retarget failed',folder,err);continue;}
      const clips={};for(const n in GLB_BODY.clips)if(!GLB_DROP.test(n))clips[n]=GLB_BODY.clips[n];
      Object.assign(clips,mine);
      GLB_OWN[folder]={scene:GLB_BODY.scene,clips,h:GLB_BODY.h,name:folder,weapons:(o.meta&&o.meta.weapons)||null,anchors3d:(o.rig&&o.rig.anchors)||null};}   // anchors3d: Rig Forge 3D FX anchors (fx3d.js)
    if(GLB_BODY)glbPrepRM(GLB_BODY.clips,GLB_BODY.scene,GLB_BODY.h);
    for(const folder in GLB_OWN)glbPrepRM(GLB_OWN[folder].clips,GLB_OWN[folder].scene,GLB_OWN[folder].h);
    done();};
  jobs.forEach(([b64,name,put])=>glbParse(b64,name,b=>{put(b);if(--left===0)finish();}));}
/* Root motion (Daniel 2026-11-23: moves travel, the fighter ends where the move ends). A clip whose hips end
   >= GLB_RM_MIN m (on the ground, body scale) away from where they started is a travelling clip: its hips' ground
   path is taken OUT of the clip (the hips keep only their height, so cross-fades stay put) and kept as
   clip.userData.rm {t, xz}; glbAnim moves the fighter's sim position along it while the clip plays (Solo +
   Battle). In-place clips (sway only) and sim-driven clips (GLB_RM_SKIP) are untouched. */
const GLB_RM_MIN=.25;
// clips the sim moves itself (knockback, K.O., dodges, tag switch, jumps): never root motion
const GLB_RM_SKIP=/^(idle|run|walk|sprint|ko|getup|knockdown|stagger|hit_|dodge|dash|switch_|jump|land|fall|air|parry|defend)/;
function glbPrepRM(clips,scene,h){const hips=scene&&scene.getObjectByName('Hips');if(!hips||!hips.parent)return;
  scene.updateMatrixWorld(true);const m4=new THREE.Matrix4().copy(scene.matrixWorld).invert().multiply(hips.parent.matrixWorld);
  const M=new THREE.Matrix3().setFromMatrix4(m4),Mi=M.clone().invert(),v=new THREE.Vector3(),min=GLB_RM_MIN*(h||1.8)/1.8;
  for(const n in clips){const c=clips[n];if(c.userData&&c.userData.rmDone)continue;c.userData=c.userData||{};c.userData.rmDone=1;
    if(GLB_RM_SKIP.test(n))continue;
    const tr=c.tracks.find(t=>t.name==='Hips.position');if(!tr||tr.values.length<6)continue;
    const V=tr.values,N=V.length/3,x0=V[0],y0=V[1],z0=V[2],xz=new Float32Array(N*2);
    v.set(V[N*3-3]-x0,V[N*3-2]-y0,V[N*3-1]-z0).applyMatrix3(M);if(Math.hypot(v.x,v.z)<min)continue;
    const out=new Float32Array(V.length);
    for(let i=0;i<N;i++){v.set(V[i*3]-x0,V[i*3+1]-y0,V[i*3+2]-z0).applyMatrix3(M);xz[i*2]=v.x;xz[i*2+1]=v.z;
      v.set(0,v.y,0).applyMatrix3(Mi);out[i*3]=x0+v.x;out[i*3+1]=y0+v.y;out[i*3+2]=z0+v.z;}
    tr.values=out;c.userData.rm={t:Float32Array.from(tr.times),xz};}}
function glbRMAt(rm,t,o){const T=rm.t,n=T.length;if(t<=T[0]){o[0]=rm.xz[0];o[1]=rm.xz[1];return o;}
  if(t>=T[n-1]){o[0]=rm.xz[n*2-2];o[1]=rm.xz[n*2-1];return o;}
  let a=0,b=n-1;while(b-a>1){const m=(a+b)>>1;if(T[m]<=t)a=m;else b=m;}
  const u=(t-T[a])/Math.max(1e-9,T[b]-T[a]);o[0]=rm.xz[a*2]+(rm.xz[b*2]-rm.xz[a*2])*u;o[1]=rm.xz[a*2+1]+(rm.xz[b*2+1]-rm.xz[a*2+1])*u;return o;}
function glbBodyOf(k){const own=k.src&&k.src.own_glb&&GLB_OWN[k.src.folder];return own||GLB_BODY;}
function useGlb(k){return !!glbBodyOf(k);}
/* skinned deep copy (what three's SkeletonUtils.clone does): clone, then rebind each mesh to the copy's own bones */
function glbClone(src){const out=src.clone(true);const bones={};out.traverse(o=>{if(o.isBone)bones[o.name]=o;});
  const orig={};src.traverse(o=>{if(o.isSkinnedMesh)orig[o.name]=o;});
  out.traverse(o=>{if(!o.isSkinnedMesh)return;const s=orig[o.name]||o;
    o.bind(new THREE.Skeleton(s.skeleton.bones.map(b=>bones[b.name]),s.skeleton.boneInverses.map(m=>m.clone())),s.bindMatrix.clone());});
  return out;}
function glbBuild(k,g){const body=glbBodyOf(k);const model=glbClone(body.scene);const s=1.8/body.h;model.scale.setScalar(s);g.add(model);
  const mat=new THREE.MeshToonMaterial({color:k.col,gradientMap:grad,skinning:true});
  const blade=new THREE.MeshToonMaterial({color:0xe8f4ff,gradientMap:grad,skinning:true,emissive:new THREE.Color(0x223044)});
  const inkM=new THREE.MeshToonMaterial({color:0x05070d,side:THREE.BackSide,skinning:true});
  inkM.onBeforeCompile=sh=>{sh.vertexShader=sh.vertexShader.replace('#include <project_vertex>','transformed += normalize(objectNormal) * 0.012;\n#include <project_vertex>');};
  const skinned=[];model.traverse(o=>{if(o.isSkinnedMesh)skinned.push(o);});
  skinned.forEach(o=>{const isBlade=/blade/i.test(o.name)||/blade/i.test(o.material&&o.material.name||'');o.material=isBlade?blade:mat;o.frustumCulled=false;
    if(isBlade){const left=/blade_?L/i.test(o.name),W=body.weapons;  // melee kits only; a character's file says which hands hold one
      const cw=W?(left?W.L:W.R):!left;o.visible=!!k.melee&&pbwOn(cw)&&!pbwCustom(cw);}   // a custom weapon (weapons3d.js) replaces this blade
    const out=new THREE.SkinnedMesh(o.geometry,inkM);out.bind(o.skeleton,o.bindMatrix);out.frustumCulled=false;out.visible=o.visible;o.parent.add(out);});
  const mixer=new THREE.AnimationMixer(model);
  if(k.melee&&body.weapons){const inkW=new THREE.MeshToonMaterial({color:0x05070d,side:THREE.BackSide});   // weapons built in the editor
    inkW.onBeforeCompile=sh=>{sh.vertexShader=sh.vertexShader.replace('#include <project_vertex>','transformed += normalize(objectNormal) * 0.006;\n#include <project_vertex>');};
    pbwAttach(model,body.weapons,{blade:blade,hilt:new THREE.MeshToonMaterial({color:0x2a2f3c,gradientMap:grad}),ink:inkW});}
  return {model,mat,mixer,body,cur:'',curId:null,act:null};}

/* clip fallbacks (v3/rig_spec.json clips) */
const GLB_FALLBACK={attack_normal:null,attack_special:null,ultimate:null,idle_ultimate:'idle',defend_reflect:'defend',defend_recovery:'stagger',
  parry:'defend',switch_in:'dash',switch_out:'dodge_back',transform:'ultimate',dodge_back:'dodge',dodge_left:'dodge',dodge_right:'dodge',
  walk:'run',sprint:'run',dash:'dodge',jump:'idle',air:'idle',air_move:'air',fall:'air',land:'idle',hit_heavy:'hit_light',hit_air:'hit_heavy',
  stagger:'hit_heavy',knockdown:'hit_heavy',getup:'idle'};
function glbClip(body,name){const C=body.clips;let n=name,guard=0;
  while(n&&!C[n]&&guard++<8){const m=n.match(/^(attack_normal|attack_special|ultimate)_\d+$/);n=m?m[1]:GLB_FALLBACK[n];}
  return n&&C[n]?n:'idle';}
const GLB_LOOPS={idle:1,run:1,walk:1,sprint:1,air:1,air_move:1,fall:1,idle_ultimate:1};
/* state -> [clip, id that restarts it when it changes, length to fit in s (0 = natural speed)] */
function glbPick(f,body){
  if(f.ko)return ['ko','ko',0];
  if(f.stun>0){const n=f.stunKind==='down'?'knockdown':f.stunKind==='air'?'hit_air':f.recoil>.45?'hit_heavy':'hit_light';return [n,'stun'+f.stunKind+(f.stunId||0),0];}
  const a=f.act;
  if(a){const nm=String(a.name||''),id=a.def&&a.def.n2d;let c;
    if(id&&body.clips[id])c=id;                        // the body has this very action's clip (own bodies: one per 2D action)
    else if(a.kind==='normal'){const n=parseInt(nm.replace(/\D/g,''),10)||1;c=n>1?'attack_normal_'+n:'attack_normal';}
    else if(a.kind==='ult')c='ultimate';
    else if(a.kind==='transform')c='transform';
    else if(nm==='switch_in')c='switch_in';
    else if(a.kind==='special'){const n=parseInt(nm.replace(/\D/g,''),10)||1;c=n>1?'attack_special_'+n:'attack_special';}
    else if(nm==='defend')c='defend';
    else c=nm||'idle';
    return [c,a,(a.def&&a.def.dur||0)/1000];}
  if(f.parry>0)return ['parry','parry',0];
  if(f.block>0)return ['defend','block',0];
  if(f.snap)return [Math.cos(Math.atan2(f.snap.ty-f.y,f.snap.tx-f.x)-f.face)<-.3?'dodge_back':'sprint','snap',0];
  if(!canFly(f)&&f.z>8)return f.vz>120?['jump','jump'+(f.jumps||0),0]:['fall','fall',0];   // jumps (gravity.js)
  if(f.landT>tick&&f.z<=0&&f.lean<=.15)return ['land','land',0];
  const air=f.z*K>1.2;
  if(f.lean>.15)return [air?'air_move':'run','move',0];
  return [air?'air':'idle','still',0];}
function glbAnim(f,rdt){const G=f.glb,B=G.body;const p=glbPick(f,B);const name=glbClip(B,p[0]);
  if(name!==G.cur||p[1]!==G.curId){const clip=B.clips[name];const act=G.mixer.clipAction(clip);
    const loop=!!GLB_LOOPS[name];act.reset();act.setLoop(loop?THREE.LoopRepeat:THREE.LoopOnce,Infinity);act.clampWhenFinished=!loop;
    act.timeScale=p[2]>0&&!loop?clip.duration/p[2]:1;
    const fade=name==='ko'||!G.act?0:p[2]>0?.06:.14;act.play();if(G.act&&G.act!==act)G.act.crossFadeTo(act,fade,false);else act.fadeIn(fade);
    G.act=act;G.cur=name;G.curId=p[1];
    G.rm=!loop&&clip.userData&&clip.userData.rm||null;G.rmP=[0,0];if(G.rm)glbRMAt(G.rm,0,G.rmP);}
  G.mixer.update(hitstopMs>0?0:rdt);
  if(G.rm&&G.act&&!f.mv3){   // root motion (not while FX Studio 3D movement drives the body): carry the fighter along the clip's ground path (body forward = +Z = facing)
    const q=glbRMAt(G.rm,Math.min(G.act.time,G.rm.t[G.rm.t.length-1]),[0,0]),s=G.model.scale.x;
    const lx=(q[0]-G.rmP[0])*s,lz=(q[1]-G.rmP[1])*s;G.rmP=q;
    if(lx||lz){const r=f.g.rotation.y,wx=lx*Math.cos(r)+lz*Math.sin(r),wz=-lx*Math.sin(r)+lz*Math.cos(r);
      const nx=clamp(f.x+wx/K,30,W-30),ny=clamp(f.y+wz/K,30,H-30);f.g.position.x+=(nx-f.x)*K;f.g.position.z+=(ny-f.y)*K;
      f.x=nx;f.y=ny;f.lx=f.x;f.ly=f.y;}}}
