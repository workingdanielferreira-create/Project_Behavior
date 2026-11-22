'use strict';
/* Clip retargeting between humanoid skeletons (three.js only; used by V3 glbody.js and Rig Forge 3D).
   The fighters' clips (characters/<name>/<name>.glb, skeleton + clips, no mesh) were solved on the placeholder body
   (characters/ual_swordsman/ual_swordsman.glb). When the body is swapped for another humanoid (Mixamo, Quaternius,
   a Blender / Rigify export ...) the clips are moved onto it here, so a new body needs no hand fixing:
   - bones are matched by RIG_SPEC (Mixamo) name; a "mixamorig" / "mixamorig:" prefix and the UE-mannequin names
     (pelvis, spine_01, upperarm_l ...) are understood (rtCanon);
   - each bone's WORLD rotation change from its rest pose is carried over, so the new skeleton's own bone axes don't
     matter, and its rest pose is lined up first (rest bone direction turned onto the clip's: T-pose vs A-pose);
   - the hips' move is scaled by hip height. Same skeleton as the clip (the placeholder) = clips used unchanged.
   Bodies must face +Z with +Y up (glTF default, as Mixamo / Blender exports do). */
const RT_UE={pelvis:'Hips',spine_01:'Spine',spine_02:'Spine1',spine_03:'Spine2',spine_04:'Spine2',spine_05:'Spine2',neck_01:'Neck',neck_02:'Neck',head:'Head'};
const RT_LIMB={clavicle:'Shoulder',upperarm:'Arm',lowerarm:'ForeArm',hand:'Hand',thigh:'UpLeg',calf:'Leg',foot:'Foot',ball:'ToeBase',ball_leaf:'Toe_End'};
const RT_FING={thumb:'Thumb',index:'Index',middle:'Middle',ring:'Ring',pinky:'Pinky'};
const RT_SIDE={l:'Left',r:'Right'};
function rtCanon(name){let n=String(name||'').replace(/^mixamorig\d*[:_]?/i,'');
  if(RT_UE[n]||RT_UE[n.toLowerCase()])return RT_UE[n]||RT_UE[n.toLowerCase()];
  const m=n.toLowerCase().match(/^(.*)_(l|r)$/);
  if(m){const base=m[1],side=RT_SIDE[m[2]];if(RT_LIMB[base])return side+RT_LIMB[base];
    const p=base.split('_');if(RT_FING[p[0]]&&p[1])return side+'Hand'+RT_FING[p[0]]+(+p[1]);}
  return n;}
/* rest data of a skeleton scene: canonical name -> {node, wq (world quat), wp (world pos)} */
function rtRest(root){root.updateMatrixWorld(true);const out={};
  root.traverse(o=>{if(o===root||!o.name||o.isMesh)return;const k=rtCanon(o.name);if(out[k])return;
    out[k]={node:o,wq:o.getWorldQuaternion(new THREE.Quaternion()),wp:o.getWorldPosition(new THREE.Vector3()),lq:o.quaternion.clone()};});
  return out;}
function rtSame(src,dst){// same skeleton (names + rest local rotations): clips can be used as they are
  for(const k in src){const d=dst[k];if(!d)continue;if(d.node.name!==src[k].node.name)return false;
    if(Math.abs(d.lq.dot(src[k].lq))<0.9999)return false;}
  return true;}
const RT_CHAIN=[['Hips','Spine'],['Spine','Spine1'],['Spine1','Spine2'],['Spine2','Neck'],['Neck','Head'],['Head','HeadTop_End']];
['Left','Right'].forEach(s=>{RT_CHAIN.push([s+'Shoulder',s+'Arm'],[s+'Arm',s+'ForeArm'],[s+'ForeArm',s+'Hand'],[s+'Hand',s+'HandMiddle1'],
  [s+'UpLeg',s+'Leg'],[s+'Leg',s+'Foot'],[s+'Foot',s+'ToeBase'],[s+'ToeBase',s+'Toe_End']);
  ['Thumb','Index','Middle','Ring','Pinky'].forEach(f=>{for(let i=1;i<4;i++)RT_CHAIN.push([s+'Hand'+f+i,s+'Hand'+f+(i+1)]);});});
