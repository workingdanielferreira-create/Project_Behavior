'use strict';
/* 3D weapon editor shapes (Rig Forge 3D "Weapons", Daniel 2026-11-22; the original Rig Forge's weapon editor in 3D).
   A character's .glb scene extras pb_body.weapons = {R: cfg, L: cfg}; cfg = true / false (old files: the body's own
   blade shown or not) or {on, shape, len, w, thick, curve, tip, guard, handle, grip, roll} (metres / degrees). A cfg
   with a shape builds that weapon from code as a child of the hand's Weapon_R / Weapon_L bone (pointing along the
   bone's rest Weapon -> WeaponTip line, grip slides it along that line, roll turns it about it) and hides the body's
   skinned blade on that hand. Used by V3 (glbody.js glbBuild) and Rig Forge 3D (preview + save). */
const PBW_SHAPES={
  sword:     {len:1.00,w:.055,thick:.012,curve:0,   tip:.14,single:false,guard:.18,handle:.20},
  katana:    {len:1.02,w:.034,thick:.010,curve:.07, tip:.08,single:true, guard:.08,handle:.26},
  dagger:    {len:.36, w:.045,thick:.010,curve:0,   tip:.30,single:false,guard:.10,handle:.11},
  greatsword:{len:1.40,w:.10, thick:.018,curve:0,   tip:.12,single:false,guard:.30,handle:.34},
  rapier:    {len:1.05,w:.018,thick:.010,curve:0,   tip:.20,single:false,guard:.14,handle:.16},
  cleaver:   {len:.72, w:.13, thick:.014,curve:0,   tip:0,  single:true, guard:.06,handle:.18},
  /* pistol (Daniel 2026-11-22): len = barrel / slide length, w = slide height, thick = slide width, handle = grip
     length, guard = trigger guard size, curve = grip rake; tip unused. The grip lies along the weapon line (in the
     fist), the barrel points out the edge side (+X) from the top of the grip: roll turns it to the finger side. */
  pistol:    {len:.19, w:.034,thick:.026,curve:.18, tip:0,  single:true, guard:.045,handle:.10}};
const PBW_KEYS=['len','w','thick','curve','tip','guard','handle'];
function pbwOn(c){return c&&typeof c==='object'?c.on!==false:!!c;}
function pbwCustom(c){return !!(c&&typeof c==='object'&&c.shape&&PBW_SHAPES[c.shape]);}
function pbwFull(c){const d=PBW_SHAPES[c.shape]||PBW_SHAPES.sword,o={on:c.on!==false,shape:c.shape,grip:+c.grip||0,roll:+c.roll||0,single:d.single};
  PBW_KEYS.forEach(k=>{o[k]=c[k]!=null&&isFinite(+c[k])?+c[k]:d[k];});return o;}
