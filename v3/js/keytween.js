'use strict';
/* Key poses + tweening (Daniel 2026-11-22): every V3 clip is stored as KEY POSES only (v3/tools/keyreduce.py); the
   scene extras pb_keys {clip: {e: [ease per key]}} say how the motion eases INTO each key. This fills in the frames
   between keys, the same way the Python tools do (keyreduce.ease / slerp): between key i and key i+1,
   u = ease(e[i+1], s), rotations slerp (shortest way), positions lerp. Used by V3 (glbody.js, before retargeting) and
   Rig Forge 3D (playback of the keys it edits). */
const KT_FPS=60;
function ktEase(kind,u){u=Math.min(Math.max(u,0),1);
  switch(kind){
    case 'linear':return u;
    case 'smooth':return u*u*(3-2*u);
    case 'in':return u*u*u;
    case 'out':{const v=1-u;return 1-v*v*v;}
    case 'snap':{const v=1-u;return 1-v*v*v*v*v;}
    case 'hold':return u>=1?1:0;
    case 'back':{const c1=1.70158,w=u-1;return 1+(c1+1)*w*w*w+c1*w*w;}
    default:return u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;}}   // inout
const KT_EASES=['linear','smooth','inout','in','out','snap','hold','back'];
/* one clip's key info from a parsed glTF: {e:[...]} or null */
function ktInfo(gltf,name){const j=gltf&&gltf.parser&&gltf.parser.json;const ex=j&&j.scenes&&j.scenes[j.scene||0]&&j.scenes[j.scene||0].extras;
  const pk=(ex&&ex.pb_keys)||(gltf&&gltf.scene&&gltf.scene.userData&&gltf.scene.userData.pb_keys);return pk&&pk[name]||null;}
/* key clip + its key info {e: eases per key (shared key times)} or {b: {track name: eases}} (Rig Forge 3D saves each
   bone with its own keys), + optional per-track h (hold frames, 60 fps) and s (in-between steps) for the segment INTO
   each key -> dense clip at fps */
function ktExpand(clip,inf,fps){fps=fps||KT_FPS;inf=inf||{};
  const dur=clip.duration,n=Math.max(1,Math.round(dur*fps)),times=new Float32Array(n+1);
  for(let i=0;i<=n;i++)times[i]=Math.min(dur,i/fps);
  const qa=new THREE.Quaternion(),qb=new THREE.Quaternion();
  const tracks=clip.tracks.map(tr=>{const T=tr.times,V=tr.values,sz=V.length/T.length,out=new Float32Array(times.length*sz);
    const eb=inf.b&&inf.b[tr.name],ez=eb&&eb.length===T.length?eb:(inf.e&&inf.e.length===T.length?inf.e:null);
    const hs=inf.h&&inf.h[tr.name],hz=hs&&hs.length===T.length?hs:null,ss=inf.s&&inf.s[tr.name],sz2=ss&&ss.length===T.length?ss:null;let k=0;
    for(let i=0;i<times.length;i++){const t=times[i];
      while(k<T.length-2&&t>=T[k+1])k++;
      let u=0,a=k,b=Math.min(k+1,T.length-1);
      if(t<=T[0]){a=b=0;}else if(t>=T[T.length-1]){a=b=T.length-1;}
      else{const span=T[b]-T[a],h=Math.min(Math.max(0,(hz?hz[b]:0)/fps),Math.max(0,span-1/fps));   // hold frames, then steps, then ease
        u=t-T[a]<h?0:(t-T[a]-h)/Math.max(1e-9,span-h);u=Math.min(Math.max(u,0),1);
        const st=sz2?sz2[b]:0;if(st&&u<1)u=Math.floor(u*(st+1))/(st+1);u=ez?ktEase(ez[b],u):u;}
      if(sz===4){qa.fromArray(V,a*4);qb.fromArray(V,b*4);if(qa.dot(qb)<0)qb.set(-qb.x,-qb.y,-qb.z,-qb.w);
        qa.slerp(qb,u).toArray(out,i*4);}
      else for(let c=0;c<sz;c++)out[i*sz+c]=V[a*sz+c]*(1-u)+V[b*sz+c]*u;}
    return new tr.constructor(tr.name,times,out);});
  return new THREE.AnimationClip(clip.name,dur,tracks);}
/* every key clip of a parsed glTF -> dense, in place (V3) */
function ktExpandAll(gltf){
  gltf.animations=gltf.animations.map(c=>{const inf=ktInfo(gltf,c.name);return inf?ktExpand(c,inf):c;});
  return gltf;}
