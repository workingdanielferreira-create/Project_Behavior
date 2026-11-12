"""
Action bar data for the HUD cards' Ready Gate (laser/hpbars.py) and what a
click on one of its icons does (laser/hudclick.py).  Daniel 2026-11-12.
Solo and Battle alike.

Each fielded image character (actions.is_image) gets one icon per action
of its attack chains, in chain order:

    attack_normal  -> attack_normal_2  -> ...   labels N1, N2, ... (own suffix)
    attack_special -> attack_special_2 -> ...   labels S1, S2, ...
    ultimate       -> ultimate_2       -> ...   labels ULT, ULT2, ...

(player.chain_names: only actions the character has frames for), plus TAG
when its slot is half of a tag pair.  Built-ins (swordsman / runner) have
no per-action cooldowns and get no icons.  Unique abilities come later.

Cooldowns are read, never changed: an action's ms left = its
ActionRunner.cooldown_until against the fighter's cooldown clock
(unique.cd_now, so a benched fighter's icons stay frozen), its length =
action_settings[name].cooldown_ms.  The Switch's ms left = the pair's
cooldown_until against the world tick, its length = the on-field fighter's
switch_in cooldown_ms (the one that came in last set it).

A click is ready-only: a cooling icon only shakes.  A ready action is
queued with actions.request_manual (skips trigger conditions and Attack
mode, starts its cooldown, the AI keeps fighting); TAG goes through
tag.request like the "Tag in" hotkey.
"""

import re

from . import actions, config, player, tag, unique
from . import roster as _roster

TICK_MS = config.TICK_MS

KINDS = (("attack", "N", "normal"), ("special", "S", "special"), ("ultimate", "ULT", "ult"))


class Entry:
    __slots__ = ("key", "name", "label", "group", "left_ms", "total_ms", "state")

    def __init__(self, key, name, label, group, left_ms, total_ms, state):
        self.key = key            # (slot index, name): stable across frames
        self.name = name          # action name, or "switch"
        self.label = label
        self.group = group        # normal | special | ult | tag
        self.left_ms = left_ms
        self.total_ms = total_ms
        self.state = state        # ready | cool | frozen | blocked


def _label(prefix, name):
    """N1 / N4 / S2 / ULT / ULT2: the number is the action's own suffix
    (attack_normal_4 = N4), not its place in the chain."""
    m = re.search(r"_(\d+)$", name)
    i = int(m.group(1)) if m else 1
    if prefix == "ULT":
        return "ULT" if i == 1 else "ULT%d" % i
    return "%s%d" % (prefix, i)


def entries(world, slot, status):
    """The Ready Gate icons for roster slot `slot` (tag.status = status)."""
    fig = slot.fig
    if fig is None or status not in ("on", "bench") or unique.is_clone(fig):
        return []
    if not actions.is_image(fig):
        return []
    out = []
    frozen = status == "bench"
    for kind, prefix, group in KINDS:
        for name in player.chain_names(fig, kind):
            left = actions.manual_left_ms(fig, world, name)
            total = float(actions._cfg(fig, name).get("cooldown_ms") or 0)
            st = "frozen" if frozen else ("cool" if left > 0 else "ready")
            out.append(Entry((slot.index, name), name, _label(prefix, name), group,
                             left, max(total, left), st))
    pr = _pair_of(world, slot)
    if pr is not None and not frozen:
        other = pr.off if pr.on is slot else pr.on
        left = max(0.0, (pr.cooldown_until - world.global_tick) * TICK_MS)
        on_fig = pr.on.fig
        total = float(actions._cfg(on_fig, "switch_in").get("cooldown_ms") or 0) if on_fig is not None else 0.0
        down = other.fig is None or other.fig.personality.hp <= 0
        st = "blocked" if down else ("cool" if left > 0 or pr.phase != "idle" else "ready")
        out.append(Entry((slot.index, "switch"), "switch", "TAG", "tag", left, max(total, left), st))
    return out


def _pair_of(world, slot):
    for pr in getattr(world, "tag_pairs", ()) or ():
        if pr is not None and slot in pr.slots():
            return pr
    return None


def _slot(world, index):
    for s in getattr(world, "slots", None) or []:
        if s.index == index:
            return s
    return None


def fire(world, key):
    """A click on icon `key` = (slot index, action).  True when it was
    accepted (queued); False = not ready (the icon shakes)."""
    idx, name = key
    s = _slot(world, idx)
    if s is None or s.fig is None or tag.status(world, s) != "on":
        return False
    if name == "switch":
        pr = _pair_of(world, s)
        if pr is None or pr.on is not s or pr.phase != "idle" or world.global_tick < pr.cooldown_until:
            return False
        off = pr.off.fig
        if off is None or off.personality.hp <= 0:
            return False
        tag.request(world, pr.off.index)
        return True
    return actions.request_manual(s.fig, world, name)


def pair_color(world, slot):
    pairs = list(getattr(world, "tag_pairs", None) or [])
    for k, pr in enumerate(pairs):
        if pr is not None and slot in pr.slots():
            return _roster.PAIR_COLORS[k % len(_roster.PAIR_COLORS)]
    return _roster.PAIR_COLORS[0]