/* retarget clips from the skeleton scene srcRoot onto dstRoot; returns {name: clip} (same objects if the skeletons match) */
function rtClips(clips,srcRoot,dstRoot){
  const S=rtRest(srcRoot),D=rtRest(dstRoot);const out={};
  if(rtSame(S,D)){clips.forEach(c=>{out[c.name]=c;});return out;}
  // rest line-up: turn each new bone's rest direction onto the clip skeleton's (world)
  const align={};RT_CHAIN.forEach(([a,b])=>{if(!S[a]||!S[b]||!D[a]||!D[b])return;
    const ds=S[b].wp.clone().sub(S[a].wp),dd=D[b].wp.clone().sub(D[a].wp);if(ds.lengthSq()<1e-10||dd.lengthSq()<1e-10)return;
    align[a]=new THREE.Quaternion().setFromUnitVectors(dd.normalize(),ds.normalize());});
  const hipK=S.Hips&&D.Hips&&Math.abs(S.Hips.wp.y)>1e-4?D.Hips.wp.y/S.Hips.wp.y:1;
  // destination bones parent-first, with their canonical names
  const order=[];dstRoot.traverse(o=>{if(o.name&&!o.isMesh&&S[rtCanon(o.name)]&&D[rtCanon(o.name)]&&D[rtCanon(o.name)].node===o)order.push(o);});
  const mixer=new THREE.AnimationMixer(srcRoot);
  clips.forEach(clip=>{
    const times=[...new Set([].concat(...clip.tracks.map(t=>Array.from(t.times))))].sort((a,b)=>a-b);
    const act=mixer.clipAction(clip);act.play();
    const Q={},P=[];order.forEach(o=>{Q[o.name]=[];});
    const wq=new Map();
    times.forEach(t=>{act.time=t;mixer.update(0);srcRoot.updateMatrixWorld(true);wq.clear();
      order.forEach(o=>{const k=rtCanon(o.name),s=S[k];
        const cur=s.node.getWorldQuaternion(new THREE.Quaternion());
        const delta=cur.multiply(s.wq.clone().invert());                       // world change from rest
        const want=delta.multiply(align[k]||new THREE.Quaternion()).multiply(D[k].wq);  // new bone's world rotation
        const par=o.parent;const pw=wq.get(par)||par.getWorldQuaternion(new THREE.Quaternion());
        const local=pw.clone().invert().multiply(want);wq.set(o,want);
        const arr=Q[o.name];const prev=arr.length?arr[arr.length-1]:null;if(prev&&prev.dot(local)<0)local.set(-local.x,-local.y,-local.z,-local.w);
        arr.push(local);});
      if(S.Hips&&D.Hips){const d=S.Hips.node.getWorldPosition(new THREE.Vector3()).sub(S.Hips.wp).multiplyScalar(hipK);
        const wp=D.Hips.wp.clone().add(d);const par=D.Hips.node.parent;par.updateMatrixWorld(true);
        P.push(par.worldToLocal(wp));}});
    act.stop();mixer.uncacheAction(clip);
    const tracks=[];order.forEach(o=>{const v=[];Q[o.name].forEach(q=>v.push(q.x,q.y,q.z,q.w));
      tracks.push(new THREE.QuaternionKeyframeTrack(o.name+'.quaternion',times,v));});
    if(P.length){const v=[];P.forEach(p=>v.push(p.x,p.y,p.z));tracks.push(new THREE.VectorKeyframeTrack(D.Hips.node.name+'.position',times,v));}
    out[clip.name]=new THREE.AnimationClip(clip.name,clip.duration,tracks);});
  return out;}
