// node arcs.js out.json : every 1/60 s, world positions of the tracked points + the parent-relative layers
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const b=await chromium.launch({args:['--use-gl=swiftshader','--allow-file-access-from-files']});
const p=await b.newPage();await p.goto('file://'+__dirname+'/view.html');await p.waitForFunction('window.READY',null,{timeout:60000});
const r=await p.evaluate(()=>{const N=['Hips','Spine2','Head','RightArm','LeftArm','RightHand','LeftHand','WeaponTip_R','WeaponTip_L','RightFoot','LeftFoot'];
 const o={};S.traverse(x=>{if(N.includes(x.name))o[x.name]=x;});const out={t:[],p:{}};N.forEach(n=>out.p[n]=[]);
 // keyblade tips: the far end of each attached mesh along its +Y
 const tips={};S.traverse(x=>{if(x.userData&&x.userData.pbw)tips[x.userData.pbwSide]=x;});
 out.p.KTip_R=[];out.p.KTip_L=[];
 for(let i=0;i<=Math.round(LEN*60);i++){const t=i/60;action.time=t;mixer.update(0);S.updateMatrixWorld(true);out.t.push(t);
  N.forEach(n=>{const v=new THREE.Vector3();o[n].getWorldPosition(v);out.p[n].push([v.x,v.y,v.z]);});
  ['R','L'].forEach(s=>{const g=tips[s];const v=new THREE.Vector3(0,1.05,0);g.localToWorld(v);out.p['KTip_'+s].push([v.x,v.y,v.z]);});}
 return out;});
fs.writeFileSync(process.argv[2],JSON.stringify(r));await b.close();})();
