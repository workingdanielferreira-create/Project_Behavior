const $=id=>document.getElementById(id);const cv=$('cv'),ctx=cv.getContext('2d'),jsonEl=$('json');
let W,H;function rsz(){W=cv.width=cv.clientWidth;H=cv.height=cv.clientHeight}window.onresize=rsz;
const D=Math.PI/180,rnd=(a,b)=>a+Math.random()*(b-a),lerp=(a,b,t)=>a+(b-a)*t;
// ================= RIG =================
// pose keys: rx,ry root offset; sp spine; hd head; lua,lfa left upper/forearm; rua,rfa; lth,lsh legs; rth,rsh; wp weapon
const PK=['rx','ry','sp','sp2','hd','lsht','rsht','lpvt','rpvt','lua','lfa','rua','rfa','lth','lsh','rth','rsh','wp','luas','lfas','ruas','rfas','lths','lshs','rths','rshs'];
const Z={rx:0,ry:0,sp:0,sp2:0,hd:0,lsht:0,rsht:0,lpvt:0,rpvt:0,lua:15,lfa:5,rua:-15,rfa:-5,lth:8,lsh:5,rth:-8,rsh:-5,wp:-45,luas:1,lfas:1,ruas:1,rfas:1,lths:1,lshs:1,rths:1,rshs:1};
const P=o=>({...Z,...o});
const ACTIONS={swordsman:{
 idle:[{t:0,p:P({})},{t:.5,p:P({ry:2,sp:2})},{t:1,p:P({})}],
 slash:[{t:0,p:P({rua:-150,rfa:-40,wp:-50,sp:-10,rx:-10})},{t:.35,p:P({rua:-155,rfa:-45,wp:-55,sp:-12,rx:-14})},{t:.55,p:P({rua:35,rfa:25,wp:35,sp:14,rx:25,lth:25,rth:-30})},{t:1,p:P({})}],
 dash:[{t:0,p:P({rx:-150,sp:22,lth:-30,lsh:45,rth:35,rsh:10,lua:-40,rua:30})},{t:1,p:P({rx:150,sp:22,lth:35,lsh:10,rth:-30,rsh:45,lua:30,rua:-40})}],
 run:[{t:0,p:P({lth:-35,lsh:40,rth:30,rsh:8,lua:-30,rua:25,sp:6})},{t:.5,p:P({lth:30,lsh:8,rth:-35,rsh:40,lua:25,rua:-30,sp:6})},{t:1,p:P({lth:-35,lsh:40,rth:30,rsh:8,lua:-30,rua:25,sp:6})}]},
shooter:{
 idle:[{t:0,p:P({wp:0})},{t:.5,p:P({ry:2,wp:0})},{t:1,p:P({wp:0})}],
 fire:[{t:0,p:P({rua:-90,rfa:0,wp:0,sp:4})},{t:.12,p:P({rua:-100,rfa:-6,wp:-6,rx:-6,sp:0})},{t:.4,p:P({rua:-90,rfa:0,wp:0,sp:4})},{t:1,p:P({rua:-90,rfa:0,wp:0,sp:4})}],
 run:[{t:0,p:P({wp:0,lth:-35,lsh:40,rth:30,rsh:8,lua:-30,rua:-70,rfa:-20,sp:8})},{t:.5,p:P({wp:0,lth:30,lsh:8,rth:-35,rsh:40,lua:25,rua:-70,rfa:-20,sp:8})},{t:1,p:P({wp:0,lth:-35,lsh:40,rth:30,rsh:8,lua:-30,rua:-70,rfa:-20,sp:8})}],
 dash:[{t:0,p:P({wp:0,rx:-150,sp:22,lth:-30,lsh:45,rth:35,rsh:10})},{t:1,p:P({wp:0,rx:150,sp:22,lth:35,lsh:10,rth:-30,rsh:45})}]}};
