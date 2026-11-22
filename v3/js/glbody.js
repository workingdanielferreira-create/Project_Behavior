'use strict';
/* .glb fighter bodies (v3/RIG_SPEC.md rig): the shared test body packed by tools/build_kits.py into data/body.gen.js
   (window.PB3_BODY) plus each kit's own <folder>.glb (window.PB3_BODIES[folder], e.g. puck / ronin_copy, clips made from
   their 2D animations by tools/retarget2d.py). loadGlbBody parses them once at boot; glbBuild gives each fighter its own
   skinned copy of its body, toon + ink, tinted in the kit colour; glbAnim picks the clip for the fighter's state every
   frame (anim.js sync). A kit's own body wins over the shared one. */
let GLB_BODY=null;          // shared body {scene, clips:{name: AnimationClip}, h: model height, name}
const GLB_OWN={};           // folder -> own body (same shape)
function glbParse(b64,name,done){
  try{const bin=atob(b64),u8=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);
    new THREE.GLTFLoader().parse(u8.buffer,'',g=>{const clips={};g.animations.forEach(c=>{clips[c.name]=c;});
      g.scene.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(g.scene);
      done({scene:g.scene,clips,h:Math.max(.5,box.max.y-box.min.y),name});},
      err=>{console.error('PB3: body .glb failed',name,err);done(null);});}
  catch(err){console.error('PB3: body .glb failed',name,err);done(null);}}
function loadGlbBody(done){
  if(!THREE.GLTFLoader){done();return;}
  const B=window.PB3_BODY,own=window.PB3_BODIES||{};const jobs=[];
  if(B&&B.glb)jobs.push([B.glb,B.name,b=>{GLB_BODY=b;}]);
  for(const folder in own)jobs.push([own[folder],folder,b=>{if(b)GLB_OWN[folder]=b;}]);
  let left=jobs.length;if(!left){done();return;}
  jobs.forEach(([b64,name,put])=>glbParse(b64,name,b=>{put(b);if(--left===0)done();}));}
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
    if(isBlade&&!k.melee)o.visible=false;               // the sword shows on melee kits only (an own body without a weapon has none)
    const out=new THREE.SkinnedMesh(o.geometry,inkM);out.bind(o.skeleton,o.bindMatrix);out.frustumCulled=false;out.visible=o.visible;o.parent.add(out);});
  const mixer=new THREE.AnimationMixer(model);
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
  const air=f.z*K>1.2;
  if(f.lean>.15)return [air?'air_move':'run','move',0];
  return [air?'air':'idle','still',0];}
function glbAnim(f,rdt){const G=f.glb,B=G.body;const p=glbPick(f,B);const name=glbClip(B,p[0]);
  if(name!==G.cur||p[1]!==G.curId){const clip=B.clips[name];const act=G.mixer.clipAction(clip);
    const loop=!!GLB_LOOPS[name];act.reset();act.setLoop(loop?THREE.LoopRepeat:THREE.LoopOnce,Infinity);act.clampWhenFinished=!loop;
    act.timeScale=p[2]>0&&!loop?clip.duration/p[2]:1;
    const fade=name==='ko'||!G.act?0:p[2]>0?.06:.14;act.play();if(G.act&&G.act!==act)G.act.crossFadeTo(act,fade,false);else act.fadeIn(fade);
    G.act=act;G.cur=name;G.curId=p[1];}
  G.mixer.update(hitstopMs>0?0:rdt);}
