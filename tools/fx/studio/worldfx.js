// World physics: Dust & Air — FX Studio's port of laser/worldfx.py.
//
// The dust, debris and displaced air the ARENA kicks up when fighters move,
// jump, get slammed, clash and blast.  Shared by every character (saved as
// world_physics.json, format pb_world_physics, read by the game from
// characters/world_physics.json); a character's FX pack may carry
// "world_physics" with any of these sections, which then replace the world's
// for the events that fighter causes.
//
// Ground model: the screen is a slope seen from its foot.  The position-scale
// grid says how big things are where (bottom-left near 5x, top-right far 1x).
// A particle has a ground point (x, y) and a height z, drawn at (x, y - z).
// Ground spreads are ellipses whose height / width ratio runs from
// ground.flat_near (nearest) to ground.flat_far (farthest): rounder the
// farther away.  Screen edges are the walls.
//
// Engine (hybrid): rocks / pebbles / sparks are closed-form (whole flight
// fixed at spawn); fine dust is simulated and relaxes toward the local air
// velocity, v = u + (v - u) e^(-dt/tau); the air is a short list of analytic
// sources (blast, wake, curl, column, jet).  tools/fx/check_parity.py checks
// WP_DEFAULTS / WP_RANGES / WP_FORMAT / WP_SECTIONS against the game.
(function () {
"use strict";
var WP_FORMAT = "pb_world_physics";
var WP_SMOKE_STYLES = ["cel", "billow", "ink", "swirl", "flat", "ring", "stepped"];
var WP_SECTIONS = ["ground", "dash", "jump", "slam", "clash", "blast", "sonic", "spiral", "pillars", "rubble", "ground_fx", "roll", "boulder_impact", "director", "team", "smoke_cel", "smoke_billow", "smoke_ink", "smoke_swirl", "smoke_flat", "smoke_ring", "smoke_stepped"];
var SPIRAL_MODES = ["whole", "parts_together", "parts_in_turn"];
var SPIRAL_DIRS = ["left_to_right", "right_to_left", "creation", "reverse_creation"];
var WP_DEFAULTS = {
  "ground": {"enabled": true, "flat_near": 0.25, "flat_far": 0.55, "max_dust": 420, "tau_ms": 140, "ink":
            "#1b1712", "style": "cel"},
  "dash": {"enabled": true, "speed": 380, "rate": 40, "inherit": 40, "size": 100, "life_ms": 700,
          "start_burst": true, "wake": true, "wake_pct": 100, "curls": true, "grit": 6, "color": "#d9c4a3",
          "style": "default"},
  "jump": {"enabled": true, "dust": 14, "pebbles": 8, "ring": true, "column": true, "land": true, "hops":
          true, "size": 100, "color": "#d9c4a3", "style": "default", "split": 0, "twist": -1},
  "slam": {"enabled": true, "min_speed": 7, "launch": true, "skid": true, "crater": true, "wall": true,
          "dust": 22, "rocks": 10, "size": 100, "color": "#cdb391", "rock_color": "#7a6e62", "style":
          "default", "split": 0, "twist": -1},
  "clash": {"enabled": true, "sheet": true, "dust": 14, "sparks": 16, "ground_jet": true, "size": 100,
           "color": "#e6dccb", "spark_color": "#ffb347", "style": "default", "split": 0, "twist": -1},
  "blast": {"enabled": true, "min_damage": 4, "strength": 100, "suck_back": true, "reach": 80, "dust": 18,
           "ring": true, "size": 100, "color": "#d9c4a3", "style": "default", "split": 0, "twist": -1},
  "sonic": {"enabled": true, "mach": 1100, "knockback": false, "cone": true, "vapor": true, "boom": true,
           "boom_hz": 0, "sweep": true, "color": "#e8f2ff", "style": "default", "split": 0, "twist": -1},
  "spiral": {"enabled": true, "parts": 1, "gap": 14, "rotation": 0, "life_pct": 100, "spiral": 0, "spin_hz":
            6.0, "min_speed": 200, "max_speed": 1500, "length_pct": 100, "radius_pct": 100, "body_scale":
            true, "body_pct": 100, "taper": 0, "trail": true, "radius_speed_pct": 100, "thread_px": 5, "segments": 24, "tail_pct": 15, "expand_pct": 600, "thin_pct": 30, "streak_pct": 90, "drift_pct": 100, "hand": "right", "reach": "behind", "speed_len": 50, "in_ms": 0, "in_mode": "whole", "in_dir": "left_to_right", "out_ms":
            0, "out_mode": "whole", "out_dir": "left_to_right"},
  "pillars": {"enabled": true, "count": 3, "radius_x_px": 420, "radius_y_px": 420, "clear_x_px": 110,
              "clear_y_px": 110, "gap_x_px": 140, "gap_y_px": 140, "respawn_s": 6.0,
              "width": 22, "height": 70, "rise_ms": 450, "hp": 60, "break_damage": 30, "break_knockback": 200,
              "break_speed": 24, "chip_pct": 100, "body_chip": 2, "melee_damage": 10, "blast_reach": 60,
              "repel": 0.25, "repel_px": 10, "block_projectiles": true, "rubble": 9, "boulders": 4,
              "color": "#8a7c6c", "facets": 7, "view_yaw": 55, "view_reach_frac": 0.5,
              "pitch_bottom": 65, "pitch_top": 15, "multi_chance": 30, "multi_size_pct": 250,
              "multi_min": 3, "multi_max": 6},
  "rubble": {"enabled": true, "rest": true, "rest_s": 6.0, "fade_s": 1.5, "max_rubble": 160, "boulders": true,
             "boulder_min": 5, "boulder_max": 11, "boulder_count": 3, "hit_knockback": 14, "hit_damage": 20,
             "speed": 20, "cooldown_ms": 700, "crater": true, "color": "#7a6e62"},
  "ground_fx": {"enabled": true, "beam_min_damage": 30, "beam_trench": true, "beam_debris": true,
                "beam_spiral": true, "trench_width": 100, "orb_min_damage": 40, "orb_crater": 100,
                "crescent_min_damage": 40, "streak_width": 100, "mark_s": 6.0, "fade_s": 1.5,
                "color": "#3b3129", "tilt_top": 6, "tilt_bottom": 90, "merge": true},
  "roll": {"enabled": true, "max_speed": 600, "zone_x_frac": 0.333, "zone_y_frac": 0.333, "vertical": true, "ease_ms": 400,
           "spawn_ahead_px": 320, "margin_px": 60},
  "boulder_impact": {"enabled": true, "speed_keep_pct": 50, "damage_keep_pct": 50, "chip_ms": 250,
                     "fighters": true},
  // Fight director (Daniel 2026-11-13, laser/tempo.py, world only): the
  // world's intensity 0..1 (calm / build / burst) that every Fight rhythm
  // fighter reads.  Pushed up by closing distance, hits, counters, HP
  // swings, low HP, KOs and quiet spells; decays back to calm by itself.
  "director": {"enabled": true, "decay_pct_s": 12, "close_px": 260, "close_pct_s": 10, "hit_pct": 3,
               "damage_pct": 60, "counter_pct": 5, "hp_swing_pct": 50, "low_hp_at": 30, "low_hp_pct_s": 6,
               "ko_pct": 45, "idle_after_s": 2.5, "idle_pct_s": 5, "build_at": 35, "burst_at": 80,
               "burst_jitter_pct": 12, "burst_s_min": 2.5, "burst_s_max": 4.5, "after_burst_pct": 8},
  // Team play (laser/tempo.py squad board, world only): melee attack
  // tokens per team (0 = no limit) and the player's token reach.
  "team": {"enabled": true, "tokens_team1": 2, "tokens_team2": 2, "token_range_pct": 160},
  "smoke_cel": {"tones": 3, "shadow": 30, "light": 50, "light_dir": 225, "outline": 2.0, "ink": "#1b1712",
               "tint": "#ffffff", "tint_mix": 0, "opacity": 100, "grow": 2.0, "grow_at": 0.6, "shrink":
               "steps", "steps": 3, "hold": 1, "fade": 0, "life_pct": 100, "rise": 12, "tau_pct": 100,
               "ground_keep": 0.9, "wobble": 0, "wobble_hz": 1.5, "spread_pct": 100, "lift_pct": 100},
  "smoke_billow": {"tones": 3, "shadow": 38, "light": 50, "light_dir": 225, "outline": 2.5, "ink": "#1b1712",
                  "tint": "#ffffff", "tint_mix": 0, "opacity": 100, "grow": 2.4, "grow_at": 0.5, "shrink":
                  "steps", "steps": 3, "hold": 1, "fade": 0, "life_pct": 100, "rise": 18, "tau_pct": 100,
                  "ground_keep": 0.9, "wobble": 0, "wobble_hz": 1.5, "spread_pct": 100, "lift_pct": 100},
  "smoke_ink": {"tones": 2, "shadow": 45, "light": 50, "light_dir": 225, "outline": 0.0, "ink": "#1b1712",
               "tint": "#3a3640", "tint_mix": 35, "opacity": 85, "grow": 2.6, "grow_at": 0.6, "shrink":
               "smooth", "steps": 3, "hold": 1, "fade": 60, "life_pct": 100, "rise": 8, "tau_pct": 100,
               "ground_keep": 0.9, "wobble": 1.5, "wobble_hz": 1.5, "spread_pct": 100, "lift_pct": 100},
  "smoke_swirl": {"tones": 2, "shadow": 30, "light": 50, "light_dir": 225, "outline": 1.5, "ink": "#1b1712",
                 "tint": "#ffffff", "tint_mix": 0, "opacity": 100, "grow": 1.8, "grow_at": 0.6, "shrink":
                 "smooth", "steps": 3, "hold": 1, "fade": 40, "life_pct": 100, "rise": 20, "tau_pct": 100,
                 "ground_keep": 0.9, "wobble": 2, "wobble_hz": 1.0, "spread_pct": 100, "lift_pct": 100},
  "smoke_flat": {"tones": 1, "shadow": 30, "light": 50, "light_dir": 225, "outline": 3.0, "ink": "#1b1712",
                "tint": "#ffffff", "tint_mix": 0, "opacity": 100, "grow": 2.0, "grow_at": 0.6, "shrink":
                "steps", "steps": 2, "hold": 1, "fade": 0, "life_pct": 100, "rise": 12, "tau_pct": 100,
                "ground_keep": 0.9, "wobble": 0, "wobble_hz": 1.5, "spread_pct": 100, "lift_pct": 100},
  "smoke_ring": {"tones": 1, "shadow": 30, "light": 50, "light_dir": 225, "outline": 1.5, "ink": "#1b1712",
                "tint": "#ffffff", "tint_mix": 0, "opacity": 100, "grow": 3.0, "grow_at": 0.9, "shrink":
                "smooth", "steps": 3, "hold": 1, "fade": 50, "life_pct": 100, "rise": 10, "tau_pct": 100,
                "ground_keep": 0.9, "wobble": 0, "wobble_hz": 1.5, "spread_pct": 100, "lift_pct": 100},
  "smoke_stepped": {"tones": 2, "shadow": 30, "light": 50, "light_dir": 225, "outline": 2.0, "ink": "#1b1712",
                   "tint": "#ffffff", "tint_mix": 0, "opacity": 100, "grow": 2.0, "grow_at": 0.6, "shrink":
                   "erode", "steps": 4, "hold": 2, "fade": 0, "life_pct": 100, "rise": 12, "tau_pct": 100,
                   "ground_keep": 0.9, "wobble": 0, "wobble_hz": 1.5, "spread_pct": 100, "lift_pct": 100}
};
var WP_RANGES = {
  "ground": {"flat_near": [0.05, 1.0], "flat_far": [0.05, 1.0], "max_dust": [0, 1500], "tau_ms": [20, 600]},
  "dash": {"speed": [50, 3000], "rate": [0, 200], "inherit": [0, 100], "size": [10, 400], "life_ms": [100,
          3000], "wake_pct": [0, 300], "grit": [0, 60]},
  "jump": {"dust": [0, 80], "pebbles": [0, 40], "size": [10, 400], "split": [0, 6], "twist": [-1, 100]},
  "slam": {"min_speed": [0, 60], "dust": [0, 120], "rocks": [0, 40], "size": [10, 400], "split": [0, 6], "twist": [-1, 100]},
  "clash": {"dust": [0, 80], "sparks": [0, 80], "size": [10, 400], "split": [0, 6], "twist": [-1, 100]},
  "blast": {"min_damage": [0, 500], "strength": [0, 300], "reach": [20, 1200], "dust": [0, 120], "size": [10,
           400], "split": [0, 6], "twist": [-1, 100]},
  "sonic": {"mach": [100, 6000], "boom_hz": [0, 10], "split": [0, 6], "twist": [-1, 100]},
  "spiral": {"parts": [1, 6], "gap": [0, 60], "rotation": [0, 360], "life_pct": [20, 500], "spiral": [0, 100],
            "spin_hz": [0.1, 30], "min_speed": [10, 3000], "max_speed": [10, 6000], "length_pct": [10, 500],
            "radius_pct": [10, 300], "body_pct": [10, 300], "taper": [-100, 100], "radius_speed_pct": [0, 500], "thread_px": [1, 40], "segments": [6, 120], "tail_pct": [5, 100], "expand_pct": [0, 1000], "thin_pct": [5, 100], "streak_pct": [0, 100], "drift_pct": [0, 300], "speed_len": [0, 200], "in_ms": [0, 2000], "out_ms": [0, 2000]},
  "pillars": {"count": [0, 12], "radius_x_px": [50, 2000], "radius_y_px": [50, 2000], "clear_x_px": [0, 600],
              "clear_y_px": [0, 600], "gap_x_px": [0, 800], "gap_y_px": [0, 800],
              "respawn_s": [0, 120], "width": [4, 2000], "height": [8, 600], "rise_ms": [16, 5000], "hp": [1, 2000],
              "break_damage": [0, 10000], "break_knockback": [0, 10000], "break_speed": [0, 200],
              "chip_pct": [0, 500], "body_chip": [0, 100], "melee_damage": [0, 500], "blast_reach": [0, 600],
              "repel": [0, 5], "repel_px": [0, 100], "rubble": [0, 60], "boulders": [0, 30],
              "facets": [5, 12], "view_yaw": [0, 85], "view_reach_frac": [0.05, 2],
              "pitch_bottom": [5, 85], "pitch_top": [5, 85], "multi_chance": [0, 100],
              "multi_size_pct": [100, 1000], "multi_min": [2, 12], "multi_max": [2, 12]},
  "rubble": {"rest_s": [0, 120], "fade_s": [0.05, 20], "max_rubble": [0, 1000], "boulder_min": [1, 60],
             "boulder_max": [1, 80], "boulder_count": [0, 30], "hit_knockback": [0, 200], "hit_damage": [0, 1000],
             "speed": [0, 200], "cooldown_ms": [0, 10000]},
  "ground_fx": {"beam_min_damage": [0, 10000], "trench_width": [10, 500], "orb_min_damage": [0, 10000],
                "orb_crater": [10, 500], "crescent_min_damage": [0, 10000], "streak_width": [10, 500],
                "mark_s": [0, 120], "fade_s": [0.05, 20], "tilt_top": [1, 90], "tilt_bottom": [1, 90]},
  "roll": {"max_speed": [0, 5000], "zone_x_frac": [0.05, 0.5], "zone_y_frac": [0.05, 0.5], "ease_ms": [0, 5000], "spawn_ahead_px": [0, 3000],
           "margin_px": [0, 600]},
  "boulder_impact": {"speed_keep_pct": [0, 100], "damage_keep_pct": [0, 100], "chip_ms": [16, 5000]},
  "director": {"decay_pct_s": [0, 100], "close_px": [0, 3000], "close_pct_s": [0, 200], "hit_pct": [0, 100],
               "damage_pct": [0, 500], "counter_pct": [0, 100], "hp_swing_pct": [0, 500], "low_hp_at": [0, 100],
               "low_hp_pct_s": [0, 100], "ko_pct": [0, 100], "idle_after_s": [0, 60], "idle_pct_s": [0, 100],
               "build_at": [0, 100], "burst_at": [1, 100], "burst_jitter_pct": [0, 50], "burst_s_min": [0.2, 30],
               "burst_s_max": [0.2, 30], "after_burst_pct": [0, 100]},
  "team": {"tokens_team1": [0, 8], "tokens_team2": [0, 8], "token_range_pct": [50, 1000]},
  "smoke_cel": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline": [0,
               8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05, 0.95],
               "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise": [-60, 60],
               "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0, 10],
               "spread_pct": [0, 400], "lift_pct": [0, 400]},
  "smoke_billow": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline":
                  [0, 8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05,
                  0.95], "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise":
                  [-60, 60], "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0,
                  10], "spread_pct": [0, 400], "lift_pct": [0, 400]},
  "smoke_ink": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline": [0,
               8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05, 0.95],
               "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise": [-60, 60],
               "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0, 10],
               "spread_pct": [0, 400], "lift_pct": [0, 400]},
  "smoke_swirl": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline":
                 [0, 8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05, 0.95],
                 "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise": [-60, 60],
                 "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0, 10],
                 "spread_pct": [0, 400], "lift_pct": [0, 400]},
  "smoke_flat": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline": [0,
                8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05, 0.95],
                "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise": [-60, 60],
                "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0, 10],
                "spread_pct": [0, 400], "lift_pct": [0, 400]},
  "smoke_ring": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline": [0,
                8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05, 0.95],
                "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise": [-60, 60],
                "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0, 10],
                "spread_pct": [0, 400], "lift_pct": [0, 400]},
  "smoke_stepped": {"tones": [1, 3], "shadow": [0, 100], "light": [0, 100], "light_dir": [0, 360], "outline":
                   [0, 8], "tint_mix": [0, 100], "opacity": [5, 100], "grow": [0.5, 5], "grow_at": [0.05,
                   0.95], "steps": [1, 8], "hold": [1, 4], "fade": [0, 100], "life_pct": [10, 400], "rise":
                   [-60, 60], "tau_pct": [10, 500], "ground_keep": [0, 1], "wobble": [0, 20], "wobble_hz": [0,
                   10], "spread_pct": [0, 400], "lift_pct": [0, 400]}
};
var WP_ENUMS = {
  "smoke_cel": {"shrink": ["steps", "smooth", "erode", "none"]},
  "smoke_billow": {"shrink": ["steps", "smooth", "erode", "none"]},
  "smoke_ink": {"shrink": ["steps", "smooth", "erode", "none"]},
  "smoke_swirl": {"shrink": ["steps", "smooth", "erode", "none"]},
  "smoke_flat": {"shrink": ["steps", "smooth", "erode", "none"]},
  "smoke_ring": {"shrink": ["steps", "smooth", "erode", "none"]},
  "smoke_stepped": {"shrink": ["steps", "smooth", "erode", "none"]},
  "spiral": {"hand": ["right", "left"], "reach": ["behind", "ahead", "centered"], "in_mode": SPIRAL_MODES,
            "out_mode": SPIRAL_MODES, "in_dir": SPIRAL_DIRS, "out_dir": SPIRAL_DIRS},
  "ground": {"style": ["cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]},
  "dash": {"style": ["default", "cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]},
  "jump": {"style": ["default", "cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]},
  "slam": {"style": ["default", "cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]},
  "clash": {"style": ["default", "cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]},
  "blast": {"style": ["default", "cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]},
  "sonic": {"style": ["default", "cel", "billow", "ink", "swirl", "flat", "ring", "stepped"]}
};
// Labels and hover help for the Studio page: [key, label, help].
var WP_FIELDS = {
  ground: [["enabled", "World physics on", "Every Dust & Air effect, for every character."],
           ["flat_near", "Ground flatness, near", "Height / width of a ring spreading on the ground at the nearest spot (bottom-left). Lower = flatter."],
           ["flat_far", "Ground flatness, far", "The same at the farthest spot (top-right). Higher than near = rounder the farther away (the slope rises toward your eye)."],
           ["max_dust", "Most dust puffs", "Cap on simulated dust puffs on screen; the oldest go first. Lower it if the game slows."],
           ["tau_ms", "Dust response (ms)", "How fast dust takes up the speed of the air round it: low = rides every gust, high = keeps its own momentum."],
           ["ink", "Ink outline", "The outline colour round rocks and rings (each smoke style has its own outline colour)."],
           ["style", "Smoke style", "The look of every dust / smoke puff, unless an event below picks its own. Edit each style under Smoke styles."]],
  dash: [["enabled", "On", "Dust kicked up by fast movement."],
         ["speed", "Speed threshold (px/s)", "On-screen speed above which a fighter kicks up dust."],
         ["rate", "Puffs per second", "At the threshold speed; up to 3x faster above it."],
         ["inherit", "Velocity inherited %", "How much of the fighter's speed each puff starts with."],
         ["size", "Puff size %", ""], ["life_ms", "Puff life (ms)", ""],
         ["start_burst", "Start burst", "The first ticks of a dash throw triple the dust."],
         ["wake", "Wake", "A pocket of air dragged along behind the fighter carries the dust after it."],
         ["wake_pct", "Wake strength %", ""],
         ["curls", "Wake curls", "Curls of air shed alternately from either side of the body."],
         ["grit", "Grit per second", "Small pebbles flicked back by the feet."],
         ["color", "Dust colour", ""], ["style", "Smoke style", "The smoke look for this event; Ground default = the Ground & dust style."]],
  jump: [["enabled", "On", "Leaps (Movement leap) and hop-backs."],
         ["dust", "Dust puffs", ""], ["pebbles", "Pebbles", "Thrown steeply (55-75 degrees) on take-off."],
         ["ring", "Ground ring", ""], ["column", "Air column", "Air drawn up behind the jumper lifts the dust after them."],
         ["land", "Landing puff", ""], ["hops", "Hop-backs too", "A hop-back makes a half-size take-off and landing."],
         ["size", "Size %", ""], ["color", "Dust colour", ""], ["style", "Smoke style", "The smoke look for this event; Ground default = the Ground & dust style."],
         ["split", "Ring parts (0 = Pressure spiral)", "Split this event's pulse ring into 2-6 parts. 0 = take the Pressure spiral section's parts."],
         ["twist", "Spiral % (-1 = Pressure spiral)", "How far this event's ring is twisted into a spring along its direction. -1 = take the Pressure spiral section's value."]],
  slam: [["enabled", "On", "Knockback slides: launch, skid, crater, wall."],
         ["min_speed", "Minimum knockback (px/tick)", "Slower slides make no slam dust. A crater needs twice this."],
         ["launch", "Launch burst", "Dust and rocks thrown back where the hit lands."],
         ["skid", "Skid trail", "Dust along the slide."],
         ["crater", "Crater", "Where a heavy slide stops: scorched dish, rim of rising dust, rocks."],
         ["wall", "Wall slam", "A slide that hits a screen edge: a dust plane on the wall."],
         ["dust", "Dust puffs", ""], ["rocks", "Rocks", ""], ["size", "Size %", ""],
         ["color", "Dust colour", ""], ["rock_color", "Rock colour", ""], ["style", "Smoke style", "The smoke look for this event; Ground default = the Ground & dust style."],
         ["split", "Ring parts (0 = Pressure spiral)", "Split this event's pulse ring into 2-6 parts. 0 = take the Pressure spiral section's parts."],
         ["twist", "Spiral % (-1 = Pressure spiral)", "How far this event's ring is twisted into a spring along its direction. -1 = take the Pressure spiral section's value."]],
  clash: [["enabled", "On", "When two opposing effects clash (World Clash)."],
          ["sheet", "Splash sheet", "Dust thrown sideways to the hit, both ways."],
          ["dust", "Dust puffs", ""], ["sparks", "Sparks", ""],
          ["ground_jet", "Ground jet", "The downward half of the splash reaches the floor a beat later and runs out along it."],
          ["size", "Size %", ""], ["color", "Dust colour", ""], ["spark_color", "Spark colour", ""], ["style", "Smoke style", "The smoke look for this event; Ground default = the Ground & dust style."],
         ["split", "Ring parts (0 = Pressure spiral)", "Split this event's pulse ring into 2-6 parts. 0 = take the Pressure spiral section's parts."],
         ["twist", "Spiral % (-1 = Pressure spiral)", "How far this event's ring is twisted into a spring along its direction. -1 = take the Pressure spiral section's value."]],
  blast: [["enabled", "On", "Where a technique's shot detonates (ki blasts, charged blasts, rockets...)."],
          ["min_damage", "Minimum damage", "Weaker shots make no blast air."],
          ["strength", "Wind strength %", ""],
          ["suck_back", "Suck-back", "After the push, the air pulls back toward the centre."],
          ["reach", "Reach (px at damage 10)", "Grows with the cube root of the damage."],
          ["dust", "Dust puffs", ""], ["ring", "Ground ring", ""], ["size", "Size %", ""],
          ["color", "Dust colour", ""], ["style", "Smoke style", "The smoke look for this event; Ground default = the Ground & dust style."],
         ["split", "Ring parts (0 = Pressure spiral)", "Split this event's pulse ring into 2-6 parts. 0 = take the Pressure spiral section's parts."],
         ["twist", "Spiral % (-1 = Pressure spiral)", "How far this event's ring is twisted into a spring along its direction. -1 = take the Pressure spiral section's value."]],
  sonic: [["enabled", "On", "Breaking the sound barrier."],
          ["mach", "Sound speed (px/s)", "On-screen speed: near fighters (bottom-left) move faster on screen, so they break it more easily."],
          ["knockback", "Knockback slides count", "Off: only a fighter's own movement breaks the barrier."],
          ["cone", "Shock cone", "Bow shock lines at sin(angle) = 1 / Mach."],
          ["vapor", "Vapour collar", "Flickers just behind the nose near Mach 1."],
          ["boom", "Barrier ring", "A ring round the body the moment it crosses Mach 1."],
          ["boom_hz", "Boom frequency (per s)", "More barrier rings per second while it stays above Mach 1. 0 = once per crossing."],
          ["sweep", "Ground sweep", "Where the cone meets the floor, the air pushes out and pulls back."],
          ["color", "Shock colour", ""], ["style", "Smoke style", "The smoke look for this event; Ground default = the Ground & dust style."],
         ["split", "Ring parts (0 = Pressure spiral)", "Split this event's pulse ring into 2-6 parts. 0 = take the Pressure spiral section's parts."],
         ["twist", "Spiral % (-1 = Pressure spiral)", "How far this event's ring is twisted into a spring along its direction. -1 = take the Pressure spiral section's value."]],
  pillars: [["enabled", "On", "Rock pillars that rise around the fight (Solo and Battle). They block fighters and projectiles for both sides; the AI does not know about them. A hit breaks one outright when ANY of its speed, FX knockback or FX damage meets the threshold below (the hit carries on); anything under every threshold is blocked and chips its HP."],
           ["count", "Pillars in the arena", "How many stand at once. A round starts with this many; when one breaks a new one rises after Respawn time."],
           ["radius_x_px", "Spawn radius X (px)", "Pillars rise at random spots inside an ellipse round the fighters' centre (the world anchor while anchor scaling is on): this is how far it reaches left / right."],
           ["radius_y_px", "Spawn radius Y (px)", "How far the spawn ellipse reaches up / down."],
           ["clear_x_px", "Clear of fighters X (px)", "Never rises inside this ellipse round a fighter: left / right reach."],
           ["clear_y_px", "Clear of fighters Y (px)", "Up / down reach of the clear ellipse round each fighter."],
           ["gap_x_px", "Gap between pillars X (px)", "Never rises inside this ellipse round another pillar: left / right reach."],
           ["gap_y_px", "Gap between pillars Y (px)", "Up / down reach of the gap ellipse round each pillar."],
           ["respawn_s", "Respawn time (s)", "After a pillar breaks, a new one rises this long later (one at a time) until the arena holds the set count again."],
           ["width", "Width (px)", "At 100% scale; perspective (position scale) sizes it like the fighters."],
           ["height", "Height (px)", "At 100% scale."],
           ["rise_ms", "Rise time (ms)", "How long it takes to grow out of the ground."],
           ["hp", "HP", "Blocked hits chip this away; at 0 it crumbles. Cracks show as it drops."],
           ["break_damage", "Break: damage", "A hit dealing this much damage or more breaks it at once."],
           ["break_knockback", "Break: FX knockback", "An effect whose knockback is this or more breaks it at once."],
           ["break_speed", "Break: speed (px/tick)", "A projectile or a fighter (running, dashing or knocked back) moving this fast or faster breaks it at once."],
           ["chip_pct", "Chip damage %", "A blocked hit takes this % of its damage off the pillar's HP."],
           ["body_chip", "Body bump chip (HP)", "HP a fighter takes off when it bumps into it under the speed threshold."],
           ["melee_damage", "Built-in slash damage", "Damage the built-in sword's slashes and crescent waves deal to a pillar (FX Studio effects use their own damage)."],
           ["blast_reach", "Blast reach (px)", "Energy blasts hit pillars within this distance of the detonation."],
           ["repel", "Repel (px/tick)", "The very subtle push that slides a touching fighter away from the pillar's centre."],
           ["repel_px", "Repel range (px)", "How close (past touching) the repel starts."],
           ["block_projectiles", "Block projectiles", "Blocked bullets / FX are destroyed at the pillar. Off = they pass through (they still chip it)."],
           ["rubble", "Break chunks", "Rocks thrown when it breaks."],
           ["boulders", "Break boulders", "Big chunks thrown when it breaks (sizes from Rubble & boulders)."],
           ["color", "Rock colour", ""],
           ["facets", "Rock facets", "Sides of each pillar's low-poly rock (each pillar gets its own random shape)."],
           ["view_yaw", "View turn (°)", "2.5D look: how far the rock turns to show its side as it moves away from the fighters' centre (the world anchor). 0 = always straight on."],
           ["view_reach_frac", "Full turn distance (× width)", "Distance from the anchor at which the rock has turned the full View turn, as a share of the screen width."],
           ["pitch_bottom", "Look-down at bottom (°)", "Camera angle for a rock at the bottom of the screen: higher = more of its top face shows."],
           ["pitch_top", "Look-down at top (°)", "Camera angle for a rock at the top of the screen (less top face; never the underside)."],
           ["multi_chance", "Multi-part chance %", "Chance a new pillar is a multi-part boulder instead: a cluster of rock blocks, side by side and stacked. Each block has the pillar's HP and break thresholds and breaks on its own; blocks above a broken one drop down."],
           ["multi_size_pct", "Multi-part size %", "Footprint of a multi-part boulder, % of Width."],
           ["multi_min", "Blocks min", "Fewest blocks in a multi-part boulder."],
           ["multi_max", "Blocks max", "Most blocks in a multi-part boulder."]],
  rubble: [["enabled", "On", "Rocks that land stay on the ground, and heavy events throw boulders."],
           ["rest", "Resting rubble", "Rocks thrown by slams, craters, walls, pillar breaks and boulders lie where they land."],
           ["rest_s", "Rest time (s)", "How long landed rubble lies before it fades."],
           ["fade_s", "Fade (s)", ""],
           ["max_rubble", "Most rubble pieces", "Oldest go first."],
           ["boulders", "Boulders", "Big chunks thrown high by a hard hit, a heavy hit or a fast fighter."],
           ["boulder_min", "Boulder size min (px)", "At 100% scale."],
           ["boulder_max", "Boulder size max (px)", ""],
           ["boulder_count", "Boulders per event", "A fast fighter throws half as many, smaller."],
           ["hit_knockback", "Trigger: knockback (px/tick)", "A hit whose knockback slide starts at this speed or more throws boulders (and craters)."],
           ["hit_damage", "Trigger: damage", "A hit taking this much HP or more in one tick throws boulders (and craters)."],
           ["speed", "Trigger: fighter speed (px/tick)", "A fighter moving this fast kicks up boulders behind it."],
           ["cooldown_ms", "Cooldown per fighter (ms)", "Least time between two boulder events from one fighter."],
           ["crater", "Crater on hits", "Knockback / heavy-hit triggers also leave a crater."],
           ["color", "Boulder colour", ""]],
  ground_fx: [["enabled", "On", "FX Studio effects mark the ground (Solo and Battle)."],
           ["beam_min_damage", "Beam: damage over", "A beam whose damage is MORE than this gouges a trench along the ground under its head as it travels."],
           ["beam_trench", "Beam trench", "The scorched gouge left on the ground under the beam's path."],
           ["beam_debris", "Beam debris", "Rocks and dust kicked up where the beam's head meets the ground."],
           ["beam_spiral", "Beam pressure spiral", "The beam's head pulls a Pressure spiral trail, with the same logic as a fighter's sound-barrier trail (Sound barrier colour, Pressure spiral settings, Min speed gate)."],
           ["trench_width", "Trench width %", "Scales the trench with the beam's own width."],
           ["orb_min_damage", "Orb: crater at damage", "An orb (ki blast / gun round) that detonates on impact with this much damage or more leaves a crater."],
           ["orb_crater", "Orb crater size %", "Crater size grows with the orb's damage; this scales it."],
           ["crescent_min_damage", "Crescent: streak at damage", "A travelling crescent (crescent wave) with this much damage or more streaks the ground under it."],
           ["streak_width", "Streak width %", ""],
           ["mark_s", "Marks last (s)", "How long trenches, streaks and orb craters stay before they fade."],
           ["fade_s", "Marks fade (s)", ""],
           ["color", "Scorch colour", "The trench / streak floor."],
           ["tilt_top", "Look-down at top (°)", "Craters, trenches and streaks lie flat on the ground: the camera angle at the top of the screen. Low = nearly edge-on (on the horizon a trench is little more than a line)."],
           ["tilt_bottom", "Look-down at bottom (°)", "The camera angle at the bottom of the screen. 90 = looking straight down into the crater / trench. The tiny planet squashes them toward the anchor like the boulders."],
           ["merge", "Merge overlaps", "Overlapping craters, trenches and streaks share one outer outline: the outline inside the overlap is removed so they read as one gouge."]],
  roll: [["enabled", "On", "Rolling world (Solo and Battle): when the fighters' centre (the world anchor) is near a screen side the world rolls past them the other way, faster the nearer the edge, so they seem to travel great distances. Pillars, rubble, craters, marks and dust roll; the fighters are not moved. Pillars that roll off-screen are replaced off the side the world rolls in from."],
           ["max_speed", "Max roll speed (px/s)", "With the anchor right at the screen edge."],
           ["zone_x_frac", "Roll zone X (share of width)", "The outer share of the screen's width, left and right, where the roll starts (0.333 = the outer thirds). The middle is still."],
           ["zone_y_frac", "Roll zone Y (share of height)", "The outer share of the screen's height, top and bottom, where the up / down roll starts (needs Roll up / down too)."],
           ["vertical", "Roll up / down too", "Also roll when the anchor is near the top or bottom."],
           ["ease_ms", "Ease (ms)", "How long the roll takes to speed up / slow down."],
           ["spawn_ahead_px", "New pillars: spread (px)", "New pillars rise this far (at most) beyond the edge, so they come in at different times."],
           ["margin_px", "Off-screen margin (px)", "How far past the edge a pillar rolls before it is gone."]],
  director: [["enabled", "On", "The fight director (Solo and Battle): one intensity for the whole fight that every Fight rhythm fighter reads (FX Studio \"Fight rhythm\" on a character). Calm = spacing and setups, build = more engages, burst = longer strings, shorter gaps and resets. It never picks moves. Off = always calm."],
           ["decay_pct_s", "Cool down % / s", "How fast the intensity falls back toward calm on its own."],
           ["close_px", "Close range px", "Fighters nearer than this (Solo: a fighter and the cursor) heat the fight up, more the closer they are."],
           ["close_pct_s", "Closeness heat % / s", "Intensity per second at point-blank range."],
           ["hit_pct", "Per hit %", "Intensity added by every landed hit."],
           ["damage_pct", "Per damage %", "Intensity added per one fighter's worth of HP dealt (big hits heat it more)."],
           ["counter_pct", "Per counter %", "Intensity added by every dodge, parry or negated hit."],
           ["hp_swing_pct", "HP swing %", "Intensity added per one fighter's worth of HP lost (a big HP drop spikes it)."],
           ["low_hp_at", "Low HP at %", "While any fighter is at or below this HP %..."],
           ["low_hp_pct_s", "Low HP heat % / s", "...the intensity keeps rising this fast."],
           ["ko_pct", "Per KO %", "Intensity added by a KO."],
           ["idle_after_s", "Quiet after s", "No hits or counters for this long counts as a quiet spell..."],
           ["idle_pct_s", "Quiet tension % / s", "...during which tension builds by itself, so a burst always comes eventually."],
           ["build_at", "Build at %", "Intensity from which the phase is BUILD (below = CALM)."],
           ["burst_at", "Burst at %", "Intensity that sets off a BURST."],
           ["burst_jitter_pct", "Burst threshold jitter %", "Each cycle's burst threshold moves by up to this much, so bursts never come on a beat."],
           ["burst_s_min", "Burst lasts min s", "A burst lasts a random time between min and max."],
           ["burst_s_max", "Burst lasts max s", ""],
           ["after_burst_pct", "After a burst %", "The intensity right after a burst ends (back to calm)."]],
  team: [["enabled", "On", "Team play (Battle, and Solo with several Team 1 fighters): each team shares a squad board (roles, intents, callouts) and melee attack tokens. Fight rhythm fighters without a token wait (flank / circle / zone) instead of piling in. Off = no token limit."],
         ["tokens_team1", "Team 1 melee tokens", "How many Team 1 fighters may melee the same target at once (0 = no limit). Ranged attacks never need one."],
         ["tokens_team2", "Team 2 melee tokens", "How many Team 2 fighters may melee the same target at once (0 = no limit)."],
         ["token_range_pct", "Player token reach %", "The player-controlled fighter (F4) holds a token while its target is within this % of its normal attack range."]],
  boulder_impact: [["enabled", "On", "Boulders and the blocks of multi-part boulders slow what hits them (Solo and Battle). Every block or boulder a fighter or an effect collides with cuts its speed (and an effect's damage) at that moment. An effect keeps the reduced damage for the rest of its life; the next attack starts at full damage again."],
           ["speed_keep_pct", "Speed kept per collision %", "50 = half the speed it had when it hit. A projectile / travelling effect that breaks the block flies on this slowly; a knockback slide that breaks it slides on this slowly; one that doesn't break it bounces off this slowly."],
           ["damage_keep_pct", "Damage kept per collision %", "50 = half the damage it had when it hit. The break check uses the damage BEFORE the cut. An effect left under the block's break damage is stuck there until its life ends."],
           ["chip_ms", "Stuck effect: chip every (ms)", "A stuck effect keeps chipping the block it is stuck on (Chip damage % of its reduced damage). If the block crumbles it flies on again."],
           ["fighters", "Fighters too", "Knockback slides are slowed / bounced at the cut speed. Off = fighters as before."]],
  spiral: [["enabled", "On", "Every Dust & Air ring (the pulse each jump, slam, clash, blast and sound barrier throws) takes these settings. Parts 1 + Spiral 0 = the plain ring."],
           ["parts", "Parts", "Split the ring into 2-6 parts, evenly round the circle (2 = left and right arcs, 4 = four arcs)."],
           ["gap", "Gap between parts %", "How much of each part's share of the circle is left empty (needs 2 or more parts)."],
           ["rotation", "Rotate pattern (deg)", "Turns where the parts' gaps sit, and where the spiral starts."],
           ["life_pct", "Ring life %", "How long rings last; longer lets a slow create / dissolve play out."],
           ["spiral", "Spiral %", "0 = a flat ring (a circle seen end-on). 100 = the ring seen side-on as a spring, laid along the direction of the action. In between blends the two."],
           ["spin_hz", "Rotation frequency (coils/s)", "How often the spring completes a coil. Coil spacing = speed / frequency, so the coils come from the distance travelled rather than a fixed count."],
           ["min_speed", "Min speed (px/s)", "At or below this speed the coils are packed as tight as they get (slow movement = coils close together)."],
           ["max_speed", "Max speed (px/s)", "At or above this speed the coils are spread as far as they get (fast movement = a stretched spiral)."],
           ["trail", "Live trail (sound barrier)", "While the fighter moves at or above Min speed (below it nothing starts) the air it bursts through winds into a spring built in real time on its actual path - a hard turn bends it right there. Moderate speed = thick cursive loops; faster = the coils stretch and the thread thins; Max speed = a straight streak. The thread is material: stretched (coils opening, pulled round a turn) it thins, friction wears it with age, and the oldest, thinnest parts dissolve first. It lives Ring life %."],
           ["radius_speed_pct", "Radius from speed %", "How much WIDER the spiral's coils swing (their radius, not the line thickness) as the fighter gets faster: the radius is x1 at Min speed and grows by this much at Max speed. 0 = the radius never changes with speed."],
           ["thread_px", "Thread thickness (px)", "How thick the spiral's line is (not its radius). Scaled by perspective like the rest of the world. A trail coil is born this thick (no outline: white air)."],
           ["segments", "Thread segments (per coil)", "Smoothness: how many line pieces make up each coil of the thread. More = a rounder, smoother curve (and a little more drawing work)."],
           ["tail_pct", "Tail thickness %", "Not used by the live trail (its thread thins by stretch and friction)."],
           ["expand_pct", "Push-out %", "How far each coil is pushed out of the spring's centre as it ages: 600 = 7x as tall by the end of its life (across the travel; it hardly widens along it), so loops grow into tall arches. The stretched legs thin and tear first; the crowns last longest."],
           ["thin_pct", "Thickness at max speed %", "How thick the trail's thread is at Max speed, as a % of Thread thickness. Moderate speed = a thick thread; blistering speed = this thin."],
           ["streak_pct", "Streak at max speed %", "How flat the coils get at Max speed: 100 = a perfectly straight streak of air (like a laser trail), 0 = they keep their full loop."],
           ["drift_pct", "Inertia %", "How much of the fighter's momentum the trail carries on with. On a hard turn the streak keeps flying the old way and swings round after it. 0 = it sits exactly on the path."],
           ["length_pct", "Length %", "How much of the distance travelled the spring covers (100 = all of it). A take-off or clash has no track, so it takes a length from the ring."],
           ["radius_pct", "Coil radius %", "How wide the coils swing, from the ring's own size (used when Scale to thrower is off or the thrower is unknown)."],
           ["body_scale", "Scale to thrower", "The coils' base radius is the size of the fighter that made it, so the spiral looks like it comes from that body."],
           ["body_pct", "Thrower size %", "Scales the coil radius taken from the fighter's body."],
           ["taper", "Taper %", "Positive widens the coils toward the end of the spring; negative tightens them (a shock cone)."],
                      ["hand", "Handedness", "Which way the coils wind."],
           ["reach", "Reaches", "Behind the action (a trail), ahead of it, or centred on it."],
           ["speed_len", "Length from power %", "Only for rings with no track (take-off, clash): a harder action stretches the spring longer."],
           ["in_ms", "Create time (ms)", "How long the ring takes to be drawn in. 0 = it appears at once."],
           ["in_mode", "Create: how", "Whole shape = every part fades in together. Parts together = every part draws in at the same time. Part by part = one after another."],
           ["in_dir", "Create: direction / order", "Left to right / right to left across the screen, or in the order the parts were created (or reversed). Sets the sweep inside each part, and the order part by part."],
           ["out_ms", "Dissolve time (ms)", "How long the ring takes to dissolve at the end of its life. 0 = the plain fade."],
           ["out_mode", "Dissolve: how", "Whole shape = everything fades together. Parts together = each part is wiped away at the same time. Part by part = one after another."],
           ["out_dir", "Dissolve: direction / order", "Left to right / right to left, or in creation order (or reversed)."]]
};
var SMOKE_FIELDS = [
  ["tones", "Tones", "Shading bands: 1 = flat, 2 = shadow + base, 3 = shadow + base + highlight."],
  ["shadow", "Shadow depth %", "How much darker the shadow tone is."],
  ["light", "Highlight %", "How much lighter the highlight is."],
  ["light_dir", "Light from (deg)", "Where the light comes from: 0 = right, 90 = below, 180 = left, 225 = upper left, 270 = above."],
  ["outline", "Outline width", "Ink line round the smoke (0 = none)."],
  ["ink", "Outline colour", ""],
  ["tint", "Tint colour", "Mixed into the event's dust colour."],
  ["tint_mix", "Tint %", "0 = the event's colour as is."],
  ["opacity", "Opacity %", ""],
  ["grow", "Peak size (x)", "How big a puff grows, from its spawn size."],
  ["grow_at", "Peak at (life)", "When it reaches peak size, as a share of its life (0.6 = 60 %)."],
  ["shrink", "Shrink", "After the peak: steps = snaps smaller in steps, smooth, erode = keeps its size and is eaten away in steps, none."],
  ["steps", "Steps", "Steps for the step shrink / erode."],
  ["hold", "Held frames", "1 = moves every tick (on ones), 2 = on twos, 3 = on threes: the held-frame anime cadence."],
  ["fade", "Fade out %", "Share of the end of its life spent fading (0 = pops out)."],
  ["life_pct", "Life %", "Scales how long puffs last."],
  ["rise", "Rise (buoyancy)", "Up-drift per tick (negative sinks); crater rims and clash sheets keep their own."],
  ["tau_pct", "Air response %", "How fast it takes up the wind: low = rides every gust, high = keeps its own momentum."],
  ["ground_keep", "Ground slide", "Speed kept per tick while touching the ground (1 = slides forever, 0 = stops dead)."],
  ["wobble", "Wobble (px)", "Turbulent sway, drawn only."],
  ["wobble_hz", "Wobble speed (Hz)", ""],
  ["spread_pct", "Spread %", "Scales how fast puffs fly out sideways."],
  ["lift_pct", "Lift %", "Scales how fast puffs launch upward."]
];
var WP_STYLE_TITLES = {cel: "Cel puff", billow: "Billow / cauliflower", ink: "Ink wash (sumi)", swirl: "Swirl / curl",
  flat: "Flat graphic", ring: "Ring puff", stepped: "Stepped / dithered"};
WP_SMOKE_STYLES.forEach(function (st) { WP_FIELDS["smoke_" + st] = SMOKE_FIELDS; });
var WP_TITLES = {ground: "Ground & dust", dash: "Dash / fast movement", jump: "Jump take-off & landing",
  slam: "Knockback slams", clash: "Clashes", blast: "Energy blasts", sonic: "Sound barrier", spiral: "Pressure spiral (pulse rings)",
  pillars: "Rock pillars (destructible)", rubble: "Rubble & boulders", ground_fx: "FX on the ground",
  roll: "Rolling world", boulder_impact: "Boulder impact",
  director: "Fight director (rhythm)", team: "Team play (attack tokens)"};
WP_SMOKE_STYLES.forEach(function (st) { WP_TITLES["smoke_" + st] = "Smoke: " + WP_STYLE_TITLES[st]; });

var TICK_MS = 16, TICK_S = TICK_MS / 1000;
// Position grids (laser/config.py POSITION_SCALE_* / SPEED_SCALE_*): TL, TR, BL, BR.
var PS = [2.3333, 1.0, 5.0, 2.3333], SS = [0.6, 0.4, 1.0, 0.6];
var PS_LO = Math.min.apply(null, PS), PS_HI = Math.max.apply(null, PS);
var TELEPORT_PX = 40;

function hex(v, d) { return (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v)) ? v.toLowerCase() : d; }
// Settings split into x / y: an old file's single value seeds both.
var WP_LEGACY_XY = {"pillars": {"radius_px": ["radius_x_px", "radius_y_px"], "clear_px": ["clear_x_px", "clear_y_px"],
                                "gap_px": ["gap_x_px", "gap_y_px"]},
                    "roll": {"zone_frac": ["zone_x_frac", "zone_y_frac"]}};
function normalizeSection(name, s) {
  s = (s && typeof s === "object") ? Object.assign({}, s) : {};
  var lg = WP_LEGACY_XY[name] || {};
  Object.keys(lg).forEach(function (o) {
    if (s.hasOwnProperty(o)) lg[o].forEach(function (k) { if (!s.hasOwnProperty(k)) s[k] = s[o]; });
  });
  var dflt = WP_DEFAULTS[name], rng = WP_RANGES[name] || {}, en = WP_ENUMS[name] || {}, out = {};
  Object.keys(dflt).forEach(function (k) {
    var d = dflt[k], v = s.hasOwnProperty(k) ? s[k] : d;
    if (typeof d === "boolean") out[k] = !!v;
    else if (en[k]) out[k] = en[k].indexOf(v) >= 0 ? v : d;
    else if (typeof d === "string") out[k] = hex(v, d);
    else {
      v = parseFloat(v); if (!isFinite(v)) v = d;
      var r = rng[k] || [-1e9, 1e9];
      out[k] = Math.max(r[0], Math.min(r[1], v));
    }
  });
  return out;
}
function normalize(c) {
  c = (c && typeof c === "object") ? c : {};
  var out = {format: WP_FORMAT};
  WP_SECTIONS.forEach(function (n) { out[n] = normalizeSection(n, c[n]); });
  return out;
}
function normalizeOverride(c) {
  c = (c && typeof c === "object") ? c : {};
  var out = {};
  WP_SECTIONS.forEach(function (n) { if (c[n] && typeof c[n] === "object") out[n] = normalizeSection(n, c[n]); });
  return out;
}

function bil(xf, yf, g) {
  var top = g[0] * (1 - xf) + g[1] * xf, bot = g[2] * (1 - xf) + g[3] * xf;
  return top * (1 - yf) + bot * yf;
}
function clamp01(v) { return Math.max(0, Math.min(1, v)); }
function escale(e) { return Math.max(0.45, Math.min(2.6, Math.pow(Math.max(0, e), 1 / 3))); }
function rgb(h) { return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16), parseInt(h.substr(5, 2), 16)]; }
function mix(c, tint, k) {
  if (k <= 0) return c;
  var t = rgb(tint);
  return [0, 1, 2].map(function (i) { return Math.round(c[i] + (t[i] - c[i]) * k); });
}
function css(c, a) { return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + (a == null ? 1 : a) + ")"; }

// ---------------------------------------------------------------- air sources
function Blast(x, y, s, ps, reach, strength, suck, flat) {
  this.x = x; this.y = y; this.age = 0;
  this.T = Math.max(4, 0.32 * s / TICK_S); this.ts = Math.max(2, 0.2 * s / TICK_S);
  this.rmax = Math.max(10, reach * s * ps); this.amp = 4.0 * s * ps * strength;
  this.suck = suck; this.flat = Math.max(0.05, flat); this.life = this.T + 6 * this.ts;
}
Blast.prototype.bbox = function () { var r = this.rmax; return [this.x - r, this.y - r * this.flat, this.x + r, this.y + r * this.flat]; };
Blast.prototype.air = function (x, y, z) {
  var dx = x - this.x, dy = (y - this.y) / this.flat, r = Math.sqrt(dx * dx + dy * dy);
  if (r >= this.rmax) return null;
  var tau = this.age - this.T * Math.pow(r / this.rmax, 2.5);
  if (tau < 0) return null;
  var q = tau / this.ts, p = Math.exp(-q) * (1 - q);
  if (p < 0 && !this.suck) return null;
  var a = this.amp * p * (1 - r / this.rmax) / Math.max(r, 4);
  return [dx * a, dy * a * this.flat, p > 0 ? 0.35 * a * r : 0];
};
function Wake(x, y, d) { this.x = x; this.y = y; this.vx = this.vy = 0; this.d = Math.max(6, d); this.k = 0; this.age = 0; this.life = 1e9; this.live = true; }
Wake.prototype.bbox = function () { var r = this.d * 4; return [this.x - r, this.y - r * 1.5, this.x + r, this.y + r]; };
Wake.prototype.air = function (x, y, z) {
  var sp = Math.hypot(this.vx, this.vy);
  if (sp < 0.01 || this.k < 0.01) return null;
  var cx = this.x - this.vx / sp * this.d * 0.8, cy = this.y - this.vy / sp * this.d * 0.8;
  var dx = x - cx, dy = y - cy, q = (dx * dx + dy * dy + z * z) / (this.d * this.d * 1.6);
  if (q > 9) return null;
  var w = this.k * Math.exp(-q);
  return [this.vx * w, this.vy * w, 0];
};
function Curl(x, y, g, rc) { this.x = x; this.y = y; this.g = g; this.rc = Math.max(4, rc); this.age = 0; this.life = 0.6 / TICK_S; }
Curl.prototype.bbox = function () { var r = 4 * this.rc * (1 + this.age / 18); return [this.x - r, this.y - r, this.x + r, this.y + r * 3]; };
Curl.prototype.air = function (x, y, z) {
  var rc = this.rc * (1 + this.age / 18), dx = x - this.x, dy = (y - z) - this.y, r2 = dx * dx + dy * dy;
  if (r2 > 16 * rc * rc) return null;
  var f = this.g * (1 - this.age / this.life) * Math.exp(-r2 / (2 * rc * rc)) / rc;
  return [-dy * f, 0, -dx * f];
};
function Column(x, y, w, r, flat) { this.x = x; this.y = y; this.w = w; this.r = Math.max(6, r); this.age = 0; this.flat = Math.max(0.05, flat); this.life = 26; }
Column.prototype.bbox = function () { var r = 3 * this.r; return [this.x - r, this.y - r * this.flat, this.x + r, this.y + r * this.flat]; };
Column.prototype.air = function (x, y, z) {
  var dx = x - this.x, dy = (y - this.y) / this.flat, q = (dx * dx + dy * dy) / (this.r * this.r);
  if (q > 9) return null;
  var k = this.w * (1 - this.age / this.life) * Math.exp(-q);
  return [-dx / this.r * k * 0.3, -dy * this.flat / this.r * k * 0.3, k];
};
function Jet(x, y, j, c, wd, flat, axis, out) {
  this.x = x; this.y = y; this.j = j; this.c = c; this.wd = Math.max(4, wd);
  this.age = 0; this.life = 28; this.flat = Math.max(0.05, flat); this.axis = axis || null; this.out = out || [0, 0];
}
Jet.prototype.bbox = function () {
  var r = this.age * this.c + 3 * this.wd + 2, w = 3 * this.wd;
  if (this.axis === "v") return [this.x - w, this.y - r, this.x + w, this.y + r * 3];
  if (this.axis === "h") return [this.x - r, this.y - w, this.x + r, this.y + w];
  return [this.x - r, this.y - r * this.flat, this.x + r, this.y + r * this.flat];
};
Jet.prototype.air = function (x, y, z) {
  var dx, dy, fall = 1, q0;
  if (this.axis === "v") { dx = 0; dy = (y - z) - this.y; q0 = (x - this.x) / (3 * this.wd); fall = Math.exp(-q0 * q0); }
  else if (this.axis === "h") { dx = x - this.x; dy = 0; q0 = (y - this.y) / (3 * this.wd); fall = Math.exp(-q0 * q0); }
  else { dx = x - this.x; dy = (y - this.y) / this.flat; }
  var r = Math.sqrt(dx * dx + dy * dy), q = (r - this.age * this.c) / this.wd;
  if (q * q > 9 || r < 0.5) return null;
  if (fall < 0.01) return null;
  var e = Math.exp(-this.age / 10) * Math.exp(-q * q), k = this.j * fall * e / r;
  var ux = dx * k, uy = dy * k * (this.axis ? 1 : this.flat), w = this.j * fall * 0.6 * e;
  if (this.axis === "v") return [this.out[0] * w, 0, -uy];
  if (this.axis === "h") return [ux, this.out[1] * w, 0];
  return [ux, uy, 0];
};

// ---------------------------------------------------------------- closed-form debris
function Burst(x, y, ps, ss, kind, pieces, g, k, e, life, col) {
  this.x = x; this.y = y; this.ps = ps; this.ss = ss; this.age = 0; this.kind = kind; this.pieces = pieces;
  this.g = g; this.k = k; this.e = e; this.life = life; this.col = col;
}
Burst.prototype.at = function (pc, t) {
  var ca = pc[0], sa = pc[1], h = pc[2], v = pc[3], g = this.g, k = this.k, e = this.e;
  var dist = k < 0.9999 ? h * (1 - Math.pow(k, t)) / (1 - k) : h * t;
  var t1 = g > 0 ? 2 * v / g : 1e9, z;
  if (t <= t1) z = v * t - 0.5 * g * t * t;
  else {
    if (this.kind === "spark") return null;
    var d1 = k < 0.9999 ? h * (1 - Math.pow(k, t1)) / (1 - k) : h * t1;
    dist = d1 + 0.45 * (dist - d1);
    var v2 = v * e, t2 = g > 0 ? 2 * v2 / g : 0, tt = t - t1;
    z = tt <= t2 ? v2 * tt - 0.5 * g * tt * tt : 0;
  }
  return [this.x + ca * dist, this.y + sa * dist, Math.max(0, z)];
};
function Ring(kind, x, y, life, r, flat, edge, col, w, ax, k, spd, dist, body) {
  this.kind = kind; this.x = x; this.y = y; this.age = 0; this.life = Math.max(2, life); this.r = r;
  this.flat = flat == null ? 1 : flat; this.edge = edge || null; this.col = col || [255, 255, 255]; this.w = w == null ? 6 : w;
  // ax: the action's direction (deg, screen) the spiral runs along; k: its power; sp: split / spiral settings (addRing).
  this.ax = ax || 0; this.k = k == null ? 1 : k; this.sp = null;
  // spd: on-screen speed (px/s) of the thrower, dist: the way it travelled (px), body: thrower body radius (px).
  this.spd = spd || 0; this.dist = dist || 0; this.body = body || 0;
}
// The Pressure spiral settings a new ring takes (null = the plain ring): the "spiral" section with the event's split / twist.
Sim.prototype.ringSplit = function (fig, sec) {
  var s = this.cfg(fig, "spiral");
  if (!s.enabled) return null;
  var n = Math.round(s.parts), tw = s.spiral, ov, t;
  if (sec) {
    ov = Math.round(sec.split || 0); if (ov > 0) n = ov;
    t = sec.twist == null ? -1 : sec.twist; if (t >= 0) tw = t;
  }
  if (n <= 1 && tw <= 0) return null;
  var d = {}; Object.keys(s).forEach(function (k) { d[k] = s[k]; });
  d.n = Math.max(1, Math.min(6, n)); d.tw = Math.max(0, Math.min(1, tw / 100));
  return d;
};

// ---------------------------------------------------------------- the simulation
// opts: {sw, sh, world (normalized), cfgFor(fig, section) optional}
function Sim(opts) {
  this.sw = opts.sw || 1120; this.sh = opts.sh || 630;
  this.world = opts.world || normalize({});
  this.cfgFor = opts.cfgFor || null;
  this.reset();
}
Sim.prototype.reset = function () {
  this.dust = []; this.src = []; this.bursts = []; this.rings = []; this.trails = []; this.later = []; this.tracks = new Map(); this.walls = []; this.t = 0;
  this.cur = this.smokeFor(null, null); this.curFx = [null, null];
};
// (style, its deep-edit profile) for puffs an event section spawns: the
// section's own style, or the ground's default ("default").
Sim.prototype.smokeFor = function (fig, sec) {
  var st = (sec && sec.style) || "default";
  if (WP_SMOKE_STYLES.indexOf(st) < 0) st = this.cfg(fig, "ground").style;
  if (WP_SMOKE_STYLES.indexOf(st) < 0) st = "cel";
  return [st, this.cfg(fig, "smoke_" + st)];
};
Sim.prototype.use = function (fig, sec) { this.cur = this.smokeFor(fig, sec); this.curFx = [fig, sec]; };
// Only this one smoke style, whatever the settings say (the style swatch).
Sim.prototype.forceStyle = null;
Sim.prototype.cfg = function (fig, name) {
  if (fig && fig.wp && fig.wp[name]) return fig.wp[name];
  return this.world[name];
};
Sim.prototype.ps = function (x, y) { return bil(clamp01(x / this.sw), clamp01(y / this.sh), PS); };
Sim.prototype.ssc = function (x, y) { return bil(clamp01(x / this.sw), clamp01(y / this.sh), SS); };
Sim.prototype.flat = function (x, y) {
  var g = this.world.ground, ps = this.ps(x, y), f = clamp01((PS_HI - ps) / (PS_HI - PS_LO));
  return g.flat_near + (g.flat_far - g.flat_near) * f;
};
Sim.prototype.addSrc = function (s) { if (this.src.length >= 24) this.src.shift(); this.src.push(s); return s; };
Sim.prototype.addRing = function (r) {
  if (r.kind === "ground" || r.kind === "boom") {
    var f = this.curFx || [null, null];
    r.sp = this.ringSplit(f[0], f[1]);
    if (r.sp) r.life = Math.max(2, r.life * r.sp.life_pct / 100);
  }
  if (this.rings.length >= 40) this.rings.shift(); this.rings.push(r);
};
// Record: x y z vx vy vz age life r0 tau rgb grav style prof seed keep.
Sim.prototype.puff = function (x, y, z, vx, vy, vz, life, r0, col, tau, grav) {
  var g = this.world.ground, cur = this.forceStyle ? [this.forceStyle, this.cfg(null, "smoke_" + this.forceStyle)] : this.cur;
  var st = cur[0], pr = cur[1], sp = pr.spread_pct / 100, lf = pr.lift_pct / 100;
  tau = (tau == null ? g.tau_ms / TICK_MS : tau) * pr.tau_pct / 100;
  if (grav == null) grav = -pr.rise / 1000;
  this.dust.push([x, y, z, vx * sp, vy * sp, vz * lf, 0, Math.max(4, life * pr.life_pct / 100), r0, Math.max(1, tau),
    mix(col, pr.tint, pr.tint_mix / 100), grav, st, pr, Math.random() * 6.283, pr.ground_keep]);
};
Sim.prototype.puffs = function (x, y, n, sp, col, size, lifeMs, az, spread, up, r0, flat) {
  if (n <= 0) return;
  var ps = this.ps(x, y), fl = flat == null ? this.flat(x, y) : flat, R = Math.random;
  spread = spread == null ? 360 : spread; up = up || [0.2, 1]; r0 = r0 || 6;
  for (var i = 0; i < Math.floor(n); i++) {
    var a = ((az || 0) + (R() - 0.5) * spread) * Math.PI / 180, s = sp * (0.4 + 0.6 * R()) * ps;
    this.puff(x + (R() - 0.5) * 6 * ps, y + (R() - 0.5) * 3 * ps, R() * 3 * ps, Math.cos(a) * s, Math.sin(a) * s * fl,
      (up[0] + (up[1] - up[0]) * R()) * ps, lifeMs / TICK_MS * (0.7 + 0.6 * R()), r0 * size * (0.7 + 0.6 * R()), col);
  }
};
Sim.prototype.debris = function (x, y, kind, n, s, col, o) {
  if (n <= 0) return;
  o = o || {};
  if (this.bursts.length >= 40) this.bursts.shift();
  var ps = this.ps(x, y), ss = this.ssc(x, y), fl = this.flat(x, y), R = Math.random, pieces = [];
  var spread = o.spread == null ? 360 : o.spread, elev = o.elev || [30, 62], spd = o.spd || [3, 9], size = o.size || [2, 5];
  for (var i = 0; i < Math.floor(n); i++) {
    var a = ((o.az || 0) + (R() - 0.5) * spread) * Math.PI / 180, sp, el;
    if (o.pi) { var u = 0.25 + 0.75 * R(); sp = Math.min(spd[1] * 1.6, spd[0] * Math.pow(u, -1.1)) * Math.sqrt(s); el = (62 - 27 * u) * Math.PI / 180; }
    else { sp = (spd[0] + (spd[1] - spd[0]) * R()) * Math.sqrt(s); el = (elev[0] + (elev[1] - elev[0]) * R()) * Math.PI / 180; }
    pieces.push([Math.cos(a), Math.sin(a) * fl, sp * Math.cos(el) * ps, sp * Math.sin(el) * ps,
      (size[0] + (size[1] - size[0]) * R()) * ps, (R() - 0.5) * 0.5, R() * 6.28]);
  }
  if (kind === "spark") this.bursts.push(new Burst(x, y, ps, ss, kind, pieces, 0.22 * ps, 0.974, 0, 34, col));
  else this.bursts.push(new Burst(x, y, ps, ss, kind, pieces, 0.34 * ps, kind === "rock" ? 0.994 : 0.98, 0.35, kind === "rock" ? 95 : 60, col));
};
// A preview fighter: {x, y, h (foot offset at 100 %), motion{bouncing, bounce_ending, bounce_vx, bounce_vy},
// hop_ticks, leap {sx, sy, ex, ey, t0, t1, h, done}, wp (override sections)}.
Sim.prototype.bodyR = function (fig, ps) { return fig ? (fig.h || 24) * ps * 0.5 : 0; };
Sim.prototype.foot = function (fig, ps) { var h = (fig.h || 24) * 0.46 * ps; return [fig.x, fig.y + h, h]; };
Sim.prototype.noteWall = function (fig, edge, speed) { this.walls.push([fig, edge, fig.x, fig.y, speed]); };
Sim.prototype.step = function (figs) {
  var self = this; this.t++;
  if (!this.world.ground.enabled) { this.reset(); return; }
  var due = this.later.filter(function (e) { return e[0] <= self.t; });
  this.later = this.later.filter(function (e) { return e[0] > self.t; });
  due.forEach(function (e) { e[1].apply(self, e[2]); });
  (figs || []).forEach(function (f) { self.observe(f); });
  this.walls.forEach(function (w) { self.wall(w[0], w[1], w[2], w[3], w[4]); });
  this.walls = [];
  this.tracks.forEach(function (tr, f) { if (tr.seen !== self.t) self.tracks.delete(f); });
  this.move();
};
Sim.prototype.observe = function (fig) {
  var tr = this.tracks.get(fig), ps = this.ps(fig.x, fig.y), ft = this.foot(fig, ps), fx = ft[0], fy = ft[1], hh = ft[2];
  var lp = fig.leap, z = 0;
  if (lp && !lp.done && lp.h > 0) {
    var u = (tr && tr.leap === lp) ? Math.min(1, (tr.leap_n + 1) / Math.max(1, tr.leap_t)) : 0;
    z = lp.h * 4 * u * (1 - u); fy += z;
  }
  if (!tr) { tr = {px: fx, py: fy, fast: false, slow: 99, burst: 0, acc: 0, gacc: 0, wake: null, shed: 0, sign: 1,
    bouncing: false, v0: 0, leap: null, leap_n: 0, leap_t: 1, hop: false, mach: 0, seen: 0, nx: 0, ny: 0, sp: 0, head: [fx, fy], sweep: 0, boom_t: 0, trail: null};
    this.tracks.set(fig, tr); }
  tr.seen = this.t;
  var dx = fx - tr.px, dy = fy - tr.py; tr.px = fx; tr.py = fy;
  var jump = Math.hypot(dx, dy);
  if (jump > TELEPORT_PX) { dx = dy = 0; jump = 0; }
  var sp = jump / TICK_S; tr.sp = sp;
  if (jump > 0.01) { tr.nx = dx / jump; tr.ny = dy / jump; }
  tr.head = [fig.x, fig.y];
  var m = fig.motion || {bouncing: false, bounce_ending: false, bounce_vx: 0, bounce_vy: 0};
  this.leapEvents(fig, tr, lp, fx, fy, ps);
  this.hopEvents(fig, tr, fx, fy, ps);
  this.knockEvents(fig, tr, m, fx, fy, ps, jump);
  this.dashEvents(fig, tr, fx, fy, ps, z, dx, dy, sp, hh);
  this.sonicEvents(fig, tr, m, fx, fy, ps, sp, hh);
};
Sim.prototype.leapEvents = function (fig, tr, lp, fx, fy, ps) {
  var c = this.cfg(fig, "jump"), live = lp && !lp.done && lp.h > 0;
  this.use(fig, c);
  if (live && tr.leap !== lp) {
    tr.leap = lp; tr.leap_n = 0; tr.leap_t = Math.max(1, Math.round((lp.t1 - lp.t0) / TICK_MS));
    if (c.enabled) this.takeoff(fig, fx, fy, ps, 1, c);
  } else if (live) tr.leap_n++;
  else if (tr.leap) {
    var land = tr.leap; tr.leap = null;
    if (c.enabled && c.land) this.landing(fig, land.ex == null ? fx : land.ex, fy, ps, 1, c);
  }
};
Sim.prototype.hopEvents = function (fig, tr, fx, fy, ps) {
  var hop = (fig.hop_ticks || 0) > 0, c = this.cfg(fig, "jump");
  this.use(fig, c);
  if (hop && !tr.hop && c.enabled && c.hops) this.takeoff(fig, fx, fy, ps, 0.5, c);
  else if (tr.hop && !hop && c.enabled && c.hops && c.land) this.landing(fig, fx, fy, ps, 0.5, c);
  tr.hop = hop;
};
Sim.prototype.takeoff = function (fig, x, y, ps, k, c) {
  var sz = c.size / 100 * k, col = rgb(c.color), fl = this.flat(x, y);
  if (c.ring) this.addRing(new Ring("ground", x, y, 16, 46 * sz * ps, fl, null, [255, 255, 255], 6 * ps * sz, -90, sz, 0, 0, this.bodyR(fig, ps)));
  this.puffs(x, y, c.dust * k, 2.6, col, sz, 650, 0, 360, [0.05, 0.4], 6);
  this.debris(x, y, "pebble", Math.floor(c.pebbles * k), sz, col, {elev: [55, 75], spd: [4, 8], size: [1.5, 3.5]});
  this.addSrc(new Jet(x, y, 1.6 * ps * sz, 2.2 * ps, 10 * ps, fl));
  if (c.column) this.addSrc(new Column(x, y, 1.4 * ps * sz, 26 * ps * sz, fl));
};
Sim.prototype.landing = function (fig, x, y, ps, k, c) {
  var sz = c.size / 100 * k * 0.6, col = rgb(c.color), fl = this.flat(x, y);
  if (c.ring) this.addRing(new Ring("ground", x, y, 12, 34 * sz * ps, fl, null, null, 4 * ps * sz, 90, sz, 0, 0, this.bodyR(fig, ps)));
  this.puffs(x, y, c.dust * k * 0.6, 2.2, col, sz, 520, 0, 360, [0.02, 0.25], 6);
  this.addSrc(new Jet(x, y, 1.0 * ps * sz, 2.0 * ps, 8 * ps, fl));
};
Sim.prototype.knockEvents = function (fig, tr, m, fx, fy, ps, jump) {
  var c = this.cfg(fig, "slam"), b = !!m.bouncing, back;
  this.use(fig, c);
  if (b && !tr.bouncing) {
    tr.v0 = Math.hypot(m.bounce_vx, m.bounce_vy);
    if (c.enabled && c.launch && tr.v0 >= c.min_speed) {
      var s = escale(Math.pow(tr.v0 / 15, 2)) * c.size / 100, col = rgb(c.color), fl = this.flat(fx, fy);
      back = Math.atan2(-m.bounce_vy, -m.bounce_vx) * 180 / Math.PI;
      this.addRing(new Ring("ground", fx, fy, 14, 40 * s * ps, fl, null, null, 5 * ps * s, Math.atan2(m.bounce_vy, m.bounce_vx) * 180 / Math.PI, s, tr.v0 * this.ssc(fx, fy) / TICK_S, 0, this.bodyR(fig, ps)));
      this.puffs(fx, fy, c.dust * 0.5, 2.0, col, s, 700, 0, 360, [0.05, 0.5]);
      this.puffs(fx, fy, c.dust * 0.5, 4.0 * s, col, s, 800, back, 70, [0.1, 0.8]);
      this.debris(fx, fy, "rock", Math.floor(c.rocks * 0.4), s, rgb(c.rock_color), {az: back, spread: 90, elev: [35, 60], spd: [3, 7], size: [2, 4.5]});
    }
  } else if (b && c.enabled && c.skid && jump > 2.5 && this.t % 2 === 0) {
    back = Math.atan2(-m.bounce_vy, -m.bounce_vx) * 180 / Math.PI;
    this.puffs(fx, fy, 1, 1.2, rgb(c.color), c.size / 100 * Math.min(1.6, jump / 8), 600, back, 80, [0.05, 0.3]);
  } else if (!b && tr.bouncing) {
    if (c.enabled && c.crater && tr.v0 >= 2 * Math.max(1, c.min_speed))
      this.crater(fig, fx, fy, ps, escale(Math.pow(tr.v0 / 15, 2)) * c.size / 100, c);
  }
  tr.bouncing = b;
};
Sim.prototype.crater = function (fig, x, y, ps, s, c) {
  var col = rgb(c.color), fl = this.flat(x, y), R = 44 * s * ps, n = Math.floor(c.dust);
  this.addRing(new Ring("ground", x, y, 22, R * 1.4, fl, null, null, 7 * ps * s, 90, s, 0, 0, this.bodyR(fig, ps)));
  this.addRing(new Ring("crater", x, y, 70, R * 0.8, fl, null, rgb(c.rock_color), 3 * ps));
  for (var i = 0; i < n; i++) {
    var a = 2 * Math.PI * i / Math.max(1, n) + Math.random() * 0.3;
    this.puff(x + Math.cos(a) * R * 0.7, y + Math.sin(a) * R * 0.7 * fl, 0, Math.cos(a) * 1.2 * ps, Math.sin(a) * 1.2 * ps * fl,
      (0.8 + 1.4 * Math.random()) * ps * s, (600 + 500 * Math.random()) / TICK_MS, 6.5 * s * (0.7 + 0.6 * Math.random()), col, null, 0.02);
  }
  this.debris(x, y, "rock", Math.floor(c.rocks), s, rgb(c.rock_color), {pi: true, spd: [3.5, 10], size: [2, 5]});
  this.addSrc(new Jet(x, y, 2.2 * ps * s, 2.6 * ps, 12 * ps, fl));
};
Sim.prototype.wall = function (fig, edge, x, y, sp) {
  var c = this.cfg(fig, "slam");
  this.use(fig, c);
  if (!(c.enabled && c.wall) || sp < c.min_speed * 0.6) return;
  var ps = this.ps(x, y), s = escale(Math.pow(sp / 15, 2)) * c.size / 100, col = rgb(c.color);
  var o = {l: [1, 0], r: [-1, 0], t: [0, 1], b: [0, -1]}[edge], ox = o[0], oy = o[1];
  var wx = edge === "l" ? 0 : (edge === "r" ? this.sw : x), wy = edge === "t" ? 0 : (edge === "b" ? this.sh : y);
  this.addRing(new Ring("wall", wx, wy, 26, 70 * s * ps, 1, edge, col, 5 * ps * s));
  for (var i = 0; i < Math.floor(c.dust); i++) {
    var along = (Math.random() - 0.5) * 2, vx, vy, vz, px, py;
    if (edge === "l" || edge === "r") { vx = ox * (0.6 + 1.8 * Math.random()) * ps * s; vy = 0; vz = along * 3.2 * ps * s; px = wx + ox * 4 * ps; py = wy; }
    else { vx = along * 3.2 * ps * s; vy = oy * (0.6 + 1.8 * Math.random()) * ps * s; vz = 0; px = wx; py = wy + oy * 4 * ps; }
    this.puff(px, py, 8 * ps * Math.random(), vx, vy, vz, (600 + 500 * Math.random()) / TICK_MS, 6 * s * (0.7 + 0.6 * Math.random()), col);
  }
  this.debris(wx + ox * 4 * ps, wy + oy * 4 * ps, "rock", Math.floor(c.rocks * 0.7), s, rgb(c.rock_color),
    {az: Math.atan2(oy, ox) * 180 / Math.PI, spread: 120, elev: [15, 55], spd: [3, 8], size: [2, 4.5]});
  this.addSrc(new Jet(wx, wy, 2.0 * ps * s, 2.8 * ps, 12 * ps, 1, (edge === "l" || edge === "r") ? "v" : "h", [ox, oy]));
};
Sim.prototype.dashEvents = function (fig, tr, fx, fy, ps, z, dx, dy, sp, hh) {
  var c = this.cfg(fig, "dash");
  this.use(fig, c);
  if (!c.enabled) { if (tr.wake) { tr.wake.live = false; tr.wake = null; } tr.fast = false; return; }
  var thr = c.speed, fast = sp >= thr && z < 2, col = rgb(c.color), sz = c.size / 100, vx = dx, vy = dy, R = Math.random;
  if (fast) {
    if (!tr.fast && tr.slow > 6 && c.start_burst) tr.burst = 4;
    tr.slow = 0;
    var k = c.inherit / 100, rate = c.rate * Math.min(3, sp / thr) * (tr.burst > 0 ? 3 : 1);
    tr.acc += rate * TICK_S;
    while (tr.acc >= 1) {
      tr.acc -= 1;
      var spread = 1.2 * ps;
      this.puff(fx - vx * R() + (R() - 0.5) * 6 * ps, fy + (R() - 0.5) * 3 * ps, R() * 2 * ps,
        vx * k + (R() - 0.5) * spread, vy * k + (R() - 0.5) * spread * 0.5, (0.15 + 0.5 * R()) * ps * (tr.burst > 0 ? 1.5 : 1),
        c.life_ms / TICK_MS * (0.7 + 0.6 * R()), (tr.burst <= 0 ? 5 : 6.5) * sz * (0.7 + 0.6 * R()), col);
    }
    tr.gacc += c.grit * Math.min(3, sp / thr) * TICK_S;
    if (tr.gacc >= 1) {
      var n = Math.floor(tr.gacc); tr.gacc -= n;
      this.debris(fx, fy, "pebble", n, sz, col, {az: Math.atan2(-vy, -vx) * 180 / Math.PI, spread: 70, elev: [25, 55], spd: [2, 5], size: [1, 2.2]});
    }
    if (tr.burst > 0) tr.burst--;
    if (c.wake) {
      if (!tr.wake || !tr.wake.live || this.src.indexOf(tr.wake) < 0) tr.wake = this.addSrc(new Wake(fx, fy, hh * 1.2));
      var w = tr.wake;
      w.x = fx; w.y = fy; w.vx = vx; w.vy = vy; w.d = Math.max(6, hh * 1.2);
      w.k = Math.min(0.6 * c.wake_pct / 100, w.k + 0.15);
      if (c.curls) {
        var spt = Math.hypot(vx, vy), D = Math.max(6, hh * 1.6);
        tr.shed += 0.2 * spt / D;
        if (tr.shed >= 1) {
          tr.shed -= 1; tr.sign = -tr.sign;
          var nx = vx / Math.max(0.01, spt), ny = vy / Math.max(0.01, spt), px = -ny, py = nx;
          this.addSrc(new Curl(fx - nx * D * 0.8 + px * tr.sign * D * 0.3, fy - D * 0.3 - ny * D * 0.8 + py * tr.sign * D * 0.3,
            tr.sign * 0.9 * spt * w.k, D * 0.35));
        }
      }
    }
  } else {
    tr.slow++; tr.burst = 0;
    if (tr.wake) { tr.wake.live = false; tr.wake = null; }
  }
  tr.fast = fast;
};
// The fighter slowed below Mach 1 (or blinked): its spring stops growing and dissolves from the oldest point.
// Coil radius multiplier for a speed: x1 at min_speed, 1 + radius_speed_pct / 100 at max_speed.
function speedRadius(sp, v) {
  var lo = sp.min_speed, hi = Math.max(sp.min_speed, sp.max_speed);
  return 1 + (sp.radius_speed_pct || 0) / 100 * (v > 0 ? Math.max(0, Math.min(1, (v - lo) / Math.max(1, hi - lo))) : 0);
}
// Spiral trail (laser/worldfx.py Trail / trail_ribbons): a spring built in real time on the fighter's path.
// Point record: [x, y, vx, vy, age, speed 0..1, phase, radius factor, laid spacing px].
var TRAIL_MAX_PTS = 700, TRAIL_STEP_PX = 10, COIL_BACK_ALPHA = 0.55, TRAIL_DRAG = 0.9, TRAIL_TURN = 0.4, TRAIL_CARRY = 0.35;
function trailAdd(t, x, y, v) {
  var sp = t.sp, lo = sp.min_speed, hi = Math.max(sp.min_speed + 1, sp.max_speed);
  var ft = v > 0 ? Math.max(0, Math.min(1, (v - lo) / (hi - lo))) : 0.5;
  t.f = t.f == null ? ft : t.f + (ft - t.f) * 0.4;
  var tgt = speedRadius(sp, v);
  t.rf = t.rf == null ? tgt : t.rf + (tgt - t.rf) * 0.4;
  if (t.lx == null) { t.lx = x; t.ly = y; t.pts.push([x, y, 0, 0, 0, t.f, t.phase, t.rf, 0]); return; }
  var dx = x - t.lx, dy = y - t.ly, ds = Math.hypot(dx, dy);
  if (ds < 0.5) return;
  var f = t.f, last = t.pts.length ? t.pts[t.pts.length - 1] : null, fa = last ? last[5] : f, ra = last ? last[7] : t.rf;
  var pitch = Math.max(4, Math.max(lo, Math.min(hi, v > 0 ? v : (lo + hi) / 2)) / Math.max(0.1, sp.spin_hz)) * (1 + 2 * f * f);
  var hand = sp.hand === "right" ? 1 : -1, carry = Math.min(0.9, TRAIL_CARRY * Math.max(0, sp.drift_pct == null ? 100 : +sp.drift_pct) / 100);
  var n = Math.max(1, Math.min(30, Math.ceil(ds / TRAIL_STEP_PX))), cx = dx * carry, cy = dy * carry;
  var px = t.cv ? t.cv[0] : cx, py = t.cv ? t.cv[1] : cy;
  cx = px + (cx - px) * TRAIL_TURN; cy = py + (cy - py) * TRAIL_TURN;   // momentum swings round over a few ticks
  for (var k = 1; k <= n; k++) {
    var a = k / n;
    t.phase += 2 * Math.PI * (ds / n) / pitch * hand;
    t.pts.push([t.lx + dx * a, t.ly + dy * a, px + (cx - px) * a, py + (cy - py) * a, 1 - a, fa + (f - fa) * a, t.phase, ra + (t.rf - ra) * a, ds / n]);
  }
  t.cv = [cx, cy];
  if (t.pts.length > TRAIL_MAX_PTS) t.pts.splice(0, t.pts.length - TRAIL_MAX_PTS);
  t.lx = x; t.ly = y;
}
function driftAt(age) { var a = Math.max(0, age - 1); return (1 - Math.pow(TRAIL_DRAG, a)) / (1 - TRAIL_DRAG); }
function trailRibbons(t, r0, baseW) {
  var pts = t.pts, n = pts.length, sp = t.sp, b = sp.tw, life = t.life, i;
  if (n < 2) return [];
  var fadeT = sp.out_ms > 0 ? Math.max(1, Math.min(life, sp.out_ms / TICK_MS)) : life * 0.5, inT = sp.in_ms > 0 ? sp.in_ms / TICK_MS : 0;
  var expand = Math.max(0, sp.expand_pct == null ? 600 : +sp.expand_pct) / 100;
  var streak = Math.max(0, Math.min(1, (sp.streak_pct == null ? 90 : +sp.streak_pct) / 100));
  var thin = Math.max(0, Math.min(1, (sp.thin_pct == null ? 30 : +sp.thin_pct) / 100));
  // (across, along) coil radius at life u: pushed OUT of its centre - across the travel it balloons, along it hardly widens
  function amps(q, u) { var a0 = r0 * q[7] * (1 - streak * Math.pow(q[5], 1.5)) * b, g = 1 - Math.pow(1 - u, 3); return [a0 * (1 + expand * g), a0 * 1.1 * (1 + 0.04 * expand * g)]; }
  function sweep(q, qp, u) { var dph = Math.abs(q[6] - qp[6]), th = 0.5 * (q[6] + qp[6]), a = amps(q, u); return dph * Math.hypot(a[1] * Math.sin(th), a[0] * Math.cos(th)); }
  // smoothness: fill in pieces between far-apart points (every field blended) so no drawn piece is longer than ~6 px
  var segN = Math.max(6, sp.segments || 24), fine = [pts[0]];
  for (i = 1; i < n; i++) {
    var qa = pts[i - 1], qb = pts[i], ub = Math.max(0, Math.min(1, qb[4] / life));
    var reach = r0 * qb[7] * (1 + expand * (1 - Math.pow(1 - ub, 3))) * b, dph = Math.abs(qb[6] - qa[6]);
    var kk = Math.max(1, Math.min(16, Math.ceil(Math.max(dph * reach / 6, dph / (2 * Math.PI) * segN))));
    for (var jj = 1; jj <= kk; jj++) {
      var aa = jj / kk, qq = [];
      for (var m = 0; m < 8; m++) qq.push(qa[m] + (qb[m] - qa[m]) * aa);
      qq.push(qb[8] / kk); fine.push(qq);
    }
  }
  pts = fine; n = pts.length;
  var base = pts.map(function (q) { var dr = driftAt(q[4]); return [q[0] + q[2] * dr, q[1] + q[3] * dr]; });
  var seg = []; for (i = 0; i < n; i++) seg.push(1);
  for (i = 1; i < n; i++) {
    var q = pts[i], qp = pts[i - 1];
    if (q[8] <= 1e-6) continue;
    var uq = Math.max(0, Math.min(1, q[4] / life));
    var now = Math.hypot(Math.hypot(base[i][0] - base[i - 1][0], base[i][1] - base[i - 1][1]), sweep(q, qp, uq));
    seg[i] = now / Math.max(1e-6, Math.hypot(q[8], sweep(q, qp, 0)));
  }
  seg[0] = seg[1];
  var out = [];
  for (i = 0; i < n; i++) {
    var p = pts[i], pa = base[Math.max(0, i - 1)], pc = base[Math.min(n - 1, i + 1)], tx = pc[0] - pa[0], ty = pc[1] - pa[1], ln = Math.hypot(tx, ty);
    if (ln < 1e-6) { tx = out.length ? out[out.length - 1][4] : 1; ty = out.length ? out[out.length - 1][5] : 0; } else { tx /= ln; ty /= ln; }
    var age = p[4], f = p[5], ph = p[6], u = Math.max(0, Math.min(1, age / life));
    var ac2 = amps(p, u), ramp = 0.35 + 0.65 * Math.min(1, age / 3), amp = ac2[0] * ramp, cs = Math.cos(ph), al = ac2[1] * ramp * cs, ac = amp * Math.sin(ph);
    var x = base[i][0] + tx * al - ty * ac, y = base[i][1] + ty * al + tx * ac;
    var st = (seg[Math.max(0, i - 1)] + seg[i] + seg[Math.min(n - 1, i + 1)]) / 3, sf = Math.max(0.2, Math.min(1.6, 1 / Math.sqrt(Math.max(1e-3, st))));
    var wear = Math.pow(u, 1.2) * (1 + 0.5 * f), w = baseW * (1 - (1 - thin) * f) * Math.max(0, sf - wear);
    var fo = age <= life - fadeT ? 1 : Math.max(0, (life - age) / fadeT), fi = inT <= 0 ? 1 : Math.min(1, age / inT);
    var back = b >= 0.5 && amp > 0.5 && cs < 0, depth = b >= 0.5 ? 1 - (1 - COIL_BACK_ALPHA) * Math.max(0, Math.min(1, 0.5 - cs)) : 1;
    out.push([x, y, w, fo * fi * depth, tx, ty, back]);
  }
  // worn through (width 0) = a gap that tapers to a point; otherwise short runs of one layer
  var ribbons = [], run = [], rb = null, prev = null;
  out.forEach(function (o) {
    var x = o[0], y = o[1], w = o[2], al = o[3], bk = o[6];
    if (w <= 0.15) {
      if (run.length) { run.push([x, y, 0, al]); if (run.length >= 2) ribbons.push([run, rb]); }
      run = []; rb = null; prev = [x, y, 0, al, bk]; return;
    }
    if (!run.length && prev && prev[2] === 0) { run = [prev.slice(0, 4)]; rb = bk; }
    prev = [x, y, w, al, bk];
    if (run.length && (bk !== rb || run.length >= 6)) { run.push([x, y, w, al]); if (run.length >= 2) ribbons.push([run, rb]); run = []; }
    if (!run.length) rb = bk;
    run.push([x, y, w, al]);
  });
  if (run.length >= 2) ribbons.push([run, rb]);
  return ribbons;
}
function ribbonPolygon(pts) {
  var n = pts.length, left = [], right = [];
  for (var i = 0; i < n; i++) {
    var a = pts[Math.max(0, i - 1)], c = pts[Math.min(n - 1, i + 1)], tx = c[0] - a[0], ty = c[1] - a[1], ln = Math.hypot(tx, ty) || 1;
    var nx = -ty / ln * pts[i][2] * 0.5, ny = tx / ln * pts[i][2] * 0.5;
    left.push([pts[i][0] + nx, pts[i][1] + ny]); right.push([pts[i][0] - nx, pts[i][1] - ny]);
  }
  return left.concat(right.reverse());
}
Sim.prototype.endTrail = function (tr) { if (tr.trail) { tr.trail.live = false; tr.trail = null; } };
Sim.prototype.sonicEvents = function (fig, tr, m, fx, fy, ps, sp, hh) {
  var c = this.cfg(fig, "sonic"), prev = tr.mach;
  this.use(fig, c);
  if (!c.enabled || ((m.bouncing || m.bounce_ending) && !c.knockback)) { tr.mach = 0; this.endTrail(tr); return; }
  var M = sp / Math.max(1, c.mach); tr.mach = M;
  // Live spiral trail: ONE spring follows the fighter (not a separate ring per boom), on the Spiral's own speed range
  // (not Mach): starts at Min speed, only ends after 8 ticks below 0.75 x Min speed; above Max speed the coils stay at the max look.
  var spl = this.ringSplit(fig, c), trailed = false;
  var trailOk = !!(spl && spl.tw > 0 && spl.trail !== false), tlo0 = spl ? spl.min_speed : 0;
  var running = trailOk && (sp >= tlo0 || (tr.trail && sp >= 0.75 * tlo0));
  if (running) {
    var tl = tr.trail;
    if (tl && tl.lx != null && Math.hypot(fig.x - tl.lx, fig.y - tl.ly) > 40 * (1 + (tr.tgap || 0))) { this.endTrail(tr); tl = null; }
    tr.tgap = 0;
    if (!tl) { tl = tr.trail = {pts: [], live: true, lx: null, ly: null, phase: 0, f: null, rf: null, cv: null}; this.trails.push(tl); tl.body = this.bodyR(fig, ps); }
    tl.sp = spl; tl.ps = ps; tl.col = rgb(c.color); tl.life = Math.max(2, 18 * spl.life_pct / 100);
    trailAdd(tl, fig.x, fig.y, sp);
    tr.boom_t = 0; trailed = true;
  } else if (tr.trail && trailOk) {
    tr.tgap = (tr.tgap || 0) + 1;       // slow for a moment: hold the trail (no new points)
    if (tr.tgap > 8) this.endTrail(tr); else trailed = true;
  } else this.endTrail(tr);
  if (M >= 1 && c.boom && !trailed) {
    // First boom on crossing Mach 1; then boom_hz more per second while supersonic (0 = once per crossing).
    var hz = +c.boom_hz || 0, fire = false;
    if (prev < 1) { fire = true; tr.boom_t = 0; }
    else if (hz > 0) { tr.boom_t = (tr.boom_t || 0) + TICK_S; if (tr.boom_t >= 1 / hz) { fire = true; tr.boom_t -= 1 / hz; } }
    if (fire) this.addRing(new Ring("boom", fig.x, fig.y, 18, 46 * ps, 1, null, rgb(c.color), 5 * ps, Math.atan2(tr.ny, tr.nx) * 180 / Math.PI, M, sp, 0, this.bodyR(fig, ps)));
  }
  if (M >= 1 && c.sweep) {
    tr.sweep++;
    if (tr.sweep % 4 === 0) {
      var back = hh * Math.sqrt(Math.max(0, M * M - 1)), bx = fx - tr.nx * back, by = fy - tr.ny * back;
      this.addSrc(new Blast(bx, by, 0.7, ps, 40, 0.5, true, this.flat(bx, by)));
      if (Math.random() < 0.5) this.puffs(bx, by, 2, 1.0, rgb(this.world.dash.color), 0.8, 600, 0, 360, [0.05, 0.3]);
    }
  } else tr.sweep = 0;
};
// A clash at (x, y): angle (degrees) = the hit axis, kb = the stronger knockback,
// owners = preview fighters (their feet give the floor).
Sim.prototype.clash = function (x, y, angle, kb, owners) {
  var own = (owners || []).filter(Boolean), c = this.cfg(own[0], "clash");
  this.use(own[0], c);
  if (!(c.enabled && this.world.ground.enabled)) return;
  var ps = this.ps(x, y), s = escale(Math.max(0.05, kb / 100)) * c.size / 100, col = rgb(c.color), perp = angle + 90, self = this;
  var gy = null;
  own.forEach(function (o) { var g0 = self.foot(o, self.ps(o.x, o.y))[1]; gy = gy == null ? g0 : Math.max(gy, g0); });
  var z0 = gy != null ? Math.max(0, gy - y) : 0, floor = gy != null ? gy : y;
  if (c.sheet) for (var i = 0; i < Math.floor(c.dust); i++) {
    var sgn = i % 2 === 0 ? 1 : -1, a = (perp + (Math.random() - 0.5) * 30) * Math.PI / 180, sp = (2 + 3.5 * Math.random()) * ps * s;
    this.puff(x, floor, z0, Math.cos(a) * sp * sgn, 0, -Math.sin(a) * sp * sgn, (450 + 450 * Math.random()) / TICK_MS, 5 * s * (0.7 + 0.6 * Math.random()), col, null, 0);
  }
  this.sparks2d(x, y, perp, Math.floor(c.sparks), s, rgb(c.spark_color), floor);
  this.addRing(new Ring("boom", x, y, 12, 36 * s * ps, 1, null, [255, 255, 255], 4 * ps, perp - 90, s, 0, 0, this.bodyR(own[0], ps)));
  if (c.ground_jet && gy != null && gy > y + 2) {
    var delay = Math.max(1, Math.floor((gy - y) / Math.max(1, 4.5 * ps * s)));
    this.later.push([this.t + delay, this.clashFloor, [x, gy, s, c, this.cur, this.curFx]]);
  }
};
Sim.prototype.clashFloor = function (x, y, s, c, cur, curFx) {
  if (cur) this.cur = cur;
  if (curFx) this.curFx = curFx;
  var ps = this.ps(x, y), fl = this.flat(x, y);
  this.addRing(new Ring("ground", x, y, 18, 50 * s * ps, fl, null, null, 5 * ps * s, 90, s));
  this.addSrc(new Jet(x, y, 2.0 * ps * s, 3.0 * ps, 10 * ps, fl));
  this.puffs(x, y, Math.floor(c.dust * 0.8), 3.2 * s, rgb(c.color), s, 700, 0, 360, [0.02, 0.3]);
};
Sim.prototype.sparks2d = function (x, y, az, n, s, col, floor) {
  if (n <= 0) return;
  if (this.bursts.length >= 40) this.bursts.shift();
  var ps = this.ps(x, y), pieces = [];
  for (var i = 0; i < n; i++) {
    var sgn = i % 2 === 0 ? 1 : -1, a = (az + (Math.random() - 0.5) * 50) * Math.PI / 180, sp = (5 + 6 * Math.random()) * Math.sqrt(s) * ps;
    pieces.push([1, 0, Math.cos(a) * sp * sgn, -Math.sin(a) * sp * sgn, 1, 0, 0]);
  }
  var b = new Burst(x, y, ps, this.ssc(x, y), "spark", pieces, 0.22 * ps, 0.974, -1, 20, col);
  b.floor = floor == null ? null : floor;    // they die on this screen y
  this.bursts.push(b);
};
// A technique shot detonating at (x, y) with this damage; fig = its owner.
// track (optional): {ax: heading deg, dist: px flown, spd: px/s} - the spiral's axis, length and pitch.
Sim.prototype.blast = function (x, y, dmg, fig, track) {
  var c = this.cfg(fig, "blast");
  this.use(fig, c);
  if (!c.enabled || dmg < c.min_damage) return;
  var ps = this.ps(x, y), s = escale(dmg / 10) * c.size / 100, fl = this.flat(x, y);
  this.addSrc(new Blast(x, y, s, ps, c.reach, c.strength / 100, c.suck_back, fl));
  if (c.ring) this.addRing(new Ring("ground", x, y, 20, c.reach * 0.6 * s * ps, fl, null, null, 4 * ps * s,
    track ? track.ax : 0, s, track ? track.spd : 0, track ? track.dist : 0, 0));
  this.puffs(x, y, Math.floor(c.dust * Math.min(2, s)), 1.5, rgb(c.color), s, 900, 0, 360, [0.05, 0.6]);
};
Sim.prototype.move = function () {
  var g = this.world.ground, self = this;
  this.src.forEach(function (s) { s.age += 1; });
  this.src = this.src.filter(function (s) { return s.age < s.life && !(s instanceof Wake && !s.live && s.k < 0.02); });
  this.src.forEach(function (s) { if (s instanceof Wake && !s.live) s.k *= 0.85; });
  this.bursts.forEach(function (b) { b.age += b.ss; });
  this.bursts = this.bursts.filter(function (b) { return b.age < b.life; });
  this.rings.forEach(function (r) { r.age += 1; });
  this.rings = this.rings.filter(function (r) { return r.age < r.life; });
  // Spiral trails: every coil ages on its own and is gone at the end of its life.
  this.trails.forEach(function (t) { t.pts.forEach(function (q) { q[4] += 1; }); t.pts = t.pts.filter(function (q) { return q[4] < t.life; }); });
  this.trails = this.trails.filter(function (t) { return t.pts.length || t.live; });
  var cap = Math.floor(g.max_dust);
  if (this.dust.length > cap) this.dust.splice(0, this.dust.length - cap);
  var src = this.src.map(function (s) { return [s].concat(s.bbox()); }), live = [];
  for (var i = 0; i < this.dust.length; i++) {
    var d = this.dust[i], x = d[0], y = d[1], z = d[2], ss = this.ssc(x, y), ux = 0, uy = 0, uz = 0;
    for (var j = 0; j < src.length; j++) {
      var b = src[j];
      if (x < b[1] || x > b[3] || y < b[2] || y > b[4]) continue;
      var a = b[0].air(x, y, z);
      if (a) { ux += a[0]; uy += a[1]; uz += a[2]; }
    }
    var k = Math.exp(-ss / d[9]);
    d[3] = ux + (d[3] - ux) * k; d[4] = uy + (d[4] - uy) * k; d[5] = uz + (d[5] - uz) * k - d[11] * ss;
    d[0] = x + d[3] * ss; d[1] = y + d[4] * ss; z = z + d[5] * ss;
    if (z < 0) { z = 0; if (d[5] < 0) d[5] = 0; d[3] *= d[15]; d[4] *= d[15]; }
    d[2] = z; d[6] += ss;
    if (d[6] < d[7] && d[0] > -50 && d[0] < this.sw + 50 && d[1] > -50 && d[1] < this.sh + 50) live.push(d);
  }
  this.dust = live;
};

// ---------------------------------------------------------------- paint
Sim.prototype.paintGround = function (g) {
  var ink = this.world.ground.ink, self = this;
  this.rings.forEach(function (r) { if (r.kind !== "boom") self.ring(g, r, ink); });
  this.bursts.forEach(function (b) { if (b.kind !== "spark") self.rocks(g, b, ink); });
  this.paintDust(g, ink);
};
// The far (dark) side of every spiral: drawn first, under the ground layer and every fighter.
Sim.prototype.paintBack = function (g) {
  var self = this, ink = this.world.ground.ink;
  this.rings.forEach(function (r) { if (r.sp && (r.kind === "ground" || r.kind === "boom") && r.sp.tw >= 0.5) self.ringSplitDraw(g, r, ink, r.age / r.life, "back"); });
  this.trails.forEach(function (t) { if (t.sp && t.sp.tw >= 0.5) self.trailDraw(g, t, ink, "back"); });
};
Sim.prototype.paintAir = function (g) {
  var self = this, ink = this.world.ground.ink;
  this.rings.forEach(function (r) { if (r.kind === "boom") self.ring(g, r, ink); });
  this.trails.forEach(function (t) { self.trailDraw(g, t, ink); });
  g.save(); g.globalCompositeOperation = "lighter";
  this.bursts.forEach(function (b) { if (b.kind === "spark") self.sparks(g, b); });
  g.restore();
  this.tracks.forEach(function (tr) { if (tr.mach >= 0.9) self.sonic(g, tr); });
};
Sim.prototype.ringSplitDraw = function (g, r, ink, u, layer) {
  var sp = r.sp, n = sp.n, b = sp.tw, grow = 1 - Math.pow(1 - u, 3), w = Math.max(1, r.w * (1 - u) * sp.thread_px / 5);
  var rad = r.r * (0.25 + 0.75 * grow), fl = r.kind === "ground" ? r.flat : 1, TAU = 2 * Math.PI;
  var inT = sp.in_ms <= 0 ? 1 : Math.min(1, r.age * TICK_MS / sp.in_ms), outT = 0, a0 = 1 - u * u;
  if (sp.out_ms > 0) {
    var ot = Math.max(1e-6, Math.min(r.life, sp.out_ms / TICK_MS));
    outT = Math.max(0, Math.min(1, (r.age - (r.life - ot)) / ot)); a0 = 1;
  }
  var ar = r.ax * Math.PI / 180, ux = Math.cos(ar), uy = Math.sin(ar), nx = -uy, ny = ux;
  var length, lo = sp.min_speed, hi = Math.max(sp.min_speed, sp.max_speed);
  if (r.dist) length = r.dist * sp.length_pct / 100 * (0.35 + 0.65 * grow);
  else {
    length = r.r * 5.0 * sp.length_pct / 100 * (0.35 + 0.65 * grow);
    length *= Math.max(0.3, Math.min(3, 1 + sp.speed_len / 100 * (r.k - 1)));
  }
  // Rotation frequency + speed = pitch (px per coil = speed / frequency), speed held inside min..max.
  var v = r.spd || (lo + hi) * 0.5, pitch = Math.max(4, Math.max(lo, Math.min(hi, v)) / Math.max(0.1, sp.spin_hz));
  var turns = Math.max(0.05, length / pitch);
  var r0 = (sp.body_scale && r.body > 0) ? r.body * sp.body_pct / 100 * (0.4 + 0.6 * grow) : rad * 0.55 * sp.radius_pct / 100;
  if (r.spd) r0 *= speedRadius(sp, r.spd);
  r0 *= 1 + 0.5 * u;   // coils open wider with age
  var rot = sp.rotation * Math.PI / 180, spin = sp.hand === "right" ? 1 : -1;
  var th0 = rot + spin * TAU * 0.6 * (2 * u - u * u);   // rigid turn about the axis, slowing to 0 at end of life
  var gapf = n >= 2 ? sp.gap / 100 : 0, span = TAU / n, parts = [], i, j;
  // Smoothness: "segments" line pieces per coil.
  var m = b > 0 ? Math.max(8, Math.min(700, Math.ceil(Math.max(6, sp.segments || 24) * Math.max(1, turns) / n))) : Math.max(8, Math.floor(96 / n));
  for (i = 0; i < n; i++) {
    var pts = [];
    for (j = 0; j <= m; j++) {
      var t = j / m, uu = gapf / 2 + t * (1 - gapf), s = (i + uu) / n, phi = (i + uu - 0.5) * span + rot;
      var x = r.x + rad * Math.cos(phi), y = r.y + rad * fl * Math.sin(phi), af = 1, bk = false;
      if (b > 0) {
        var th = TAU * turns * s * spin + th0, rs = r0 * Math.max(0.05, 1 + sp.taper / 100 * (2 * s - 1));
        var off = sp.reach === "behind" ? -(1 - s) * length : sp.reach === "ahead" ? s * length : (s - 0.5) * length;
        var sn = Math.sin(th), hx = r.x + ux * off + nx * rs * sn, hy = r.y + uy * off + ny * rs * sn;
        x += (hx - x) * b; y += (hy - y) * b;
        af = (1 - b) + b * Math.max(0, Math.min(1, 0.5 + 2 * Math.cos(th)));
        bk = b >= 0.5 && Math.cos(th) < 0;      // the far side of the coil
      }
      pts.push([x, y, af, t, bk]);
    }
    parts.push(pts);
  }
  var mid = parts.map(function (pts) { var q = 0; pts.forEach(function (v) { q += v[0]; }); return q / pts.length; });
  function ranks(d) {
    var key = [], k;
    for (k = 0; k < n; k++) key.push(d === "left_to_right" ? mid[k] : d === "right_to_left" ? -mid[k] : d === "reverse_creation" ? -k : k);
    var order = key.map(function (v, k2) { return k2; }).sort(function (a, c) { return key[a] - key[c]; }), rk = {};
    order.forEach(function (v, k2) { rk[v] = k2; });
    return rk;
  }
  function wipe(mode, d, prog, rk, pts, idx) {
    if (mode === "whole") return null;
    var pr = mode === "parts_together" ? prog : Math.max(0, Math.min(1, prog * n - rk[idx])), cs;
    if (d === "left_to_right" || d === "right_to_left") {
      var lo = 1e9, hi = -1e9;
      pts.forEach(function (q) { lo = Math.min(lo, q[0]); hi = Math.max(hi, q[0]); });
      cs = pts.map(function (q) { var c = (q[0] - lo) / (hi - lo + 1e-6); return d === "right_to_left" ? 1 - c : c; });
    } else cs = pts.map(function (q) { return d === "reverse_creation" ? 1 - q[3] : q[3]; });
    return cs.map(function (c) { return Math.max(0, Math.min(1, (pr * 1.1 - c) * 12)); });
  }
  var rkIn = ranks(sp.in_dir), rkOut = ranks(sp.out_dir), whole = 1;
  if (sp.in_mode === "whole" && sp.in_ms > 0) whole *= inT;
  if (sp.out_mode === "whole" && sp.out_ms > 0) whole *= 1 - outT;
  var segs = [];
  parts.forEach(function (pts, idx) {
    var vin = sp.in_ms > 0 ? wipe(sp.in_mode, sp.in_dir, inT, rkIn, pts, idx) : null;
    var vout = sp.out_ms > 0 ? wipe(sp.out_mode, sp.out_dir, outT, rkOut, pts, idx) : null, f = [], q;
    for (q = 0; q < pts.length; q++) {
      var v = pts[q][2] * whole;
      if (vin) v *= vin[q];
      if (vout) v *= 1 - vout[q];
      f.push(v);
    }
    for (q = 0; q < pts.length - 1; q++) {
      if ((pts[q][4] && pts[q + 1][4]) !== (layer === "back")) continue;
      var a = a0 * Math.min(f[q], f[q + 1]);
      if (a > 0.01) segs.push([pts[q][0], pts[q][1], pts[q + 1][0], pts[q + 1][1], a]);
    }
  });
  g.save(); g.lineCap = "butt";
  [[w + 3, ink], [w, css(r.col)]].forEach(function (pass) {
    g.lineWidth = pass[0]; g.strokeStyle = pass[1];
    segs.forEach(function (sg) {
      g.globalAlpha = sg[4]; g.beginPath(); g.moveTo(sg[0], sg[1]); g.lineTo(sg[2], sg[3]); g.stroke();
    });
  });
  g.restore();
};
// The live spiral trail (trailRibbons): white air, no ink outline, brush ribbons whose width follows speed,
// stretch and friction wear.  layer "back" = only the far side of each coil.
Sim.prototype.trailDraw = function (g, t, ink, layer) {
  if (!t.pts || t.pts.length < 2 || !t.sp) return;
  var sp = t.sp, back = layer === "back";
  var r0 = (sp.body_scale && t.body > 0) ? t.body * sp.body_pct / 100 : 46 * t.ps * 0.55 * sp.radius_pct / 100;
  var baseW = Math.max(1, sp.thread_px * t.ps);
  g.save();
  trailRibbons(t, r0, baseW).forEach(function (rib) {
    var pts = rib[0];
    if (rib[1] !== back) return;
    var a0 = pts[0][3], a1 = pts[pts.length - 1][3];
    if (a0 <= 0.01 && a1 <= 0.01) return;
    var gr = g.createLinearGradient(pts[0][0], pts[0][1], pts[pts.length - 1][0], pts[pts.length - 1][1]);
    gr.addColorStop(0, css(t.col, a0)); gr.addColorStop(1, css(t.col, a1));
    var poly = ribbonPolygon(pts);
    g.fillStyle = gr; g.beginPath(); g.moveTo(poly[0][0], poly[0][1]);
    for (var j = 1; j < poly.length; j++) g.lineTo(poly[j][0], poly[j][1]);
    g.closePath(); g.fill();
  });
  g.restore();
};
Sim.prototype.ring = function (g, r, ink) {
  if (r.sp && (r.kind === "ground" || r.kind === "boom")) { this.ringSplitDraw(g, r, ink, r.age / r.life); return; }
  var u = r.age / r.life, grow = 1 - Math.pow(1 - u, 3), w = Math.max(1, r.w * (1 - u)), rx, ry, a;
  g.save();
  if (r.kind === "crater") {
    a = 150 * (1 - Math.floor(u * 4) / 4) / 255;
    g.lineWidth = Math.max(1, r.w); g.strokeStyle = css(r.col, a);
    g.beginPath(); g.ellipse(r.x, r.y, r.r, r.r * r.flat, 0, 0, 2 * Math.PI); g.stroke();
    g.lineWidth = Math.max(1, r.w * 2.5); g.strokeStyle = "rgba(0,0,0," + (a / 2) + ")";
    g.beginPath(); g.ellipse(r.x, r.y, r.r * 0.6, r.r * 0.6 * r.flat, 0, 0, 2 * Math.PI); g.stroke();
    g.restore(); return;
  }
  var rad = r.r * (0.25 + 0.75 * grow);
  if (r.kind === "wall") {
    if (r.edge === "l" || r.edge === "r") { rx = rad * 0.16; ry = rad; } else { rx = rad; ry = rad * 0.16; }
    a = 230 * (1 - u) / 255;
    g.beginPath(); g.ellipse(r.x, r.y, rx, ry, 0, 0, 2 * Math.PI);
    g.fillStyle = css(r.col, a); g.fill();
    g.lineWidth = w + 3; g.strokeStyle = ink; g.stroke();
    g.lineWidth = w; g.strokeStyle = "rgba(255,255,255," + a + ")"; g.stroke();
    g.restore(); return;
  }
  var fl = r.kind === "ground" ? r.flat : 1;
  a = 1 - u * u;
  g.beginPath(); g.ellipse(r.x, r.y, rad, rad * fl, 0, 0, 2 * Math.PI);
  g.globalAlpha = a; g.lineWidth = w + 3; g.strokeStyle = ink; g.stroke();
  g.lineWidth = w; g.strokeStyle = css(r.col); g.stroke();
  g.restore();
};
Sim.prototype.rocks = function (g, b, ink) {
  var fade = b.age < b.life * 0.75 ? 1 : Math.max(0, (b.life - b.age) / (b.life * 0.25));
  if (fade <= 0) return;
  var col = css(b.col), lit = css([Math.min(255, b.col[0] + 60), Math.min(255, b.col[1] + 60), Math.min(255, b.col[2] + 60)]);
  g.save(); g.globalAlpha = fade; g.lineWidth = 1.2; g.strokeStyle = ink;
  for (var i = 0; i < b.pieces.length; i++) {
    var pc = b.pieces[i], at = b.at(pc, b.age);
    if (!at) continue;
    var x = at[0], sy = at[1] - at[2], s = pc[4] * (b.kind === "rock" ? 1 : 0.7), rot = at[2] > 0 ? pc[6] + pc[5] * b.age : pc[6], pts = [];
    for (var k = 0; k < 4; k++) {
      var a = rot + k * 1.5708 + (k % 2 ? 0.25 : -0.1), rr = s * (k % 2 === 0 ? 1 : 0.8);
      pts.push([x + Math.cos(a) * rr, sy + Math.sin(a) * rr]);
    }
    g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (k = 1; k < 4; k++) g.lineTo(pts[k][0], pts[k][1]); g.closePath();
    g.fillStyle = col; g.fill(); g.stroke();
    g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); g.lineTo(pts[1][0], pts[1][1]); g.lineTo(x, sy); g.closePath();
    g.fillStyle = lit; g.fill();
  }
  g.restore();
};
Sim.prototype.sparks = function (g, b) {
  g.lineCap = "round";
  for (var i = 0; i < b.pieces.length; i++) {
    var pc = b.pieces[i], x0, y0, x1, y1;
    if (b.e < 0) {
      if (b.age > 20) continue;
      var h = pc[2], v = pc[3], k = b.k;
      var pos = function (tt) { var f = (1 - Math.pow(k, tt)) / (1 - k); return [b.x + h * f, b.y - (v * f - 0.5 * b.g * tt * tt)]; };
      var p1 = pos(b.age), p0 = pos(Math.max(0, b.age - 2)); x1 = p1[0]; y1 = p1[1]; x0 = p0[0]; y0 = p0[1];
      if (b.floor != null && y0 > b.floor) continue;   // it hit the floor
      if (b.floor != null && y1 > b.floor) y1 = b.floor;
    } else {
      var a1 = b.at(pc, b.age), a0 = b.at(pc, Math.max(0, b.age - 2));
      if (!a1 || !a0) continue;
      x1 = a1[0]; y1 = a1[1] - a1[2]; x0 = a0[0]; y0 = a0[1] - a0[2];
    }
    var w = Math.max(1, 1.5 * b.ps);
    g.strokeStyle = css(b.col, 0.55); g.lineWidth = w * 2.2; g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
    g.strokeStyle = "rgba(255,255,255,0.9)"; g.lineWidth = w * 0.7; g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
  }
};
Sim.prototype.sonic = function (g, tr) {
  var M = tr.mach, x = tr.head[0], y = tr.head[1], nx = tr.nx, ny = tr.ny, c = this.world.sonic;
  if (!nx && !ny) return;
  var ps = this.ps(x, y), tip = [x + nx * 14 * ps, y + ny * 14 * ps];
  g.save();
  if (M >= 0.9 && M < 1.25 && c.vapor) {
    var a = (60 + 90 * Math.random()) / 255;
    g.save(); g.translate(x - nx * 4 * ps, y - ny * 4 * ps); g.rotate(Math.atan2(ny, nx));
    g.beginPath(); g.ellipse(0, 0, 5 * ps, 16 * ps, 0, 0, 2 * Math.PI);
    g.fillStyle = "rgba(235,245,255," + a + ")"; g.fill(); g.restore();
  }
  if (M >= 1 && c.cone) {
    var mu = Math.asin(Math.min(1, 1 / M)), L = 90 * ps, back = Math.atan2(-ny, -nx), col = rgb(c.color);
    [-1, 1].forEach(function (sgn) {
      var an = back + sgn * mu, ex = tip[0] + Math.cos(an) * L, ey = tip[1] + Math.sin(an) * L;
      var ox = -Math.sin(an) * 2 * sgn, oy = Math.cos(an) * 2 * sgn;
      g.lineWidth = 3 * Math.max(1, ps * 0.6); g.strokeStyle = "rgba(0,0,0,0.6)";
      g.beginPath(); g.moveTo(tip[0], tip[1]); g.lineTo(ex, ey); g.stroke();
      g.lineWidth = 1.5 * Math.max(1, ps * 0.6); g.strokeStyle = css(col, 0.82);
      g.beginPath(); g.moveTo(tip[0] + ox, tip[1] + oy); g.lineTo(ex + ox, ey + oy); g.stroke();
    });
  }
  g.restore();
};
// ---------------------------------------------------------------- anime smoke
// (size factor, erosion 0..1, opacity) of a puff at this age under its
// style's Life settings, or null once it is gone (laser/worldfx.py smoke_look).
function smokeLook(pr, age, life) {
  var hold = Math.max(1, Math.floor(pr.hold));
  age = Math.floor(age / hold) * hold;
  var u = age / life;
  if (u >= 1) return null;
  var gm = pr.grow, ga = pr.grow_at, ero = 0, g;
  if (u < ga) g = 1 + (gm - 1) * (1 - Math.pow(1 - u / ga, 2));
  else {
    var v = (u - ga) / Math.max(1e-6, 1 - ga), n = Math.max(1, Math.floor(pr.steps));
    if (pr.shrink === "smooth") g = gm * (1 - v);
    else if (pr.shrink === "steps") g = gm * (1 - Math.floor(v * n) / n);
    else if (pr.shrink === "erode") { g = gm; ero = Math.floor(v * n + 1) / (n + 1); }
    else g = gm;
  }
  var a = pr.opacity / 100, f = pr.fade / 100;
  if (f > 0 && u > 1 - f) a *= Math.max(0, (1 - u) / f);
  return [g, ero, a];
}
var MERGED = {cel: 1, billow: 1, flat: 1, stepped: 1};
var LOBES = [[0, 0.18, 0.62], [-0.44, 0.12, 0.47], [0.44, 0.14, 0.5], [-0.22, -0.3, 0.46], [0.24, -0.32, 0.42]];
var BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
var SPRITES = new Map(), DITHER = {};
function lobes(st, r, seed) {
  if (st !== "billow") return [[0, 0, r]];
  var v = Math.floor(seed * 10) % 4, sx = v & 1 ? -1 : 1, k = v & 2 ? 1.08 : 1;
  return LOBES.map(function (l, i) { return [l[0] * r * sx, l[1] * r, l[2] * r * (i % 2 ? k : 1)]; });
}
function shade(c, k) { return c.map(function (v) { return Math.max(0, Math.min(255, Math.floor(v * k))); }); }
function lift(c, k) { return c.map(function (v) { return Math.floor(v + (255 - v) * k); }); }
function ditherPattern(g, level) {
  if (!DITHER[level]) {
    var cv = document.createElement("canvas"); cv.width = cv.height = 4;
    var x = cv.getContext("2d"); x.fillStyle = "#000";
    for (var i = 0; i < 4; i++) for (var j = 0; j < 4; j++) if (BAYER[j][i] < level * 4) x.fillRect(i, j, 1, 1);
    DITHER[level] = cv;
  }
  return g.createPattern(DITHER[level], "repeat");
}
// A cached puff sprite {cv, half}: outline = the ink silhouette grown by the
// outline width, else the shaded fill (laser/worldfx.py _sprite).
function sprite(st, r, col, pr, ero, seed, outline) {
  var ow = Math.round(pr.outline * 2) / 2, lvl = ero > 0 ? Math.min(3, Math.floor(ero * 4)) : 0;
  var vr = st === "billow" ? Math.floor(seed * 10) % 4 : 0, tones = st === "flat" ? 1 : Math.floor(pr.tones);
  var ldir = Math.round(pr.light_dir / 15) * 15;
  var key = outline ? ["o", st, r, pr.ink, ow, vr, lvl].join() :
    ["f", st, r, col.join("."), tones, Math.floor(pr.shadow), Math.floor(pr.light), ldir, vr, lvl, ow].join();
  var hit = SPRITES.get(key);
  if (hit) return hit;
  if (SPRITES.size > 1600) SPRITES.clear();
  var lob = lobes(st, r, seed), half = Math.floor(r * 1.35 + ow + 3), n = 2 * half;
  var cv = document.createElement("canvas"); cv.width = cv.height = n;
  var q = cv.getContext("2d"), c = half;
  function blobs(fn) { lob.forEach(function (l) { q.beginPath(); fn(l); q.fill(); }); }
  if (st === "ink") {
    var dark = shade(col, 1 - pr.shadow / 100), lite = lift(col, pr.light / 100);
    var gr = q.createRadialGradient(c, c, 0, c, c, r);
    gr.addColorStop(0, css(dark, 225 / 255)); gr.addColorStop(0.6, css(dark, 170 / 255));
    if (tones >= 2) gr.addColorStop(0.84, css(lite, 105 / 255));
    gr.addColorStop(1, css(lite, 0));
    q.fillStyle = gr; q.beginPath(); q.arc(c, c, r, 0, 2 * Math.PI); q.fill();
  } else if (outline) {
    q.fillStyle = pr.ink;
    blobs(function (l) { q.arc(c + l[0], c + l[1], l[2] + ow, 0, 2 * Math.PI); });
  } else {
    var a = ldir * Math.PI / 180, lx = Math.cos(a), ly = Math.sin(a);
    if (tones >= 2) {
      q.fillStyle = css(shade(col, 1 - pr.shadow / 100));
      blobs(function (l) { q.arc(c + l[0], c + l[1], l[2], 0, 2 * Math.PI); });
      q.fillStyle = css(col);
      blobs(function (l) { q.arc(c + l[0] + lx * l[2] * 0.14, c + l[1] + ly * l[2] * 0.14, l[2] * 0.86, 0, 2 * Math.PI); });
    } else {
      q.fillStyle = css(col);
      blobs(function (l) { q.arc(c + l[0], c + l[1], l[2], 0, 2 * Math.PI); });
    }
    if (tones >= 3 && pr.light > 0) {
      q.fillStyle = css(lift(col, pr.light / 100));
      blobs(function (l) { q.ellipse(c + l[0] + lx * l[2] * 0.4, c + l[1] + ly * l[2] * 0.4, l[2] * 0.36, l[2] * 0.3, 0, 0, 2 * Math.PI); });
    }
  }
  if (lvl > 0) { q.globalCompositeOperation = "destination-out"; q.fillStyle = ditherPattern(q, lvl); q.fillRect(0, 0, n, n); }
  hit = {cv: cv, half: half};
  SPRITES.set(key, hit);
  return hit;
}
function blit(g, sp, x, y, a) { g.globalAlpha = Math.max(0, Math.min(1, a)); g.drawImage(sp.cv, Math.floor(x - sp.half), Math.floor(y - sp.half)); }
function swirl(g, x, y, r, col, pr, a, seed, age) {
  var n = 12, turn = seed + age * 0.07, w = Math.max(1.5, r * 0.32), tones = Math.floor(pr.tones);
  function path(ox, oy) {
    g.beginPath();
    for (var i = 0; i < n; i++) {
      var f = i / (n - 1), ang = turn + f * 4.4, rr = r * (0.18 + 0.82 * f), px = x + ox + Math.cos(ang) * rr, py = y + oy + Math.sin(ang) * rr * 0.8;
      if (i) g.lineTo(px, py); else g.moveTo(px, py);
    }
  }
  g.globalAlpha = Math.max(0, Math.min(1, a)); g.lineCap = g.lineJoin = "round";
  if (pr.outline > 0) { path(0, 0); g.strokeStyle = pr.ink; g.lineWidth = w + 2 * pr.outline; g.stroke(); }
  path(0, 0); g.strokeStyle = css(tones >= 2 ? shade(col, 1 - pr.shadow / 100) : col); g.lineWidth = w; g.stroke();
  if (tones >= 2) {
    var al = pr.light_dir * Math.PI / 180;
    path(Math.cos(al) * w * 0.25, Math.sin(al) * w * 0.25);
    g.strokeStyle = css(tones >= 3 ? lift(col, pr.light / 100) : col); g.lineWidth = w * 0.45; g.stroke();
  }
}
function ringPuff(g, x, y, r, col, pr, a) {
  var t = Math.max(1, r * 0.3);
  g.globalAlpha = Math.max(0, Math.min(1, a));
  if (pr.outline > 0) { g.beginPath(); g.ellipse(x, y, r, r * 0.85, 0, 0, 2 * Math.PI); g.strokeStyle = pr.ink; g.lineWidth = t + 2 * pr.outline; g.stroke(); }
  g.beginPath(); g.ellipse(x, y, r, r * 0.85, 0, 0, 2 * Math.PI); g.strokeStyle = css(col); g.lineWidth = t; g.stroke();
  if (Math.floor(pr.tones) >= 2) {
    g.beginPath(); g.ellipse(x, y, r + t * 0.15, r * 0.85 + t * 0.15, 0, 0, 2 * Math.PI);
    g.strokeStyle = css(lift(col, pr.light / 100)); g.lineWidth = Math.max(1, t * 0.35); g.stroke();
  }
}
// Every dust puff in its own smoke style: outlined styles draw every ink
// outline first, then every fill, so overlapping puffs merge into one
// outlined cloud; ink wash, swirl and ring draw one by one on top.
Sim.prototype.paintDust = function (g, ink) {
  var merged = [], loose = [];
  for (var i = 0; i < this.dust.length; i++) {
    var d = this.dust[i], pr = d[13], look = smokeLook(pr, d[6], d[7]);
    if (!look) continue;
    var ps = this.ps(d[0], d[1]), r = d[8] * look[0] * ps * 0.5;
    if (r < 1) continue;
    var x = d[0], y = d[1] - d[2];
    if (pr.wobble > 0) { var ph = d[6] * pr.wobble_hz * 6.283 * TICK_S + d[14]; x += Math.sin(ph) * pr.wobble * ps; y += Math.cos(ph * 0.7) * pr.wobble * ps * 0.5; }
    var it = [x, y, Math.min(60, Math.round(r)), d[10], d[12], pr, look[1], look[2], d[14], d[6]];
    (MERGED[d[12]] ? merged : loose).push(it);
  }
  g.save();
  merged.forEach(function (it) { if (it[5].outline > 0) blit(g, sprite(it[4], it[2], it[3], it[5], it[6], it[8], true), it[0], it[1], it[7]); });
  merged.forEach(function (it) { blit(g, sprite(it[4], it[2], it[3], it[5], it[6], it[8], false), it[0], it[1], it[7]); });
  loose.forEach(function (it) {
    if (it[4] === "ink") blit(g, sprite("ink", it[2], it[3], it[5], it[6], it[8], false), it[0], it[1], it[7]);
    else if (it[4] === "swirl") swirl(g, it[0], it[1], it[2], it[3], it[5], it[7], it[8], it[9]);
    else ringPuff(g, it[0], it[1], it[2], it[3], it[5], it[7]);
  });
  g.restore();
};

window.WORLDFX = {
  FORMAT: WP_FORMAT, FILE: "world_physics.json", SECTIONS: WP_SECTIONS, DEFAULTS: WP_DEFAULTS, RANGES: WP_RANGES,
  FIELDS: WP_FIELDS, TITLES: WP_TITLES, TICK_MS: TICK_MS, ENUMS: WP_ENUMS,
  SMOKE_STYLES: WP_SMOKE_STYLES, STYLE_TITLES: WP_STYLE_TITLES,
  normalize: normalize, normalizeSection: normalizeSection, normalizeOverride: normalizeOverride,
  Sim: Sim, pscale: function (x, y, sw, sh) { return bil(clamp01(x / sw), clamp01(y / sh), PS); }
};
})();