let keyframes=[],selKF=-1,poseMode=false;
function poseAt(t){ // interpolate keyframes at t in 0..1
 if(!keyframes.length)return P({});
 const ks=keyframes;if(t<=ks[0].t)return{...ks[0].p};if(t>=ks[ks.length-1].t)return{...ks[ks.length-1].p};
 for(let i=0;i<ks.length-1;i++){if(t>=ks[i].t&&t<=ks[i+1].t){const f=(t-ks[i].t)/(ks[i+1].t-ks[i].t||1),o={};
  PK.forEach(k=>o[k]=lerp(ks[i].p[k],ks[i+1].p[k],f));return o}}return{...ks[0].p}}
const BONES0={ua:22,fa:20,th:26,sh:24,torso:36};
function boneLens(){return (appMode==='char'&&CH&&CH.bones)?CH.bones:BONES0}
// ================= TARGET DUMMY =================
// Movable target capsule with hitbox zones (head/torso/legs) + impact anchors.
// Used to author how effects apply to targets — identical semantics in Solo & Battle.
let DUMMY={x:140,y:2,h:100,w:34},dragDum=null;
function dummyOn(){const e=$('showdummy');return!!(e&&e.checked)}
function dummyGeom(){const cx=W/2,cy=H/2+40,X=cx+DUMMY.x,Y=cy+DUMMY.y,h=DUMMY.h,w=DUMMY.w,top=Y-h/2;
 const headB=top+h*0.22,torsoB=top+h*0.60,bot=top+h;
 return{X,Y,w,h,top,headB,torsoB,bot,head:[X,(top+headB)/2],torso:[X,(headB+torsoB)/2],legs:[X,(torsoB+bot)/2]}}
function dummyHit(wx,wy){const G=dummyGeom();return wx>G.X-G.w/2-6&&wx<G.X+G.w/2+6&&wy>G.top-6&&wy<G.bot+6}
function drawDummy(){const G=dummyGeom(),sc=1/cam.z;
 ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;ctx.shadowBlur=0;
 ctx.fillStyle='rgba(122,133,153,0.13)';ctx.strokeStyle=dragDum?'#ffd24a':'#7a8599';ctx.lineWidth=2*sc;
 ctx.beginPath();ctx.roundRect(G.X-G.w/2,G.top,G.w,G.h,G.w/2);ctx.fill();ctx.stroke();
 ctx.setLineDash([4*sc,3*sc]);ctx.lineWidth=1.2*sc;
 const zone=(y0,y1,c)=>{ctx.strokeStyle=c;ctx.strokeRect(G.X-G.w/2,y0,G.w,y1-y0)};
 zone(G.top,G.headB,'#ff7070');zone(G.headB,G.torsoB,'#ffd24a');zone(G.torsoB,G.bot,'#4ad0ff');
 ctx.setLineDash([]);
 [[G.head,'#ff7070'],[G.torso,'#ffd24a'],[G.legs,'#4ad0ff']].forEach(([p,c])=>{
  ctx.strokeStyle=c;ctx.lineWidth=1.4*sc;ctx.beginPath();
  ctx.moveTo(p[0]-5*sc,p[1]);ctx.lineTo(p[0]+5*sc,p[1]);ctx.moveTo(p[0],p[1]-5*sc);ctx.lineTo(p[0],p[1]+5*sc);ctx.stroke();
  ctx.beginPath();ctx.arc(p[0],p[1],3*sc,0,6.28);ctx.stroke()});
 ctx.fillStyle='#7a8599';ctx.font=(10*sc)+'px sans-serif';ctx.textAlign='center';
 ctx.fillText('TARGET',G.X,G.top-8*sc);ctx.textAlign='start';
 ctx.restore()}
