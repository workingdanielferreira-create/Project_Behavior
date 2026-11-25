const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [ts,out]=process.argv.slice(2);const b=await chromium.launch({args:['--use-gl=swiftshader','--allow-file-access-from-files']});
const p=await b.newPage({viewport:{width:520,height:560}});await p.goto('file://'+__dirname+'/view.html');await p.waitForFunction('window.READY');
let i=0;for(const t of ts.split(',').map(Number)){for(const [bn,dx,dy,dz] of [['RightHand',-0.5,0.1,0.1],['RightHand',-0.2,0.5,0.4],['RightHand',0.1,0.1,0.55]]){
const d=await p.evaluate(([t,bn,dx,dy,dz])=>handShot(t,bn,dx,dy,dz),[t,bn,dx,dy,dz]);fs.writeFileSync(`${out}_${i++}.png`,Buffer.from(d.split(',')[1],'base64'));}}
await b.close();})();