/* blade along +Y (0 = guard .. len = tip), edge toward +X, spine toward -X when single-edged; curve bends it toward -X */
function pbwBladeGeo(c){const n=16,pos=[],idx=[];
  for(let i=0;i<=n;i++){const t=i/n,y=t*c.len,taper=c.tip>0&&t>1-c.tip?Math.max(0,(1-t)/c.tip):1,hw=c.w/2*taper,
      x=-c.curve*c.len*t*t,ht=c.thick/2*(0.35+0.65*taper);
    const back=c.single?-hw*0.15:-hw;                 // single edge: a thick spine stays near the middle
    pos.push(x+hw,y,0, x,y,ht, x+back,y,0, x,y,-ht);}
  for(let i=0;i<n;i++)for(let j=0;j<4;j++){const a=i*4+j,b=i*4+(j+1)%4,c2=a+4,d=b+4;idx.push(a,c2,b,b,c2,d);}
  idx.push(0,1,2,0,2,3);const t0=n*4;idx.push(t0,t0+2,t0+1,t0,t0+3,t0+2);
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.setIndex(idx);g.computeVertexNormals();return g;}
function pbwInk(geo,inkMat){const m=new THREE.Mesh(geo,inkMat);m.renderOrder=-1;return m;}
/* pistol parts in the weapon's local frame (+Y = weapon line through the fist, +X = barrel) */
function pbwPistol(c,add,mats){const top=c.handle*0.3,rake=Math.atan(c.curve);
  const slide=new THREE.BoxGeometry(c.len,c.w,c.thick);slide.translate(c.len/2-c.handle*0.25,top+c.w/2,0);add(slide,mats.blade);
  const bar=new THREE.CylinderGeometry(c.thick*0.28,c.thick*0.28,c.len*0.12,10);bar.rotateZ(Math.PI/2);
  bar.translate(c.len*1.06-c.handle*0.25,top+c.w*0.62,0);add(bar,mats.hilt||mats.blade);
  const grip=new THREE.BoxGeometry(c.thick*1.15,c.handle,c.thick*1.05);grip.translate(0,top-c.handle/2,0);
  grip.rotateZ(rake);add(grip,mats.hilt||mats.blade);
  if(c.guard>0){const gd=new THREE.TorusGeometry(c.guard*0.5,c.thick*0.14,6,14,Math.PI);gd.rotateZ(Math.PI);
    gd.translate(c.guard*0.55+c.thick*0.4,top,0);add(gd,mats.hilt||mats.blade);}}
/* the weapon as a Group (local +Y = blade direction), mats = {blade, hilt, ink} */
function pbwBuild(cfg,mats){const c=pbwFull(cfg),g=new THREE.Group();g.name='pbw_'+c.shape;
  const add=(geo,mat)=>{const m=new THREE.Mesh(geo,mat);m.castShadow=false;g.add(m);if(mats.ink)g.add(pbwInk(geo,mats.ink));return m;};
  if(c.shape==='pistol'){pbwPistol(c,add,mats);return g;}
  add(pbwBladeGeo(c),mats.blade);
  if(c.guard>0){const gg=new THREE.BoxGeometry(c.single?c.guard*0.6:c.guard,c.thick*2.2,c.thick*3.2);gg.translate(0,-c.thick*1.1,0);add(gg,mats.hilt||mats.blade);}
  if(c.handle>0){const hg=new THREE.CylinderGeometry(c.thick*1.5,c.thick*1.7,c.handle,10);hg.translate(0,-c.thick*2.2-c.handle/2,0);add(hg,mats.hilt||mats.blade);}
  return g;}
/* (re)attach the custom weapons to a skeleton scene; returns the meshes it hid (body's skinned blades) */
function pbwAttach(root,weapons,mats){pbwDetach(root);if(!weapons)return;
  ['R','L'].forEach(side=>{const cfg=weapons[side],bone=root.getObjectByName('Weapon_'+side),tip=root.getObjectByName('WeaponTip_'+side);
    const skin=[];root.traverse(o=>{if(o.isSkinnedMesh&&(side==='L'?/blade_?L$/i.test(o.name):/^blade$/i.test(o.name)))skin.push(o);});
    if(!bone)return;
    if(!pbwCustom(cfg)){return;}
    skin.forEach(o=>{o.userData.pbwHid=o.userData.pbwHid==null?o.visible:o.userData.pbwHid;o.visible=false;});
    if(!pbwOn(cfg))return;
    const c=pbwFull(cfg),axis=tip?tip.position.clone().normalize():new THREE.Vector3(0,1,0);
    const g=pbwBuild(cfg,mats);g.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),axis);
    g.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(axis,c.roll*Math.PI/180));
    g.position.copy(axis).multiplyScalar(c.grip);
    g.userData.pbw=true;bone.add(g);});}
function pbwDetach(root){const rm=[];root.traverse(o=>{if(o.userData&&o.userData.pbw)rm.push(o);});rm.forEach(o=>{if(o.parent)o.parent.remove(o);});
  root.traverse(o=>{if(o.isSkinnedMesh&&o.userData.pbwHid!=null){o.visible=o.userData.pbwHid;delete o.userData.pbwHid;}});}