function dummyExport(){if(!dummyOn())return null;
 return{enabled:true,offset_from_figure:[DUMMY.x,DUMMY.y],width:DUMMY.w,height:DUMMY.h,
  hitbox_zones:{head:[0,0.22],torso:[0.22,0.6],legs:[0.6,1]},
  impact_anchors:['dummy_head','dummy_torso','dummy_legs'],
  fire:(function(){const c=dummyFireCfg();return{enabled:dummyFireChecked(),rate_ms:c.rate_ms,damage:c.damage,speed:c.speed,
   note:'WIZARD PREVIEW ONLY: dummy mimics an enemy shooter so incoming-fire FX can be authored. Visual impacts only, no stats. NEVER implement in laser/ (Solo or Battle).'}})(),
  note:'Zone bounds are fractions of dummy height from top. Offset is from figure root. Applies identically in Solo & Battle. The target_dummy block (including fire) is a wizard preview aid only and must never be wired into the game engine.'}}
function dummyImport(td){if(!td||!td.enabled)return;const e=$('showdummy');if(e)e.checked=true;
 const of=td.offset_from_figure||[140,2];DUMMY.x=+of[0]||0;DUMMY.y=+of[1]||0;
 if(td.width)DUMMY.w=+td.width;if(td.height)DUMMY.h=+td.height;
 const f=td.fire;if(f){const c=$('dumfire');if(c)c.checked=!!f.enabled;
  if($('dumrate')&&f.rate_ms)$('dumrate').value=f.rate_ms;
  if($('dumdmg')&&f.damage!==undefined)$('dumdmg').value=f.damage;
  if($('dumspd')&&f.speed)$('dumspd').value=f.speed}}
// ---- [DUMMY FIRE] WIZARD PREVIEW ONLY ----
// The dummy mimics an enemy shooter (like a Battle-mode opponent) so incoming-fire FX/defense layers can be
// authored visually. Bullets deal NO stats damage: contact with the figure spawns a spark impact + floating
// damage number, purely visual. The dummy itself is invincible. Per standing rule, target_dummy (including
// this fire block) is NEVER implemented in laser/ for Solo or Battle modes.
let dumBullets=[],dumFloat=[],dumFireAcc=0;
function dummyFireChecked(){const e=$('dumfire');return!!(e&&e.checked)}
function dummyFireOn(){return dummyOn()&&dummyFireChecked()}
function dummyFireCfg(){return{
 rate_ms:Math.max(80,+(($('dumrate')||{}).value)||900),
 damage:Math.max(0,+(($('dumdmg')||{}).value)||0),
 speed:Math.max(40,+(($('dumspd')||{}).value)||320)}}
function figCenter(){if(curJ){const p=curJ.chest||curJ.torso_mid||curJ.hip;if(p)return[p[0],p[1]]}return[W/2,H/2+40-40]}
function figHit(wx,wy){if(!curJ)return false;let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9,n=0;
 for(const k in curJ){if(k[0]==='_'||k.slice(0,6)==='dummy_'||k==='enemy_target')continue;
  const p=curJ[k];if(!p||p.length<2)continue;
  x0=Math.min(x0,p[0]);y0=Math.min(y0,p[1]);x1=Math.max(x1,p[0]);y1=Math.max(y1,p[1]);n++}
 if(!n)return false;const pad=10;return wx>x0-pad&&wx<x1+pad&&wy>y0-pad&&wy<y1+pad}
