// World Camera — FX Studio's port of laser/camera.py.
//
// The dynamic action camera: a paint-time VIEW only (the game never moves a
// fighter for it).  Follow-cam frames every fielded fighter and eases there
// (Battle zooms in up to max_zoom when the fight is tight, Solo follows at a
// light fixed solo_zoom; never below 1.0x, never off-screen); a hit-stop
// punches in toward the impact with a roll along the knockback; every
// screen shake adds trauma (amplitude = shake_max_px * trauma^2, smooth
// noise), so overlapping hits stack.  Saved as camera.json (format
// pb_camera), read by the game from characters/camera.json and hot-reloaded
// about once a second.  tools/fx/check_parity.py checks CAM_DEFAULTS /
// CAM_RANGES / CAM_FORMAT against the game.
(function () {
"use strict";
var CAM_FORMAT = "pb_camera";
var CAM_DEFAULTS = {
  "follow": true, "punch": true, "shake": true,
  "max_zoom": 1.6, "solo_zoom": 1.15, "follow_s": 0.4, "margin_x_px": 220.0, "margin_y_px": 220.0,
  "punch_zoom": 0.3, "punch_tilt_deg": 3.0, "punch_pull": 0.6, "punch_in_ticks": 3, "punch_out_s": 0.35,
  "shake_max_px": 16.0, "shake_hz": 18.0,
  "ult_on": true, "ult_zoom": 2.3, "ult_in_s": 0.6, "ult_max_s": 1.5, "ult_out_s": 0.5,
  "switch_on": true, "switch_zoom": 1.8, "switch_in_s": 0.15, "switch_hold_s": 0.5, "switch_out_s": 0.4,
  "ko_on": true, "ko_zoom": 2.5, "ko_in_s": 0.2, "ko_hold_s": 1.0, "ko_out_s": 0.6, "ko_slow": 0.25, "ko_slow_s": 0.9,
  "clash_on": true, "clash_zoom": 2.0, "clash_in_s": 0.08, "clash_hold_s": 0.3, "clash_out_s": 0.35,
  "depth": true, "depth_base": 0.10, "depth_gain": 0.20, "depth_shot": 0.15, "depth_budget_ms": 14.0,
  "anchor_scale": true, "anchor_s": 0.3, "anchor_fixed": false, "anchor_zoom": 1.15, "anchor_view_x_frac": 0.5, "anchor_view_y_frac": 0.5,
  "vscale_bottom": 5.0, "vscale_top": 1.0, "dscale_near": 1.0, "dscale_far": 0.10,
  "dscale_far_x_frac": 0.5, "dscale_far_y_frac": 0.5, "dscale_curve": 1.0, "scale_min": 0.10, "scale_max": 5.0,
  "speed_min": 0.40, "speed_max": 1.00,
  "planet": true, "planet_reach_x_frac": 0.6, "planet_reach_y_frac": 0.6, "planet_horizon_deg": 80.0, "planet_far": 0.15, "planet_squash": 0.85,
  "planet_ball": true, "planet_ball_radius_frac": 1.5, "planet_ball_top_frac": 0.15, "planet_ball_cols": 64, "planet_ball_bands": 3,
  "wireframe": false
};
var CAM_RANGES = {
  "max_zoom": [1.0, 3.0], "solo_zoom": [1.0, 3.0], "follow_s": [0.02, 5.0], "margin_x_px": [0.0, 1000.0], "margin_y_px": [0.0, 1000.0],
  "punch_zoom": [0.0, 1.5], "punch_tilt_deg": [0.0, 30.0], "punch_pull": [0.0, 1.0],
  "punch_in_ticks": [1, 30], "punch_out_s": [0.02, 5.0],
  "shake_max_px": [0.0, 100.0], "shake_hz": [1.0, 60.0],
  "ult_zoom": [1.0, 4.0], "ult_in_s": [0.02, 5.0], "ult_max_s": [0.0, 10.0], "ult_out_s": [0.02, 5.0],
  "switch_zoom": [1.0, 4.0], "switch_in_s": [0.02, 5.0], "switch_hold_s": [0.0, 10.0], "switch_out_s": [0.02, 5.0],
  "ko_zoom": [1.0, 4.0], "ko_in_s": [0.02, 5.0], "ko_hold_s": [0.0, 10.0], "ko_out_s": [0.02, 5.0],
  "ko_slow": [0.05, 1.0], "ko_slow_s": [0.0, 5.0],
  "clash_zoom": [1.0, 4.0], "clash_in_s": [0.02, 5.0], "clash_hold_s": [0.0, 10.0], "clash_out_s": [0.02, 5.0],
  "depth_base": [0.0, 0.6], "depth_gain": [0.0, 0.6], "depth_shot": [0.0, 0.6],
  "depth_budget_ms": [4.0, 60.0],
  "anchor_s": [0.02, 5.0], "anchor_zoom": [1.0, 3.0],
  "anchor_view_x_frac": [0.0, 1.0], "anchor_view_y_frac": [0.0, 1.0],
  "vscale_bottom": [0.1, 10.0], "vscale_top": [0.1, 10.0],
  "dscale_near": [0.05, 2.0], "dscale_far": [0.05, 2.0],
  "dscale_far_x_frac": [0.1, 1.5], "dscale_far_y_frac": [0.1, 1.5], "dscale_curve": [0.2, 5.0],
  "scale_min": [0.05, 10.0], "scale_max": [0.05, 10.0],
  "speed_min": [0.05, 2.0], "speed_max": [0.05, 2.0],
  "planet_reach_x_frac": [0.1, 2.0], "planet_reach_y_frac": [0.1, 2.0], "planet_horizon_deg": [10.0, 90.0],
  "planet_far": [0.05, 1.0], "planet_squash": [0.0, 0.95],
  "planet_ball_radius_frac": [0.3, 5.0], "planet_ball_top_frac": [0.0, 0.9],
  "planet_ball_cols": [16, 192], "planet_ball_bands": [1, 8]
};
// Settings split into x / y: an old file's single value seeds both.
var CAM_LEGACY_XY = {"margin_px": ["margin_x_px", "margin_y_px"],
  "dscale_far_frac": ["dscale_far_x_frac", "dscale_far_y_frac"],
  "planet_reach_frac": ["planet_reach_x_frac", "planet_reach_y_frac"]};
// Wireframe overlay toggles (laser/camera.py WIRE_KEYS): camera.json
// "wire_off" lists the keys whose part of the wireframe is hidden.  Camera
// settings, two wireframe-only parts and "section.key" Dust & Air settings;
// a part with several owners hides when ANY of them is unticked.
var CAM_WIRE_KEYS = [
  "follow", "margin_x_px", "margin_y_px", "max_zoom", "solo_zoom", "anchor_zoom",
  "punch", "punch_tilt_deg", "shake", "shake_max_px", "ult_on", "switch_on", "ko_on", "clash_on",
  "depth", "depth_base", "depth_gain", "depth_shot",
  "anchor_scale", "vscale_bottom", "vscale_top", "dscale_near", "dscale_far",
  "dscale_far_x_frac", "dscale_far_y_frac", "dscale_curve", "scale_min", "scale_max", "speed_min", "speed_max",
  "planet", "planet_reach_x_frac", "planet_reach_y_frac", "planet_horizon_deg", "planet_far", "planet_squash",
  "wire_grid", "wire_view",
  "roll.enabled", "roll.max_speed", "roll.zone_x_frac", "roll.zone_y_frac", "roll.vertical",
  "roll.spawn_ahead_px", "roll.margin_px",
  "pillars.enabled", "pillars.count", "pillars.respawn_s", "pillars.radius_x_px", "pillars.radius_y_px",
  "pillars.clear_x_px", "pillars.clear_y_px", "pillars.gap_x_px", "pillars.gap_y_px",
  "pillars.width", "pillars.height", "pillars.hp", "pillars.multi_chance"
];
// The Wireframe group's own rows: the two wireframe-only parts, then the Dust
// & Air settings it draws (also ticked beside them on the Dust & Air page).
var CAM_WIRE_EXTRA = [
  ["wire_grid", "Plain grid & border", "The plain scene grid and the screen border (cyan): the camera's zoom / tilt warp shows on it."],
  ["wire_view", "View box", "The green box of what the camera sees now, with its zoom."],
  ["roll.enabled", "Roll: off notice", "Rolling world (Dust & Air): the \"rolling world OFF\" status line."],
  ["roll.max_speed", "Roll: direction arrow", "Rolling world: the live roll direction / speed arrow and the max speed in the zone labels."],
  ["roll.zone_x_frac", "Roll: left / right zones", "Rolling world: the left and right roll bands (Roll zone X)."],
  ["roll.zone_y_frac", "Roll: top / bottom zones", "Rolling world: the top and bottom roll bands (Roll zone Y)."],
  ["roll.vertical", "Roll: up / down", "Rolling world: the top and bottom bands (shown only with Roll up / down too)."],
  ["roll.margin_px", "Roll: off-screen margin", "Rolling world: where pillars are dropped past the edge (seen when zoomed out)."],
  ["roll.spawn_ahead_px", "Roll: new pillar spread", "Rolling world: how far out new pillars rise (seen when zoomed out)."],
  ["pillars.enabled", "Pillars: off notice", "Rock pillars (Dust & Air): the \"pillars OFF\" status line."],
  ["pillars.count", "Pillars: count line", "Rock pillars: the pillars standing / wanted status line."],
  ["pillars.respawn_s", "Pillars: respawn timer", "Rock pillars: the next-pillar countdown in the status line."],
  ["pillars.radius_x_px", "Pillars: spawn X", "Rock pillars: the spawn ellipse and its X reach."],
  ["pillars.radius_y_px", "Pillars: spawn Y", "Rock pillars: the spawn ellipse and its Y reach."],
  ["pillars.clear_x_px", "Pillars: clear X", "Rock pillars: each fighter's clear ellipse and its X reach."],
  ["pillars.clear_y_px", "Pillars: clear Y", "Rock pillars: each fighter's clear ellipse and its Y reach."],
  ["pillars.gap_x_px", "Pillars: gap X", "Rock pillars: each pillar's gap ellipse (game only: live pillars)."],
  ["pillars.gap_y_px", "Pillars: gap Y", "Rock pillars: each pillar's gap ellipse (game only: live pillars)."],
  ["pillars.width", "Pillars: footprints", "Rock pillars: each pillar's ground footprint and body (game only: live pillars)."],
  ["pillars.height", "Pillars: bodies", "Rock pillars: each pillar's projectile / melee body (game only: live pillars)."],
  ["pillars.hp", "Pillars: HP", "Rock pillars: each pillar's HP label (game only: live pillars)."],
  ["pillars.multi_chance", "Pillars: multi-part", "Rock pillars: the multi-part block count label."]
];
var DEPTH_MAX = 0.6;
// Cinematic shot kinds: settings prefix and priority (higher wins).
var CAM_SHOTS = {"clash": ["clash", 1], "switch_in": ["switch", 2], "ultimate": ["ult", 3], "ko": ["ko", 4]};
// [group title, [[key, label, tip, step], ...]]
var CAM_GROUPS = [
  ["Follow-cam", [
    ["follow", "Follow-cam", "Frame the fighters and follow them. Off = the camera stays still at 1.0x (punch-in and shake still work)."],
    ["max_zoom", "Battle max zoom ×", "Battle: how far the camera zooms in when the fighters are close. It never zooms out below 1.0x, so nobody is pushed off the overlay.", 0.05],
    ["solo_zoom", "Solo zoom ×", "Solo: the light fixed zoom the camera follows the fighter at.", 0.05],
    ["follow_s", "Follow time (s)", "How long the camera takes to catch up with the fighters (about 95% of the way). Lower = snappier, higher = floatier.", 0.05],
    ["margin_x_px", "Margin X (px)", "Space kept left and right of the outermost fighters when framing them. Bigger = zooms in less.", 10],
    ["margin_y_px", "Margin Y (px)", "Space kept above and below the outermost fighters when framing them. Bigger = zooms in less.", 10]
  ]],
  ["Hit-stop punch-in", [
    ["punch", "Punch-in", "On every hit-stop (finishers, ultimates, strikes with Hit-stop) the camera snaps in toward the impact, holds through the freeze, then eases back."],
    ["punch_zoom", "Extra zoom ×", "Zoom added on top of the follow zoom at the peak of the punch.", 0.05],
    ["punch_tilt_deg", "Tilt (°)", "Roll along the knockback's left/right direction at the peak. 0 = level.", 0.5],
    ["punch_pull", "Pull to impact", "0..1: how far the view centre moves onto the impact point.", 0.05],
    ["punch_in_ticks", "Snap-in (ticks)", "How fast the punch reaches full zoom (1 tick = 16 ms).", 1],
    ["punch_out_s", "Ease-back (s)", "How long the camera takes to settle back after the freeze ends.", 0.05]
  ]],
  ["Screen shake", [
    ["shake", "Shake", "Strike shakes (Hit weight: shake / shake_px / shake_ticks) add trauma; overlapping hits build up and fade together. Off = no screen shake at all."],
    ["shake_max_px", "Max shake (px)", "Amplitude at full trauma. A single shake from rest still shakes its own px (up to this).", 1],
    ["shake_hz", "Shake speed (Hz)", "How fast the smooth shake moves. Higher = buzzier, lower = rolling.", 1]
  ]],
  ["Cinematic: Ultimate", [
    ["ult_on", "Ultimate push-in", "When any fighter starts its ultimate, the camera pushes in on it and holds while the ultimate plays."],
    ["ult_zoom", "Zoom ×", "How close the push-in gets.", 0.05],
    ["ult_in_s", "Push-in time (s)", "A slow push-in reads as a wind-up.", 0.05],
    ["ult_max_s", "Max hold (s)", "Holds while the ultimate plays, but never longer than this.", 0.1],
    ["ult_out_s", "Ease-back (s)", "How long it takes to return to the follow-cam.", 0.05]
  ]],
  ["Cinematic: Tag switch-in", [
    ["switch_on", "Switch-in shot", "When a tag partner switches in, the camera moves onto it."],
    ["switch_zoom", "Zoom ×", "", 0.05],
    ["switch_in_s", "Move-in time (s)", "", 0.05],
    ["switch_hold_s", "Hold (s)", "", 0.05],
    ["switch_out_s", "Ease-back (s)", "", 0.05]
  ]],
  ["Cinematic: KO", [
    ["ko_on", "KO shot", "On a KO the camera holds on the fallen fighter, then re-frames whoever is left. In Solo the final KO holds the frame, then the run ends."],
    ["ko_zoom", "Zoom ×", "", 0.05],
    ["ko_in_s", "Move-in time (s)", "", 0.05],
    ["ko_hold_s", "Hold (s)", "", 0.05],
    ["ko_out_s", "Ease-back (s)", "", 0.05],
    ["ko_slow", "Slow-mo speed", "Game speed during the KO slow-mo (both sides at once). 1 = no slow-mo, 0.25 = quarter speed.", 0.05],
    ["ko_slow_s", "Slow-mo time (s)", "How long the slow-mo lasts (real seconds). 0 = none.", 0.05]
  ]],
  ["Cinematic: Clash", [
    ["clash_on", "Clash shot", "When two opposing FX clash, the camera snaps onto the clash point."],
    ["clash_zoom", "Zoom ×", "", 0.05],
    ["clash_in_s", "Snap-in time (s)", "", 0.02],
    ["clash_hold_s", "Hold (s)", "", 0.05],
    ["clash_out_s", "Ease-back (s)", "", 0.05]
  ]],
  ["Wireframe overlay", [
    ["wireframe", "Wireframe overlay", "Draws a wireframe over the scene showing how the environment acts on the fighters: size contours and per-spot size / pace (Scaling grid, cyan), the anchor, planet horizon and squash rings and the depth tilt's near / far lines (magenta), the roll zones and roll direction (orange), the camera framing and view (green), the pillar spawn radius, clear zones, footprints and respawn timer (yellow). Shown on the preview here AND over the game screen (Solo and Battle); it follows every edit live. While it is on, every setting it draws gets a tick box in front of its name (here and on the Dust & Air page): untick one to hide its part of the wireframe (preview and game). A part drawn for several settings hides when any of them is unticked."]
  ]],
  ["Depth tilt", [
    ["depth", "Depth tilt", "A real perspective along the arena's depth (bottom-left near, top-right far): far things shrink and draw in toward the nearest fighter, so the slope reads deeper. Drawing only — sizes, hits and walls in the game are unchanged."],
    ["depth_base", "Base strength", "Perspective always applied (0 = none).", 0.01],
    ["depth_gain", "Near-side extra", "Added when the action is at the near (bottom-left) side: a lower, more dramatic camera.", 0.01],
    ["depth_shot", "Cinematic extra", "Added at the peak of a cinematic shot (ultimate, switch-in, KO, clash).", 0.01],
    ["depth_budget_ms", "Paint budget (ms)", "Perspective painting costs more. If drawing a frame takes longer than this for about 2 s, the game turns the depth tilt off for the session (save camera.json or press F5 to retry).", 1]
  ]],
  ["World anchor scaling", [
    ["anchor_scale", "Anchor scaling", "An invisible anchor sits at the centre of all fighters; the camera pans onto it. Every fighter, FX and its pace scale by height on screen x distance from the anchor. While on, closeness is shown by the scaling (the camera keeps a fixed pan zoom, only reduced to fit everyone) and the depth tilt runs bottom-near / top-far. Off = the old corner grid and follow zoom."],
    ["anchor_s", "Anchor follow (s)", "How long the anchor takes to catch up with the centre of the fighters (about 95%).", 0.05],
    ["anchor_fixed", "Fix anchor position", "On = the anchor is pinned to the screen spot YOU set with Anchor on view X / Y below (0..1 across, 0..1 down; any spot you like) and moves with the camera, so it never slides on screen; fighters grow and shrink around it as they move. The camera follows the fighters (at the pan zoom). Off = the anchor follows the fighters' centre."],
    ["anchor_zoom", "Pan zoom ×", "Fixed follow zoom while anchor scaling is on (1.0 = no room to pan). Only ever reduced to keep everyone in view.", 0.05],
    ["anchor_view_x_frac", "Anchor on view X (× width)", "Where the anchor sits left / right on the screen: 0 = left edge, 0.5 = centre, 1 = right edge. With Fix anchor position on, this is the spot it is pinned to. Needs a pan zoom above 1.0 to have room to move; the view still never leaves the screen.", 0.01],
    ["anchor_view_y_frac", "Anchor on view Y (× height)", "Where the anchor sits up / down on the screen: 0 = top edge, 0.5 = centre, 1 = bottom edge. With Fix anchor position on, this is the spot it is pinned to. Needs a pan zoom above 1.0 to have room to move; the view still never leaves the screen.", 0.01],
    ["vscale_bottom", "Bottom size ×", "Size at the very bottom of the screen (left or right does not matter).", 0.1],
    ["vscale_top", "Top size ×", "Size at the very top of the screen.", 0.1],
    ["dscale_near", "On-anchor ×", "Distance factor right on the anchor (fighters face to face).", 0.05],
    ["dscale_far", "Far ×", "Distance factor at the far distance below.", 0.01],
    ["dscale_far_x_frac", "Far distance X (× width)", "Left / right reach of the ellipse round the anchor that gets the Far factor, as a share of the screen width. 0.5 = two fighters on opposite edges.", 0.05],
    ["dscale_far_y_frac", "Far distance Y (× width)", "Up / down reach of the far ellipse, as a share of the screen width (same unit as X, so equal values = a circle).", 0.05],
    ["dscale_curve", "Falloff curve", "1 = linear. Above 1 = stays big at close range, drops when far. Below 1 = drops quickly.", 0.05],
    ["scale_min", "Min size ×", "Final size is clamped between Min and Max (final = vertical × distance).", 0.01],
    ["scale_max", "Max size ×", "", 0.1],
    ["speed_min", "Pace at min size", "Movement pace at the smallest size (pace rises linearly with size).", 0.05],
    ["speed_max", "Pace at max size", "Movement pace at the largest size.", 0.05]
  ]],
  ["Tiny planet", [
    ["planet", "Tiny planet", "The anchor becomes the top of a small planet: everything shrinks along a sphere curve as it moves away from the anchor (big near the top, dropping fast toward the horizon), and the terrain, rubble, debris, dust & air are squashed along the line to the anchor near the rim (foreshortening). Nothing is moved, so pillars and dust still line up with the fighters. Needs Anchor scaling; replaces the distance factors above and the depth tilt while on."],
    ["planet_reach_x_frac", "Horizon distance X (× width)", "How far left / right of the anchor the horizon is, as a share of the screen width. Smaller = a tinier planet.", 0.05],
    ["planet_reach_y_frac", "Horizon distance Y (× width)", "How far above / below the anchor the horizon is, as a share of the screen width (same unit as X, so equal values = a round horizon).", 0.05],
    ["planet_horizon_deg", "Horizon angle (°)", "How far round the sphere the horizon sits. 90 = a full quarter turn (strongest falloff and squash at the rim).", 1],
    ["planet_far", "Size at horizon ×", "Distance factor at the horizon (1 on the anchor).", 0.01],
    ["planet_squash", "Rim squash", "How much the world layers are flattened along the line to the anchor at the horizon. 0 = none.", 0.01],
    ["planet_ball", "Big ball", "The fight happens on top of a big ball (shown in the preview above too): the whole scene - fighters, FX, bullets, terrain, dust - is bent onto the ball. One curved horizon arc above the fight, nothing drawn past it, and things off to the side drop down the curve and lean outward. Drawing only: hits and walls are unchanged; the HUD stays flat."],
    ["planet_ball_radius_frac", "Ball radius (× width)", "Radius of the horizon arc, as a share of the screen width. Smaller = a rounder, tighter ball.", 0.05],
    ["planet_ball_top_frac", "Horizon height (× height)", "Where the top of the ball's horizon sits on screen, as a share of the screen height (0 = the very top).", 0.01],
    ["planet_ball_cols", "Curve cells across", "How many slices the bend is made of across the screen. More = smoother curve, slower.", 1],
    ["planet_ball_bands", "Curve cells down", "How many slices down the screen. More = more even spacing, slower.", 1]
  ]]
];
// Settings that do nothing under the current settings (Studio greys them out
// and locks them).  Each rule mirrors the game code that skips them; the first
// matching rule names the reason.  [controller test, reason, keys]
var CAM_DEPTH_KEYS = ["depth", "depth_base", "depth_gain", "depth_shot", "depth_budget_ms"];
var CAM_DSCALE_KEYS = ["dscale_near", "dscale_far", "dscale_far_x_frac", "dscale_far_y_frac", "dscale_curve"];
var CAM_BALL_KEYS = ["planet_ball_radius_frac", "planet_ball_top_frac", "planet_ball_cols", "planet_ball_bands"];
var CAM_PLANET_KEYS = ["planet_reach_x_frac", "planet_reach_y_frac", "planet_horizon_deg", "planet_far", "planet_squash", "planet_ball"].concat(CAM_BALL_KEYS);
var CAM_IDLE_RULES = [
  // camera.py _target: follow off = fixed 1.0x at the centre.
  [function (c) { return !c.follow; }, "Follow-cam is off",
   ["margin_x_px", "margin_y_px", "max_zoom", "solo_zoom", "anchor_zoom"]],
  // ... Anchor on view X / Y still place a fixed anchor on screen with the follow-cam off.
  [function (c) { return !c.follow && !c.anchor_fixed; }, "Follow-cam is off", ["anchor_view_x_frac", "anchor_view_y_frac"]],
  // worldscale.set_anchor / camera.py _target: anchor scaling off = corner grid + old follow zoom.
  [function (c) { return !c.anchor_scale; }, "Anchor scaling is off",
   ["anchor_s", "anchor_fixed", "anchor_zoom", "anchor_view_x_frac", "anchor_view_y_frac", "vscale_bottom", "vscale_top"]
     .concat(CAM_DSCALE_KEYS, ["scale_min", "scale_max", "speed_min", "speed_max", "planet"], CAM_PLANET_KEYS)],
  // camera.py _step_anchor / _target: a fixed anchor doesn't glide, and the cam frames the fighters.
  [function (c) { return c.anchor_fixed; }, "Fix anchor position is on", ["anchor_s"]],
  // camera.py _target: anchor scaling uses Pan zoom instead.
  [function (c) { return c.anchor_scale; }, "Anchor scaling is on (it uses Pan zoom instead)", ["max_zoom", "solo_zoom"]],
  // worldscale.size (planet curve replaces the distance term), Camera.depth_live (planet replaces the tilt).
  [function (c) { return c.anchor_scale && c.planet; }, "Tiny planet is on", CAM_DSCALE_KEYS.concat(CAM_DEPTH_KEYS)],
  [function (c) { return !c.planet; }, "Tiny planet is off", CAM_PLANET_KEYS],
  // camera.py / ballwarp.py: the big ball bend is off.
  [function (c) { return !c.planet_ball; }, "Big ball is off", CAM_BALL_KEYS],
  [function (c) { return !c.depth; }, "Depth tilt is off", CAM_DEPTH_KEYS.slice(1)],
  [function (c) { return !c.punch; }, "Punch-in is off", ["punch_zoom", "punch_tilt_deg", "punch_pull", "punch_in_ticks", "punch_out_s"]],
  [function (c) { return !c.shake; }, "Shake is off", ["shake_max_px", "shake_hz"]],
  [function (c) { return !c.ult_on; }, "Ultimate push-in is off", ["ult_zoom", "ult_in_s", "ult_max_s", "ult_out_s"]],
  [function (c) { return !c.switch_on; }, "Switch-in shot is off", ["switch_zoom", "switch_in_s", "switch_hold_s", "switch_out_s"]],
  // app.py _ko_cinematic: no KO shot = no KO slow-mo either.
  [function (c) { return !c.ko_on; }, "KO shot is off", ["ko_zoom", "ko_in_s", "ko_hold_s", "ko_out_s", "ko_slow", "ko_slow_s"]],
  [function (c) { return !c.clash_on; }, "Clash shot is off", ["clash_zoom", "clash_in_s", "clash_hold_s", "clash_out_s"]]
];
// Settings whose change can grey / un-grey others (the page rebuilds on them).
var CAM_IDLE_CONTROLLERS = ["follow", "anchor_scale", "anchor_fixed", "planet", "planet_ball", "depth", "punch", "shake", "ult_on", "switch_on", "ko_on", "clash_on"];
function camIdle(c, k) {
  for (var i = 0; i < CAM_IDLE_RULES.length; i++) {
    var r = CAM_IDLE_RULES[i];
    if (r[2].indexOf(k) >= 0 && r[0](c)) return r[1];
  }
  return "";
}

var TICK_MS = 16, DT = TICK_MS / 1000;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function normalize(o) {
  var s = {format: CAM_FORMAT};
  Object.keys(CAM_DEFAULTS).forEach(function (k) { s[k] = CAM_DEFAULTS[k]; });
  s.wire_off = [];
  if (!o || typeof o !== "object") return s;
  o = Object.assign({}, o);
  Object.keys(CAM_LEGACY_XY).forEach(function (old) {
    if (old in o) CAM_LEGACY_XY[old].forEach(function (k) { if (!(k in o)) o[k] = o[old]; });
  });
  if (Array.isArray(o.wire_off)) s.wire_off = CAM_WIRE_KEYS.filter(function (k) { return o.wire_off.indexOf(k) >= 0; });
  Object.keys(CAM_DEFAULTS).forEach(function (k) { if (typeof CAM_DEFAULTS[k] === "boolean" && k in o) s[k] = !!o[k]; });
  Object.keys(CAM_RANGES).forEach(function (k) {
    if (!(k in o)) return;
    var v = parseFloat(o[k]);
    if (isFinite(v)) s[k] = clamp(v, CAM_RANGES[k][0], CAM_RANGES[k][1]);
  });
  s.punch_in_ticks = Math.round(s.punch_in_ticks);
  if (s.scale_min > s.scale_max) { var t = s.scale_min; s.scale_min = s.scale_max; s.scale_max = t; }
  return s;
}
function hash(i, seed) {
  var h = (Math.imul(i, 374761393) + Math.imul(seed, 668265263)) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  h = (h ^ (h >>> 16)) >>> 0;
  return (h & 0xFFFF) / 32767.5 - 1;
}
function noise(x, seed) {
  var i = Math.floor(x), f = x - i, a = hash(i, seed), b = hash(i + 1, seed), u = f * f * (3 - 2 * f);
  return a + (b - a) * u;
}
// laser/worldscale.py _ellipse_u: 0 at the centre, 1 on the (rx, ry) ellipse.
function ellU(dx, dy, rx, ry) { return rx > 1e-6 && ry > 1e-6 ? Math.hypot(dx / rx, dy / ry) : 0; }
function ease(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
function ticks(sec) { return Math.max(1, Math.round(sec / DT)); }

// One cinematic move (laser/camera.py _Shot): ramps in, holds, eases out;
// follows `fig` ({x, y}) when given; whileFn keeps the hold going.
function Shot(kind, x, y, fig, zoom, inT, holdT, outT, whileFn) {
  this.kind = kind; this.prio = CAM_SHOTS[kind][1]; this.x = x; this.y = y; this.fig = fig; this.zoom = zoom;
  this.inT = Math.max(1, inT); this.holdT = Math.max(0, holdT); this.outT = Math.max(1, outT); this.whileFn = whileFn || null;
  this.env = 0; this.age = 0; this.out = false;
}
Shot.prototype.step = function () {
  if (this.fig) { this.x = this.fig.x; this.y = this.fig.y; }
  this.age++;
  if (!this.out) {
    this.env = Math.min(1, this.env + 1 / this.inT);
    var held = this.age - this.inT;
    if (this.whileFn) { var going = false; try { going = !!this.whileFn(); } catch (e) {} if (held >= 0 && (!going || held >= this.holdT)) this.out = true; }
    else if (held >= this.holdT) this.out = true;
  } else this.env = Math.max(0, this.env - 1 / this.outT);
  return !(this.out && this.env <= 0);
};

// The camera.  figs = [{x, y}], battle = bool, hitstop = ticks left.
function Cam(sw, sh, cfg) {
  this.sw = sw; this.sh = sh; this.cfg = cfg || normalize({});
  this.reset();
}
Cam.prototype.reset = function () {
  this.cx = this.sw / 2; this.cy = this.sh / 2; this.zoom = 1;
  this.env = 0; this.inLeft = 0; this.px = this.cx; this.py = this.cy; this.roll = 0;
  this.req = null; this.prevHs = 0; this.trauma = 0; this.decay = 0; this.t = 0; this.shot = null;
  this.k = 0; this.ax = this.sw / 2; this.ay = this.sh / 2; this.anc = null;
};
Cam.prototype.depthT = function (x, y) {
  if (this.cfg.anchor_scale) return 1 - y / this.sh;
  return 0.5 * (x / this.sw) + 0.5 * (1 - y / this.sh);
};
// World anchor (laser/camera.py _step_anchor): eased centre of the fighters.
Cam.prototype.stepAnchor = function (figs) {
  var c = this.cfg;
  if (!c.anchor_scale) { this.anc = null; return; }
  if (c.anchor_fixed) { this.pinAnchor(); return; }   // fixed: on its screen spot
  if (!figs.length) return;
  var tx = 0, ty = 0;
  figs.forEach(function (f) { tx += f.x; ty += f.y; });
  tx /= figs.length; ty /= figs.length;
  if (!this.anc) { this.anc = [tx, ty]; return; }
  var a = 1 - Math.exp(-DT * 3 / c.anchor_s);
  this.anc = [this.anc[0] + (tx - this.anc[0]) * a, this.anc[1] + (ty - this.anc[1]) * a];
};
// laser/camera.py _pin_anchor: the anchor under its screen spot of the follow view.
Cam.prototype.pinAnchor = function () {
  var c = this.cfg, z = Math.max(1e-6, this.zoom);
  this.anc = [this.cx + (c.anchor_view_x_frac - 0.5) * this.sw / z, this.cy + (c.anchor_view_y_frac - 0.5) * this.sh / z];
};
// laser/worldscale.py size(): vertical x distance-from-anchor (null = off).
Cam.prototype.planetOn = function () { return !!(this.cfg.planet && this.cfg.anchor_scale); };
// Tiny planet: [theta, dx, dy, dist] of a point (laser/worldscale.py _theta).
Cam.prototype.theta = function (x, y) {
  var c = this.cfg, hz = clamp(c.planet_horizon_deg, 1, 90) * Math.PI / 180;
  var dx = x - this.anc[0], dy = y - this.anc[1], d = Math.hypot(dx, dy);
  return [clamp(ellU(dx, dy, c.planet_reach_x_frac * this.sw, c.planet_reach_y_frac * this.sw), 0, 1) * hz, dx, dy, d];
};
// laser/worldscale.py squash(): [k, ux, uy] or null.
Cam.prototype.squashAt = function (x, y) {
  if (!this.planetOn() || !this.anc) return null;
  var t = this.theta(x, y);
  if (t[3] < 1e-3) return null;
  var k = clamp(1 - this.cfg.planet_squash * (1 - Math.cos(t[0])), 0.05, 1);
  return k > 0.999 ? null : [k, t[1] / t[3], t[2] / t[3]];
};
Cam.prototype.sizeAt = function (x, y) {
  var c = this.cfg;
  if (!c.anchor_scale || !this.anc) return null;
  var v = c.vscale_top + (c.vscale_bottom - c.vscale_top) * clamp(y / this.sh, 0, 1);
  if (this.planetOn()) {
    var ch = Math.cos(clamp(c.planet_horizon_deg, 1, 90) * Math.PI / 180);
    var cc = ch < 1 - 1e-6 ? (Math.cos(this.theta(x, y)[0]) - ch) / (1 - ch) : 1;
    return clamp(v * (c.planet_far + (1 - c.planet_far) * clamp(cc, 0, 1)), c.scale_min, c.scale_max);
  }
  var u = clamp(ellU(x - this.anc[0], y - this.anc[1], c.dscale_far_x_frac * this.sw, c.dscale_far_y_frac * this.sw), 0, 1);
  var d = c.dscale_near + (c.dscale_far - c.dscale_near) * (u > 0 ? Math.pow(u, c.dscale_curve) : 0);
  return clamp(v * d, c.scale_min, c.scale_max);
};
// The size / pace rule a fighter gets at (x, y): anchor scaling (sizeAt), else
// the old corner grid (laser/combat.py position_scale, laser/config.py).
var GRID_SIZE = [2.3333, 1.0, 5.0, 2.3333], GRID_PACE = [0.6, 0.4, 1.0, 0.6];   // TL, TR, BL, BR
function bilerp(c, x, y) { return (c[0] * (1 - x) + c[1] * x) * (1 - y) + (c[2] * (1 - x) + c[3] * x) * y; }
Cam.prototype.sizeAny = function (x, y) {
  var s = this.sizeAt(x, y);
  return s != null ? s : bilerp(GRID_SIZE, clamp(x / this.sw, 0, 1), clamp(y / this.sh, 0, 1));
};
Cam.prototype.paceAny = function (x, y) {
  var c = this.cfg, s = this.sizeAt(x, y);
  if (s == null) return bilerp(GRID_PACE, clamp(x / this.sw, 0, 1), clamp(y / this.sh, 0, 1));
  if (c.scale_max - c.scale_min < 1e-6) return c.speed_max;
  return c.speed_min + (c.speed_max - c.speed_min) * (s - c.scale_min) / (c.scale_max - c.scale_min);
};
Cam.prototype.depthTarget = function (figs) {
  var c = this.cfg, best = null, self = this;
  if (!c.depth || this.planetOn() || !figs.length) return [0, this.ax, this.ay];
  figs.forEach(function (f) { var t = self.depthT(f.x, f.y); if (!best || t < best[0]) best = [t, f.x, f.y]; });
  var t = clamp(best[0], 0, 1);
  return [Math.min(DEPTH_MAX, c.depth_base + c.depth_gain * (1 - t)), best[1], best[2]];
};
// Depth tilt of a scene point under view v: [x', y', w] (draw sizes at 1/w).
Cam.prototype.depth = function (v, x, y) {
  var k = v[6], w = 1 + k * (this.depthT(x, y) - this.depthT(v[7], v[8]));
  return [v[7] + (x - v[7]) / w, v[8] + (y - v[8]) / w, w];
};
Cam.prototype.shotOn = function (kind) { var s = CAM_SHOTS[kind]; return !!s && !!this.cfg[s[0] + "_on"]; };
Cam.prototype.koHoldTicks = function () { return ticks(this.cfg.ko_in_s) + ticks(this.cfg.ko_hold_s); };
// kind: "ultimate" / "switch_in" / "ko" / "clash"; on (x, y) or on fig.
Cam.prototype.startShot = function (kind, x, y, fig, whileFn) {
  if (!CAM_SHOTS[kind] || !this.shotOn(kind)) return false;
  var cur = this.shot;
  if (cur && !cur.out && cur.prio > CAM_SHOTS[kind][1]) return false;
  if (fig) { x = fig.x; y = fig.y; }
  var pre = CAM_SHOTS[kind][0], c = this.cfg, hold = kind === "ultimate" ? c.ult_max_s : c[pre + "_hold_s"];
  var s = new Shot(kind, x, y, fig, c[pre + "_zoom"], ticks(c[pre + "_in_s"]), Math.round(hold / DT), ticks(c[pre + "_out_s"]), whileFn);
  if (cur) s.env = cur.env;
  this.shot = s;
  return true;
};
Cam.prototype.addShake = function (px, ticks) {
  var mx = this.cfg.shake_max_px;
  if (px <= 0 || mx <= 0) return;
  var add = Math.sqrt(Math.min(1, px / mx)), rate = add / Math.max(1, Math.round(ticks)), b = this.trauma;
  this.decay = b <= 1e-4 ? rate : (b * this.decay + add * rate) / (b + add);
  this.trauma = Math.min(1, b + add);
};
Cam.prototype.punch = function (x, y, dx, dy) { this.req = [x, y, dx || 0, dy || 0]; };
Cam.prototype.clampC = function (cx, cy, z) {
  var hw = this.sw / (2 * z), hh = this.sh / (2 * z);
  return [Math.min(Math.max(cx, hw), this.sw - hw), Math.min(Math.max(cy, hh), this.sh - hh)];
};
Cam.prototype.target = function (figs, battle) {
  var c = this.cfg;
  if (!c.follow || !figs.length) return [this.sw / 2, this.sh / 2, 1];
  var xs = figs.map(function (f) { return f.x; }), ys = figs.map(function (f) { return f.y; });
  var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
  var fit = Math.min(this.sw / Math.max(1, x1 - x0 + 2 * c.margin_x_px), this.sh / Math.max(1, y1 - y0 + 2 * c.margin_y_px));
  var z, cc;
  if (c.anchor_scale && c.anchor_fixed) {
    z = Math.max(1, Math.min(c.anchor_zoom, fit));   // fixed anchor: follow the fighters instead
    cc = this.clampC((x0 + x1) / 2, (y0 + y1) / 2, z);
  } else if (c.anchor_scale && this.anc) {
    z = Math.max(1, Math.min(c.anchor_zoom, fit));
    cc = this.clampC(this.anc[0] - (c.anchor_view_x_frac - 0.5) * this.sw / z,
                     this.anc[1] - (c.anchor_view_y_frac - 0.5) * this.sh / z, z);
  } else {
    z = battle ? clamp(fit, 1, c.max_zoom) : clamp(Math.min(c.solo_zoom, fit), 1, c.solo_zoom);
    cc = this.clampC((x0 + x1) / 2, (y0 + y1) / 2, z);
  }
  return [cc[0], cc[1], z];
};
Cam.prototype.step = function (figs, battle, hs) {
  var c = this.cfg; this.t++;
  this.stepAnchor(figs);
  var tg = this.target(figs, battle), a = 1 - Math.exp(-DT * 3 / c.follow_s);
  this.cx += (tg[0] - this.cx) * a; this.cy += (tg[1] - this.cy) * a; this.zoom += (tg[2] - this.zoom) * a;
  if (c.anchor_scale && c.anchor_fixed) this.pinAnchor();   // this tick's view: no lag
  var dt = this.depthTarget(figs);
  this.k += (dt[0] - this.k) * a; this.ax += (dt[1] - this.ax) * a; this.ay += (dt[2] - this.ay) * a;
  if (this.shot && (!this.shotOn(this.shot.kind) || !this.shot.step())) this.shot = null;
  var req = this.req; this.req = null;
  if (c.punch) {
    if (!req && hs > 0 && this.prevHs <= 0) req = [this.cx, this.cy, 0, 0];
    if (req) {
      this.px = req[0]; this.py = req[1];
      var d = Math.hypot(req[2], req[3]);
      this.roll = d > 1e-6 ? c.punch_tilt_deg * req[2] / d : 0;
      this.inLeft = c.punch_in_ticks;
    }
    if (this.inLeft > 0 || hs > 0) { this.env = Math.min(1, this.env + 1 / c.punch_in_ticks); this.inLeft = Math.max(0, this.inLeft - 1); }
    else this.env = Math.max(0, this.env - DT / c.punch_out_s);
  } else { this.env = 0; this.inLeft = 0; }
  this.prevHs = hs;
  if (this.trauma > 0) this.trauma = Math.max(0, this.trauma - this.decay);
};
// [cx, cy, zoom, roll_deg, shake_dx, shake_dy]
Cam.prototype.view = function () {
  var c = this.cfg, cx = this.cx, cy = this.cy, z = this.zoom, s = this.shot;
  var dep = c.depth && !this.planetOn(), dk = dep ? this.k : 0;
  if (s && s.env > 0) { var k = ease(s.env); cx += (s.x - cx) * k; cy += (s.y - cy) * k; z += (Math.max(z, s.zoom) - z) * k; if (dep) dk += c.depth_shot * k; }
  dk = clamp(dk, 0, DEPTH_MAX);
  var e = c.punch ? ease(this.env) : 0, pull = c.punch_pull * e;
  z += c.punch_zoom * e;
  var cc = this.clampC(cx + (this.px - cx) * pull, cy + (this.py - cy) * pull, z);
  var sx = 0, sy = 0;
  if (c.shake && this.trauma > 0) {
    var amp = c.shake_max_px * this.trauma * this.trauma, ph = this.t * DT * c.shake_hz;
    sx = amp * noise(ph, 1); sy = amp * noise(ph, 2);
  }
  return [cc[0], cc[1], z, this.roll * e, sx, sy, dk, this.ax, this.ay];
};
// Push the view onto a 2D canvas context (the caller saves / restores).
Cam.prototype.apply = function (g, v) {
  g.translate(this.sw / 2 + v[4], this.sh / 2 + v[5]);
  if (v[3]) g.rotate(v[3] * Math.PI / 180);
  g.scale(v[2], v[2]);
  g.translate(-v[0], -v[1]);
};

// Big ball (laser/ballwarp.py BallWarp.setup / _map): this frame's ball in
// screen px, or null when off.  [px, py, R, top, rref, cy, yBot, sw, sh]
Cam.prototype.ballGeo = function (v) {
  var c = this.cfg;
  if (!(c.planet_ball && this.planetOn())) return null;
  var sw = this.sw, sh = this.sh, R = Math.max(16, c.planet_ball_radius_frac * sw), top = c.planet_ball_top_frac * sh;
  var px = sw * 0.5, py = sh * 0.6;
  if (this.anc) {
    // Camera.world_to_screen (no depth: the planet replaces it).
    var r = (v[3] || 0) * Math.PI / 180, cs = Math.cos(r), sn = Math.sin(r);
    var dx = (this.anc[0] - v[0]) * v[2], dy = (this.anc[1] - v[1]) * v[2];
    px = sw / 2 + v[4] + dx * cs - dy * sn; py = sh / 2 + v[5] + dx * sn + dy * cs;
  }
  py = Math.max(top + 1, Math.min(sh, py));
  var rref = Math.max(0.3 * R, R - (py - top));
  return [px, py, R, top, rref, top + R, Math.min(sh, top + 0.97 * R), sw, sh];
};
// A screen point -> where the ball draws it.
function ballMap(geo, x, y) {
  var r = geo[2] - (y - geo[3]), phi = (x - geo[0]) / geo[4];
  return [geo[0] + r * Math.sin(phi), geo[5] - r * Math.cos(phi)];
}

window.CAMERA = {
  FORMAT: CAM_FORMAT, DEFAULTS: CAM_DEFAULTS, RANGES: CAM_RANGES, GROUPS: CAM_GROUPS, SHOTS: CAM_SHOTS,
  WIRE_KEYS: CAM_WIRE_KEYS, WIRE_EXTRA: CAM_WIRE_EXTRA, ellU: ellU,
  idle: camIdle, IDLE_CONTROLLERS: CAM_IDLE_CONTROLLERS,
  TICK_MS: TICK_MS, normalize: normalize, Cam: Cam, ballMap: ballMap
};
})();
