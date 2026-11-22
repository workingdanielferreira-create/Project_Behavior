'use strict';
/* Renderer: WebGL setup, scene, lights, toon / ink / additive materials, 2D ground (x, y) + height -> 3D (V, VA). */
/* ================= renderer ================= */
const host=$('game'),cvs=$('gl');
const renderer=new THREE.WebGLRenderer({canvas:cvs,antialias:true});
const scene=new THREE.Scene();scene.background=new THREE.Color(0x141834);scene.fog=new THREE.Fog(0x161a38,90,300);
const cam=new THREE.PerspectiveCamera(38,16/9,.1,400);cam.position.set(0,20,26);
function resize(){const r=host.getBoundingClientRect();if(!r.width)return;renderer.setSize(r.width,r.height,false);cam.aspect=r.width/r.height;cam.updateProjectionMatrix();}
if('ResizeObserver' in window)new ResizeObserver(resize).observe(host);resize();
scene.add(new THREE.HemisphereLight(0xb0c0ff,0x201018,.8));const sun=new THREE.DirectionalLight(0xffffff,.8);sun.position.set(-10,20,10);scene.add(sun);
const gd=new Uint8Array([60,60,60,255,140,140,140,255,255,255,255,255]);const grad=new THREE.DataTexture(gd,3,1,THREE.RGBAFormat);grad.minFilter=grad.magFilter=THREE.NearestFilter;grad.needsUpdate=true;
const toon=c=>new THREE.MeshToonMaterial({color:c,gradientMap:grad});
const ink=new THREE.MeshBasicMaterial({color:0x04050b,side:THREE.BackSide});
function inked(g,m,s){const a=new THREE.Mesh(g,m);const b=new THREE.Mesh(g,ink);b.scale.setScalar(s||1.12);a.add(b);return a;}
const add=(c,o)=>new THREE.MeshBasicMaterial({color:c,transparent:true,opacity:o==null?1:o,blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.DoubleSide});
// FX are placed by ground (x, y) + a height in units; anything above knee height rides the altitude of the
// fighter standing there (FXF = the fighter whose action is spawning FX wins a tie).
let FXF=null;
function altAt(x,y){let best=null,bd=1e9;for(const sd of (typeof sides!=='undefined'?sides:[])){const f=sd.team[sd.on];if(!f||!f.on)continue;const d=Math.hypot(f.x-x,f.y-y);if(d<80){if(f===FXF)return f.z;if(d<bd){bd=d;best=f;}}}return best?best.z:0;}
const V=(x,y,h)=>new THREE.Vector3((x-W/2)*K,(h||0)+((h||0)>.3?altAt(x,y)*K:0),(y-H/2)*K);
const VA=(x,y,z,h)=>new THREE.Vector3((x-W/2)*K,(h||0)+z*K,(y-H/2)*K);
// Render resolution (Settings > Quality): high = up to 2x on high-DPI screens.
function applyQuality(){renderer.setPixelRatio(settings.quality==='low'?.75:settings.quality==='medium'?1:Math.min(2,devicePixelRatio||1));resize();}