function resetDummyFire(){dumBullets=[];dumFloat=[];dumFireAcc=0}
function updateDummyFire(dt){
 if(dummyFireOn()&&typeof playing!=='undefined'&&playing){const cfg=dummyFireCfg();dumFireAcc+=dt*1000;
  while(dumFireAcc>=cfg.rate_ms){dumFireAcc-=cfg.rate_ms;
   const[sx,sy]=dummyCenter(),tc=figCenter(),a=Math.atan2(tc[1]-sy,tc[0]-sx);
   dumBullets.push({x:sx,y:sy,vx:Math.cos(a)*cfg.speed,vy:Math.sin(a)*cfg.speed,dmg:cfg.damage,age:0})}}
 else dumFireAcc=0;
 for(let i=dumBullets.length-1;i>=0;i--){const b=dumBullets[i];b.x+=b.vx*dt;b.y+=b.vy*dt;b.age+=dt*1000;
  if($('showfig')&&$('showfig').checked&&figHit(b.x,b.y)){
   if(typeof spawnBFX==='function')spawnBFX('particles',{count:12,spread_deg:360,angle_deg:0,speed_min:40,speed_max:160,size_min:2,size_max:5,life_min:160,life_max:320,c1:'#ffd070',c2:'#ff4020',shape:'spark',burst:true,drag:0.94,gravity:0,glow:12},b.x,b.y);
   if(b.dmg>0)dumFloat.push({x:b.x,y:b.y-8,txt:'-'+b.dmg,age:0});
   dumBullets.splice(i,1);continue}
  if(b.age>4000)dumBullets.splice(i,1)}
 for(let i=dumFloat.length-1;i>=0;i--){const f=dumFloat[i];f.age+=dt*1000;f.y-=22*dt;if(f.age>700)dumFloat.splice(i,1)}}
function drawDummyFire(){if(!dumBullets.length&&!dumFloat.length)return;const sc=1/cam.z;ctx.save();
 ctx.globalCompositeOperation='lighter';
 for(const b of dumBullets){ctx.shadowBlur=12;ctx.shadowColor='#ff6a3c';ctx.fillStyle='#ffb27a';
  ctx.beginPath();ctx.arc(b.x,b.y,3.2,0,6.28);ctx.fill();
  const s=Math.hypot(b.vx,b.vy)||1,k=10/s;ctx.strokeStyle='#ff6a3c';ctx.lineWidth=1.6;
  ctx.beginPath();ctx.moveTo(b.x,b.y);ctx.lineTo(b.x-b.vx*k,b.y-b.vy*k);ctx.stroke()}
 ctx.globalCompositeOperation='source-over';ctx.shadowBlur=0;
 ctx.fillStyle='#ffd0a0';ctx.font=(11*sc)+'px sans-serif';ctx.textAlign='center';
 for(const f of dumFloat){ctx.globalAlpha=Math.max(0,1-f.age/700);ctx.fillText(f.txt,f.x,f.y)}
 ctx.globalAlpha=1;ctx.textAlign='start';ctx.restore()}
function joints(pose){ // world joint positions
 const cx=W/2,cy=H/2+40,J={},hip=[cx+pose.rx,cy+pose.ry];J.hip=hip;
 const B=(o,a,l)=>[o[0]+Math.cos(a)*l,o[1]+Math.sin(a)*l];
 const BL=boneLens();
 const spW=(-90+pose.sp)*D;J.torso_mid=B(hip,spW,BL.torso/2);
 const spW2=spW+(pose.sp2||0)*D;J.chest=B(J.torso_mid,spW2,BL.torso/2);
 const hdW=spW2+pose.hd*D;J.head=B(J.chest,hdW,16);
 J.r_shoulder=B(J.chest,spW2+Math.PI/2+pose.rsht*D,11);J.l_shoulder=B(J.chest,spW2-Math.PI/2+pose.lsht*D,11);
 J.r_hip=B(hip,pose.rpvt*D,8);J.l_hip=B(hip,Math.PI+pose.lpvt*D,8);
 const armBase=spW2+Math.PI;
 const luaW=armBase+pose.lua*D;J.l_elbow=B(J.l_shoulder,luaW,BL.ua*(pose.luas||1));
 const lfaW=luaW+pose.lfa*D;J.l_hand=B(J.l_elbow,lfaW,BL.fa*(pose.lfas||1));
 const ruaW=armBase+pose.rua*D;J.r_elbow=B(J.r_shoulder,ruaW,BL.ua*(pose.ruas||1));
 const rfaW=ruaW+pose.rfa*D;J.r_hand=B(J.r_elbow,rfaW,BL.fa*(pose.rfas||1));
 const lthW=(90+pose.lth)*D;J.l_knee=B(J.l_hip,lthW,BL.th*(pose.lths||1));J.l_foot=B(J.l_knee,(lthW+pose.lsh*D),BL.sh*(pose.lshs||1));
 const rthW=(90+pose.rth)*D;J.r_knee=B(J.r_hip,rthW,BL.th*(pose.rths||1));J.r_foot=B(J.r_knee,(rthW+pose.rsh*D),BL.sh*(pose.rshs||1));
 const fig=$('fig').value,wW=rfaW+pose.wp*D;J._wW=wW;J._rfaW=rfaW;J._spW=spW;J._spW2=spW2;J._luaW=luaW;J._lfaW=lfaW;J._ruaW=ruaW;J._hdW=hdW;
 if(fig==='swordsman'){J.blade_mid=B(J.r_hand,wW,19);J.blade_tip=B(J.r_hand,wW,38)}
 else if(fig==='custom'&&CH){const pts=wpnWorld(J.r_hand,wW);J._wpts=pts;
  J.weapon_tip=pts.length?pts[pts.length-1]:B(J.r_hand,wW,30);J.weapon_mid=pts.length?wpnMid(pts,J.r_hand):B(J.r_hand,wW,15)}
 else{J.muzzle=B(J.r_hand,wW,16)}
 if(dummyOn()){const G=dummyGeom();J.dummy_head=G.head;J.dummy_torso=G.torso;J.dummy_legs=G.legs}
 // enemy_target: always-available anchor = the opposing character's current position (previewed here via the
 // target dummy centre). A layer anchored here with follow=false spawns ONCE at that position and behaves
 // normally afterward (it does not keep tracking the enemy). Identical in Solo & Battle.
 const EG=dummyGeom();J.enemy_target=[EG.X,(EG.top+EG.bot)/2];
 return J}
