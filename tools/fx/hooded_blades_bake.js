// Bake characters/hooded_blades with Rig Forge's OWN package export.
//
// Loads tools/fx/rigforge.html in headless Chromium, puts the pose source
// (tools/fx/sources/HoodedBlades_rigforge.json, written by hooded_blades_poses.py)
// into Rig Forge's state, and runs pkgBuildPkg(): the same code path as
// "Export character package..." on an imported package.  So the frames, the
// per-frame anchors and the embedded "rigforge" block (rig + every keyframe)
// are exactly what Rig Forge writes, and Rig Forge's "Import package..."
// reopens the character with all its keys, tweens, holds and layer orders.
//
// usage: node tools/fx/hooded_blades_bake.js [out_dir]
//        (default out_dir = characters/hooded_blades)
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const HERE = __dirname;
const ROOT = path.resolve(HERE, "..", "..");
const SRC = path.join(HERE, "sources", "HoodedBlades_rigforge.json");
const OUT = path.resolve(process.argv[2] || path.join(ROOT, "characters", "hooded_blades"));
const HEAD_PX = 64;          // render resolution (head diameter in px), like the other rig packages
const COLOUR = "#2b2f45";    // figure silhouette colour

(async () => {
  const src = JSON.parse(fs.readFileSync(SRC, "utf8"));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.error("page error:", e.message));
  // Fonts only style the UI; a blocked font request would hold back the page scripts.
  await page.route(/^https?:\/\//, (r) => r.abort());
  // Rig Forge's code is one closure; load an in-memory copy (the file on disk is
  // untouched) with a hook at the end of the closure exposing what the export uses.
  const html = fs.readFileSync(path.join(HERE, "rigforge.html"), "utf8");
  const end = html.lastIndexOf("})();");
  if (end < 0) throw new Error("rigforge.html: closure end not found");
  const hook = "window.__RF={get S(){return S;},RIGDEF:RIGDEF,clone:clone,xlSync:xlSync,newPose:newPose," +
    "normPose:normPose,PKEYS:PKEYS,pkgCamera:pkgCamera,pkgBuildPkg:pkgBuildPkg};\n";
  await page.setContent(html.slice(0, end) + hook + html.slice(end), { waitUntil: "load" });
  await page.waitForFunction(() => !!window.__RF);
  const res = await page.evaluate(({ src, HEAD_PX, COLOUR }) => {
    const { S, RIGDEF, clone, xlSync, newPose, normPose, PKEYS, pkgCamera, pkgBuildPkg } = window.__RF;
    const pv = src.rig.pivots;
    S.rig = Object.assign(clone(RIGDEF), src.rig.bones, {
      shx: pv.shoulder_x, shy: pv.shoulder_y, hipx: pv.hip_x, hipy: pv.hip_y, sep: pv.side_separation,
      wd: clone(src.rig.widths), wdsep: false, xl: clone(src.rig.lines), xa: [],
      w1at: src.weapon.attach, w2at: src.weapon2.attach, w1wt: 0, w2wt: 0,
    });
    S.weapon = clone(src.weapon.points);
    S.weapon2 = clone(src.weapon2.points);
    xlSync();
    ["name", "display_name", "description", "archetype"].forEach((k) => (S.meta[k] = src[k]));
    S.meta.predicates = clone(src.predicates);
    S.meta.movement = clone(src.movement);
    S.meta.stats = clone(src.stats);
    S.meta.palette = clone(src.palette);
    const acts = {};
    Object.keys(src.actions).forEach((k) => {
      const a = src.actions[k];
      acts[k] = {
        name: k, duration_ms: a.duration_ms, trigger: a.trigger, retrigger_cooldown_ms: a.retrigger_cooldown_ms || 0,
        keyframes: a.keyframes.map((p) => {
          const q = newPose();
          PKEYS.forEach((k2) => { if (typeof p[k2] === "number") q[k2] = p[k2]; });
          q._xl = clone(p._xl || {});
          q._tween = clone(p._tween);
          q._layers = clone(p._layers);
          if (p._note) q._note = p._note;
          return normPose(q);
        }),
      };
    });
    S.actions = acts; S.cur = "idle"; S.kf = 0;
    document.getElementById("pk_col").value = COLOUR;
    document.getElementById("pk_travel").checked = true;
    const cam = pkgCamera(HEAD_PX, true);
    S.meta.pkg = { ppu: cam.ppu, cx: cam.cx, cy: cam.cy, size: [cam.size, cam.size], head_px: HEAD_PX, colour: COLOUR };
    const r = pkgBuildPkg();
    // layer orders as Rig Forge normalised them (sanity: every x: line kept)
    const lost = [];
    Object.keys(S.actions).forEach((k) => S.actions[k].keyframes.forEach((p, i) => {
      ["x:hood", "x:coat_b", "x:coat_f"].forEach((id) => { if (p._layers.order.indexOf(id) < 0) lost.push(k + "#" + i + " " + id); });
    }));
    return {
      manifest: r.manifest, lost,
      files: r.files.map((f) => ({ name: f.name, data: f.canvas.toDataURL("image/png") })),
    };
  }, { src, HEAD_PX, COLOUR });
  await browser.close();
  if (res.lost.length) { console.error("layers dropped by Rig Forge:", res.lost); process.exit(1); }

  fs.mkdirSync(OUT, { recursive: true });
  // clear old frames of this character only
  fs.readdirSync(OUT).filter((f) => f.endsWith(".png")).forEach((f) => fs.unlinkSync(path.join(OUT, f)));
  res.files.forEach((f) => fs.writeFileSync(path.join(OUT, f.name), Buffer.from(f.data.split(",")[1], "base64")));
  const man = res.manifest;
  man.note = "Rig Forge rig, baked by tools/fx/hooded_blades_bake.js through Rig Forge's own package export " +
    "(pose source: tools/fx/hooded_blades_poses.py). Frames face right; the image centre (origin_px) is the " +
    "figure's position in-game; anchors are image px per frame. \"rigforge\" holds the rig and keyframes so " +
    "Rig Forge's Import package... reopens it exactly. No FX file yet: build FX in FX Studio.";
  fs.writeFileSync(path.join(OUT, "character.json"), JSON.stringify(man, null, 1));
  const counts = Object.keys(man.actions).map((k) => k + ":" + man.actions[k].frames.length).join(" ");
  console.log("wrote", res.files.length, "frames to", OUT, "size", man.image.size.join("x"));
  console.log(counts);
})().catch((e) => { console.error(e); process.exit(1); });
