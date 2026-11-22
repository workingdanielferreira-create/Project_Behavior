'use strict';
/* Character kits. hits: [atMs, dmg, weight L/M/H/B, reach px], lunge: [atMs, px], fx: [atMs, type, arg] (fxlib.js runs the type). */
/* ================= kits ================= */
// hits: [atMs, dmg, weight(L/M/H/B), reach px], lunge: [atMs, px] (snap forward), fx: [atMs, type, arg]
const KITS={
 // ---- Hooded Blades: REAL kit (characters/hooded_blades/hooded_blades.fxkit.json) ----
 // action lengths = timing frames x frame_ms; damage = each effect's battle.damage; conditions, rhythm, dodge,
 // movement style and berserker bonus from the file. Only the 3D look of each FX is new.
 blades:{key:'blades',name:'HOODED BLADES',short:'HB',real:true,col:0xd8324a,acc:0x232842,fx:0xf4f8ff,fx2:0x6a3fd0,core:0xffffff,hp:2500,melee:true,reach:150,speed:260,blink:.35,
  react:{kind:'sidestep',p:1,cd:0,dist:108,trig:140,shotsOnly:true,counter:'normal2'},gate:true,
  t:{neutral:[250,900],feint:8,string:[4,8],gap:[260,50],spacing:60,reset:140,resetMs:[200,600],aggr:1.4,mom:.35,punish:85},
  style:'blades',berserk:{maxLost:.6,bonus:3,steps:5},entrance:'oath',entranceDmg:30,
  normals:[
   {n2d:'attack_normal',dur:500,hits:[[180,40,'M',150]],fx:[[30,'arcmove',80],[170,'oath',3.6]]},
   {n2d:'attack_normal_2',dur:700,hits:[[50,40,'M',190],[180,40,'L',190]],fx:[[0,'starburst',195]]},
   {n2d:'attack_normal_3',dur:800,hits:[[220,40,'M',150],[360,40,'M',150]],fx:[[0,'arcmove',65],[200,'pierce',0],[340,'oath',3.4]]},
   {n2d:'attack_normal_4',dur:602,hits:[[330,40,'M',150]],fx:[[0,'bf',0],[300,'pierce',0]]},
   {n2d:'attack_normal_5',dur:806,hits:[[500,40,'H',170]],fx:[[0,'leapto',200],[480,'satellite',0]]}],
  special:{n2d:'attack_special',name:'Starburst',cd:0,mcd:2500,dur:700,hits:[],fx:[[0,'leapto',100],[160,'starfield',160]]},
  special2:{n2d:'attack_special_2',name:'Blade hop chain',cd:0,mcd:3000,dur:500,armor:1,hits:[],fx:[[0,'oath',3.6],[20,'hopchain',0]]},
  ult:{n2d:'ultimate',name:'Sword Graveyard',cd:0,mcd:15000,dur:2000,armor:2,hits:[],fx:[[110,'graveyard',16],[1330,'flare',0]]},
  defend:{n2d:'defend',dur:674,hits:[],fx:[]},
  triggers:[
   {slot:'ult',conds:[['hp_below',50],['hp_below',30],['hp_below',10]]},
   {slot:'defend',conds:[['target_act','ult',300],['damage_taken',500,1000]]},
   {slot:'special2',conds:[['blade_near',60],['self_act','attack_special',300]]},
   {slot:'special',cd:200,conds:[['every_ms',5000],['self_act','attack_normal_5',300]]}]},
 // ---- Sueko: REAL kit (characters/Sueko/*.fxkit.json): no fight rhythm (movement style drives her) ----
 sueko:{key:'sueko',name:'SUEKO',short:'SK',real:true,col:0xf2f4f6,acc:0x3fb0ea,fx:0x7fd8ff,core:0xffffff,hp:2000,melee:true,reach:100,speed:300,blink:0,
  rhythm:false,react:{kind:'sidestep',p:1,cd:0,dist:108,trig:80,shotsOnly:true},
  t:{neutral:[300,900],feint:0,string:[1,1],gap:[300,150],spacing:30,reset:200},
  style:'sueko',forms:[{at:.6,spd:2,dmg:2,taken:.8,col:0x27ec73,acc:0xff3a3a,aura:0xff3a3a},{at:.3,spd:3,dmg:3,taken:.5,col:0x1ff0ff,acc:0x3aff7a,aura:0x3aff7a}],
  retreat:{hp:300,ms:2000,cd:600,dur:500},entrance:'axe',entranceDmg:50,
  normals:[{n2d:'attack_normal',dur:400,hits:[[100,5,'M',110,320]],lunge:[[0,50]],fx:[[90,'impact',0],[200,'hopback',150]]}],
  special:{n2d:'attack_special',name:'Serious punch',cd:0,mcd:3500,dur:900,armor:1,hits:[],fx:[[0,'seriouscharge',512],[512,'serious',30]]},
  special2:{n2d:'attack_special_2',name:'Ki barrage',cd:0,mcd:3000,dur:1100,hits:[],fx:[[0,'kistream',15]]},
  ult:{n2d:'ultimate',name:'Gigantic meteor',cd:0,mcd:12000,dur:2100,armor:1,hits:[],fx:[[0,'meteor',20]]},
  transform:{n2d:'transform',dur:3000,hits:[],fx:[[0,'transform',0]]},
  triggers:[
   {slot:'ult',conds:[['every_ms',8750]]},
   {slot:'special',conds:[['every_ms',5000]]},
   {slot:'special2',conds:[['proj_count',10],['target_beyond',800]]}]},
 ronin:{name:'RONIN',short:'RO',col:0x6a54a8,acc:0xc9b27a,fx:0xb9a0ff,core:0xffffff,hp:2000,melee:true,reach:90,speed:240,blink:.15,react:{kind:'parry',p:.3},
  t:{neutral:[350,1200],feint:25,string:[3,7],gap:[340,70],spacing:35,reset:150},
  normals:[
   {dur:260,hits:[[110,36,'L',105]],lunge:[[20,60]],fx:[[100,'slash',3.4]]},
   {dur:260,hits:[[110,36,'L',105]],lunge:[[20,60]],fx:[[100,'slash',3.6]]},
   {dur:320,hits:[[150,50,'M',110]],lunge:[[40,110]],fx:[[140,'slash',4.4]]},
   {dur:420,hits:[[200,66,'H',115]],lunge:[[60,70]],fx:[[190,'slash',5.2]]}],
  special:{name:'Dash slash',cd:3400,dur:420,hits:[[150,70,'M',520]],fx:[[120,'dashslash',380]]},
  special2:{name:'Moonfall',cd:5200,dur:620,armor:1,hits:[],fx:[[60,'moon',0]]},
  ult:{name:'Cross-cut',cd:22000,dur:1300,armor:1,hits:[[350,60,'M',0],[600,60,'M',0],[850,60,'M',0],[1100,130,'B',0]],fx:[[100,'vanish',0],[340,'cut',0],[590,'cut',0],[840,'cut',0],[1090,'xcut',0]]}},
 gunner:{name:'GUNNER',short:'GN',col:0x2f8fd6,acc:0x1a2d4a,fx:0x9fe0ff,core:0xe8f8ff,hp:1600,melee:false,reach:420,speed:520,blink:.35,react:{kind:'dodge',p:.12},
  t:{neutral:[600,1600],feint:20,string:[4,7],gap:[260,110],spacing:220,reset:300},
  normals:[
   {dur:300,hits:[],fx:[[60,'shot',24],[150,'shot',24],[240,'shot',24]]},
   {dur:260,hits:[],fx:[[80,'shot',30],[180,'shot',30]]},
   {dur:340,hits:[],fx:[[120,'bigshot',60]]}],
  special:{name:'Spread',cd:3600,dur:380,hits:[],fx:[[120,'spread',26]]},
  special2:{name:'Rail',cd:5200,dur:700,armor:1,hits:[],fx:[[260,'rail',140]]},
  ult:{name:'Barrage',cd:22000,dur:1600,armor:1,hits:[],fx:[[100,'barrage',22]]}},
 puck:{name:'PUCK',short:'PK',col:0xf08a24,acc:0x1d2a5a,fx:0xffd24a,core:0xfff6c8,hp:1800,melee:true,reach:85,speed:330,blink:.25,react:{kind:'sidestep',p:.7,cd:700},entrance:'axe',
  t:{neutral:[100,400],feint:8,string:[4,12],gap:[100,50],spacing:40,reset:300,resetMs:[200,400],aggr:4,mom:1.05,punish:85},
  normals:[
   {dur:260,hits:[[110,30,'M',100]],lunge:[[0,90]],fx:[[100,'kick',3.2],[170,'hopback',150]]},
   {dur:190,hits:[[80,22,'L',88]],lunge:[[0,50]],fx:[[75,'punch',2.6]]},
   {dur:200,hits:[[85,24,'L',88]],lunge:[[0,50]],fx:[[80,'punch',2.8]]},
   {dur:360,hits:[[280,52,'H',115]],lunge:[[60,120]],fx:[[40,'hop',0],[270,'slam',4.2]]}],
  special:{name:'Charged laser',cd:3200,dur:640,armor:1,hits:[],fx:[[0,'charge',300],[300,'laser',85]]},
  special2:{name:'Ki barrage',cd:5200,dur:1050,hits:[],fx:[[60,'kibarrage',14]]},
  ult:{name:'Full-power beam',cd:22000,dur:1650,armor:2,hits:[],fx:[[0,'charge',550],[550,'kame',0]]}},
 tough:{name:'TOUGH',short:'TG',col:0xd49a2c,acc:0x5a3b16,fx:0xffc857,core:0xfff2cc,hp:2600,melee:true,reach:75,speed:210,blink:0,react:{kind:'block',p:.35},
  t:{neutral:[600,1600],feint:15,string:[3,5],gap:[340,110],spacing:35,reset:140},
  normals:[
   {dur:300,hits:[[140,42,'M',90]],lunge:[[40,50]],fx:[[130,'punch',3]]},
   {dur:320,hits:[[150,42,'M',90]],lunge:[[40,50]],fx:[[140,'punch',3.2]]},
   {dur:460,hits:[[240,80,'H',100]],lunge:[[80,60]],fx:[[230,'slam',4]]}],
  special:{name:'Chain pull',cd:3000,dur:450,hits:[[180,50,'M',520]],fx:[[170,'chain',0]]},
  special2:{name:'Repulse nova',cd:5000,dur:700,armor:2,hits:[[320,90,'B',260]],fx:[[310,'nova',260]]},
  ult:{name:'Fortress slam',cd:22000,dur:1100,armor:2,hits:[[700,220,'B',330]],fx:[[100,'leap',0],[690,'bigslam',330]]}}
};
// Alternate colours for a character that is on BOTH teams (the enemy copy).
const ALT={sueko:{col:0x3a3a48,fx:0xff6a6a,core:0xfff0f0},puck:{col:0x2fb38a,fx:0x7dffc8,core:0xe8fff6},blades:{col:0x8a2f9e,fx:0xe08aff,core:0xf8e8ff},ronin:{col:0xb0423a,fx:0xff8a70,core:0xfff0e8},gunner:{col:0x9b4fd6,fx:0xd9a0ff,core:0xf6e8ff},tough:{col:0x5a8a3a,fx:0xb8ff7a,core:0xf2ffe8}};
// Names shown on the team-select screen.
const NAMES={puck:'Puck',blades:'Hooded Blades',sueko:'Sueko',ronin:'Ronin',gunner:'Gunner',tough:'Tough'};
const ROLES={blades:'Real kit · blink blade duelist',sueko:'Real kit · forms, ki and meteor',puck:'Rush brawler · laser and beam',ronin:'Iaido swordsman · parries',gunner:'Ranged · kites and barrages',tough:'Heavy · blocks and slams'};