const ANCHORS=()=>['point','hip','torso_mid','chest','head','l_shoulder','r_shoulder','l_hand','r_hand','l_foot','r_foot','enemy_target',...($('fig').value==='swordsman'?['blade_mid','blade_tip']:$('fig').value==='custom'?['weapon_mid','weapon_tip']:['muzzle']),...(dummyOn()?['dummy_head','dummy_torso','dummy_legs']:[])];
function drawBody(J,fig,alpha=1){ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha*=alpha;
 ctx.strokeStyle=(fig==='custom'&&CH)?CH.palette.body:'#8fa0b8';ctx.lineWidth=3.5;ctx.lineCap='round';
 const L=(a,b)=>{ctx.beginPath();ctx.moveTo(J[a][0],J[a][1]);ctx.lineTo(J[b][0],J[b][1]);ctx.stroke()};
 L('hip','torso_mid');L('torso_mid','chest');L('chest','l_shoulder');L('chest','r_shoulder');L('hip','l_hip');L('hip','r_hip');
 L('l_shoulder','l_elbow');L('l_elbow','l_hand');L('r_shoulder','r_elbow');L('r_elbow','r_hand');
 L('l_hip','l_knee');L('l_knee','l_foot');L('r_hip','r_knee');L('r_knee','r_foot');
 ctx.beginPath();ctx.arc(J.head[0],J.head[1]-4,10,0,6.28);ctx.stroke();
 ctx.restore()}
