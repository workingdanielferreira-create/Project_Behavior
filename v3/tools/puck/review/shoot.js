// node shoot.js times.json out_dir   -> out_dir/<i>_<view>.png
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [tf,out]=process.argv.slice(2);const T=JSON.parse(fs.readFileSync(tf));fs.mkdirSync(out,{recursive:true});
const b=await chromium.launch({args:['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist','--allow-file-access-from-files']});
const p=await b.newPage({viewport:{width:520,height:560}});p.on('console',m=>console.log('pg:',m.text()));
await p.goto('file://'+__dirname+'/view.html');await p.waitForFunction('window.READY',null,{timeout:60000});
const h0=await p.evaluate('hipsAt(0)'),h1=await p.evaluate('hipsAt(LEN)');const cz=(h0[2]+h1[2])/2;
for(let i=0;i<T.times.length;i++){for(const v of T.views){const hz=(await p.evaluate(t=>hipsAt(t),T.times[i]))[2];const d=await p.evaluate(([t,v,cz])=>shot(t,v,0,cz),[T.times[i],v,hz*0.7+cz*0.3]);
 fs.writeFileSync(`${out}/${i}_${v}.png`,Buffer.from(d.split(',')[1],'base64'));}}
console.log('hips',h0,h1);await b.close();})();