function drawWeapon(J,fig,alpha=1){ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha*=alpha;ctx.lineCap='round';
 const L=(a,b)=>{ctx.beginPath();ctx.moveTo(J[a][0],J[a][1]);ctx.lineTo(J[b][0],J[b][1]);ctx.stroke()};
 if(fig==='swordsman'){ctx.strokeStyle='#d8dee9';ctx.lineWidth=2.5;L('r_hand','blade_tip')}
 else if(fig==='custom'&&CH){const pts=J._wpts||[];
  if(pts.length){const wp=()=>{ctx.beginPath();ctx.moveTo(J.r_hand[0],J.r_hand[1]);pts.forEach(p=>ctx.lineTo(p[0],p[1]));ctx.stroke()};
   ctx.save();ctx.strokeStyle=CH.palette.accent;ctx.lineWidth=CH.weapon.thickness+3;ctx.shadowColor=CH.palette.accent;ctx.shadowBlur=8;ctx.globalAlpha*=0.55;wp();ctx.restore();
   ctx.strokeStyle=CH.weapon.color;ctx.lineWidth=CH.weapon.thickness;wp()}
  if(weaponEdit){ctx.globalAlpha=1;pts.forEach((p,i)=>{ctx.fillStyle=i===dragWP?'#ff4040':'#ffd050';ctx.beginPath();ctx.arc(p[0],p[1],4/Math.max(cam.z,0.5)+2,0,6.28);ctx.fill()});
   ctx.fillStyle=CH.palette.accent;ctx.beginPath();ctx.arc(J.r_hand[0],J.r_hand[1],3,0,6.28);ctx.fill();
   [['weapon_mid','#7fd'],['weapon_tip','#7fd']].forEach(([a,c])=>{if(J[a]){ctx.strokeStyle=c;ctx.lineWidth=1;ctx.beginPath();ctx.arc(J[a][0],J[a][1],6,0,6.28);ctx.stroke()}})}}
 else{ctx.strokeStyle='#d8dee9';ctx.lineWidth=4;L('r_hand','muzzle')}
 ctx.restore()}
function drawFigure(J,fig){drawBody(J,fig);drawWeapon(J,fig)}
function drawJointDots(J){if(!poseMode)return;ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
 for(const k in J){if(k[0]==='_'||k.slice(0,6)==='dummy_')continue;ctx.fillStyle=k===dragJ?'#ff4040':'#4af';
  ctx.beginPath();ctx.arc(J[k][0],J[k][1],4.5,0,6.28);ctx.fill()}
 ctx.restore()}
// --- built-in Character / Weapon layers (z-orderable in the layer stack) ---
const BUILTIN_TYPES=['figure','weapon'];
function isBI(l){return !!l&&BUILTIN_TYPES.includes(l.type)}
function ensureBuiltin(ls){if(!ls.some(l=>l.type==='figure'))ls.push({type:'figure',visible:true,opacity:1});
 if(!ls.some(l=>l.type==='weapon'))ls.push({type:'weapon',visible:true,opacity:1});return ls}
// joint→bone mapping for drag posing: [origin joint, worldBase fn(pose,J), poseKey]
const DRAGMAP={torso_mid:['hip',(p,J)=>-90*D,'sp'],chest:['torso_mid',(p,J)=>J._spW,'sp2'],head:['chest',(p,J)=>J._spW2,'hd'],
 r_shoulder:['chest',(p,J)=>J._spW2+Math.PI/2,'rsht'],l_shoulder:['chest',(p,J)=>J._spW2-Math.PI/2,'lsht'],
 r_hip:['hip',()=>0,'rpvt'],l_hip:['hip',()=>Math.PI,'lpvt'],
 l_elbow:['l_shoulder',(p,J)=>J._spW2+Math.PI,'lua',['luas',()=>boneLens().ua]],l_hand:['l_elbow',(p,J)=>J._luaW,'lfa',['lfas',()=>boneLens().fa]],
 r_elbow:['r_shoulder',(p,J)=>J._spW2+Math.PI,'rua',['ruas',()=>boneLens().ua]],r_hand:['r_elbow',(p,J)=>J._ruaW,'rfa',['rfas',()=>boneLens().fa]],
 l_knee:['l_hip',()=>90*D,'lth',['lths',()=>boneLens().th]],l_foot:['l_knee',(p,J)=>(90+p.lth)*D,'lsh',['lshs',()=>boneLens().sh]],
 r_knee:['r_hip',()=>90*D,'rth',['rths',()=>boneLens().th]],r_foot:['r_knee',(p,J)=>(90+p.rth)*D,'rsh',['rshs',()=>boneLens().sh]],
 blade_tip:['r_hand',(p,J)=>J._rfaW,'wp'],blade_mid:['r_hand',(p,J)=>J._rfaW,'wp'],muzzle:['r_hand',(p,J)=>J._rfaW,'wp'],weapon_tip:['r_hand',(p,J)=>J._rfaW,'wp'],weapon_mid:['r_hand',(p,J)=>J._rfaW,'wp']};
let dragJ=null,cam={z:1,x:0,y:0,init:false},panning=null,pivDrag=null;
const PIV_ARM=36;
function pivotGizmoOK(){return sel>=0&&fx.layers[sel]&&!isBI(fx.layers[sel])&&!weaponEdit&&!poseMode}
function drawPivotGizmo(){if(!pivotGizmoOK())return;const l=fx.layers[sel];
 const[x,y]=aPos(l),sc=1/cam.z,a=(l.prot||0)*D,hx=x+Math.cos(a)*PIV_ARM*sc,hy=y+Math.sin(a)*PIV_ARM*sc;
 ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;ctx.shadowBlur=0;
 ctx.strokeStyle=pivDrag==='rot'?'#ff4040':'#4ad0ff';ctx.lineWidth=1.5*sc;
 ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(hx,hy);ctx.stroke();
 ctx.fillStyle=pivDrag==='rot'?'#ff4040':'#4ad0ff';ctx.beginPath();ctx.arc(hx,hy,5*sc,0,6.28);ctx.fill();
 ctx.strokeStyle=pivDrag==='pos'?'#ff4040':'#ffd24a';
 ctx.beginPath();ctx.arc(x,y,8*sc,0,6.28);ctx.stroke();
 ctx.beginPath();ctx.moveTo(x-12*sc,y);ctx.lineTo(x+12*sc,y);ctx.moveTo(x,y-12*sc);ctx.lineTo(x,y+12*sc);ctx.stroke();
 if(l.type==='image'){const[sx,sy]=imgScaleHandle(l,x,y);
  ctx.fillStyle=pivDrag==='scale'?'#ff4040':'#8dff6a';
  ctx.fillRect(sx-5*sc,sy-5*sc,10*sc,10*sc)}
 ctx.restore()}
function imgScaleHandle(l,x,y){const half=Math.hypot(l.w0||64,l.h0||64)/2*(l.scale||1);
 const a=(l.prot||0)*D+Math.atan2(l.h0||64,l.w0||64);
 return[x+Math.cos(a)*half,y+Math.sin(a)*half]}
function pivotAnchorXY(l){let ax=W/2,ay=H/2;if(l.anchor&&l.anchor!=='point'&&curJ&&curJ[l.anchor])[ax,ay]=curJ[l.anchor];return[ax,ay]}
function pivotInfo(l){const pi=$('pivinfo');if(pi)pi.textContent=`x ${(l.px||0).toFixed(0)}  y ${(l.py||0).toFixed(0)}  rot ${Math.round(l.prot||0)}°`}
function resetPivot(){const l=fx.layers[sel];if(!l||isBI(l))return;l.px=0;l.py=0;l.prot=0;pivotInfo(l)}
function camInit(){if(!cam.init&&W){cam.x=W/2;cam.y=H/2;cam.init=true}}
function toWorld(mx,my){return[(mx-W/2)/cam.z+cam.x,(my-H/2)/cam.z+cam.y]}
cv.addEventListener('wheel',e=>{e.preventDefault();camInit();
 const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
 const[wx,wy]=toWorld(mx,my);const nz=Math.max(0.3,Math.min(6,cam.z*Math.pow(1.1,-e.deltaY/100)));
 cam.x=wx-(mx-W/2)/nz;cam.y=wy-(my-H/2)/nz;cam.z=nz},{passive:false});
function resetView(){cam.z=1;cam.x=W/2;cam.y=H/2}
cv.onmousedown=e=>{camInit();const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
 if(weaponEdit){const[wx,wy]=toWorld(mx,my);wpnClick(wx,wy);return}
 if(dummyOn()){const[wx,wy]=toWorld(mx,my);if(dummyHit(wx,wy)){dragDum=[wx-(W/2+DUMMY.x),wy-(H/2+40+DUMMY.y)];return}}
 if(poseMode&&selKF>=0){const[wx,wy]=toWorld(mx,my);
  const J=joints(keyframes[selKF].p);let best=null,bd=14/cam.z;
  for(const k in J){if(k[0]==='_'||k.slice(0,6)==='dummy_')continue;const d=Math.hypot(J[k][0]-wx,J[k][1]-wy);if(d<bd){bd=d;best=k}}
  dragJ=best;if(dragJ)return}
 if(pivotGizmoOK()){const l=fx.layers[sel],[wx,wy]=toWorld(mx,my),[x,y]=aPos(l),sc=1/cam.z,a=(l.prot||0)*D;
  if(l.type==='image'){const[sx,sy]=imgScaleHandle(l,x,y);if(Math.hypot(wx-sx,wy-sy)<9*sc){pivDrag='scale';return}}
  const hx=x+Math.cos(a)*PIV_ARM*sc,hy=y+Math.sin(a)*PIV_ARM*sc;
  if(Math.hypot(wx-hx,wy-hy)<9*sc){pivDrag='rot';return}
  if(Math.hypot(wx-x,wy-y)<12*sc){pivDrag='pos';return}}
 panning=[mx,my]};
cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
 if(dragDum){const[wx,wy]=toWorld(mx,my);DUMMY.x=+(wx-W/2-dragDum[0]).toFixed(1);DUMMY.y=+(wy-(H/2+40)-dragDum[1]).toFixed(1);return}
 if(pivDrag&&sel>=0&&fx.layers[sel]){const l=fx.layers[sel],[wx,wy]=toWorld(mx,my),[ax,ay]=pivotAnchorXY(l);
  if(pivDrag==='pos'){l.px=+(wx-ax).toFixed(1);l.py=+(wy-ay).toFixed(1)}
  else if(pivDrag==='scale'){const d=Math.hypot(wx-(ax+(l.px||0)),wy-(ay+(l.py||0)));
   l.scale=+Math.max(0.05,Math.min(10,d/(Math.hypot(l.w0||64,l.h0||64)/2))).toFixed(3)}
  else{l.prot=Math.round(Math.atan2(wy-(ay+(l.py||0)),wx-(ax+(l.px||0)))/D)}
  pivotInfo(l);return}
 if(weaponEdit&&dragWP>=0){const[wx,wy]=toWorld(mx,my);CH.weapon.points[dragWP]=wpnLocal(wx,wy);return}
 if(panning){cam.x-=(mx-panning[0])/cam.z;cam.y-=(my-panning[1])/cam.z;panning=[mx,my];return}
 if(!dragJ||selKF<0)return;const[wx,wy]=toWorld(mx,my);
 const kp=keyframes[selKF].p;
 if(dragJ==='hip'){kp.rx=wx-W/2;kp.ry=wy-(H/2+40);return}
 const m=DRAGMAP[dragJ];if(!m)return;const J=joints(kp);const o=J[m[0]];
 const wa=Math.atan2(wy-o[1],wx-o[0]);kp[m[2]]=(wa-m[1](kp,J))/D;
 while(kp[m[2]]>180)kp[m[2]]-=360;while(kp[m[2]]<-180)kp[m[2]]+=360;
 if(m[3]){const dist=Math.hypot(wx-o[0],wy-o[1]);kp[m[3][0]]=Math.max(0.5,Math.min(1.8,+(dist/m[3][1]()).toFixed(3)))}};
cv.onmouseup=()=>{dragJ=null;panning=null;dragWP=-1;dragDum=null;if(pivDrag){pivDrag=null;renderProps()}};cv.onmouseleave=()=>{dragJ=null;panning=null;dragWP=-1;dragDum=null;if(pivDrag){pivDrag=null;renderProps()}};
