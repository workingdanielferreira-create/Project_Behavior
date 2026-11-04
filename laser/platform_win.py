"""
Windows platform layer — keyboard polling, process priority, cursor position.

All Win32 access is isolated here and guarded: on a non-Windows host (or if
user32/kernel32 are unavailable) the functions degrade to safe no-ops so the
rest of the package still imports and can be unit-tested off-Windows.
"""

import ctypes

# Virtual-key codes ---------------------------------------------------------
VK_CTRL  = 0x11
VK_SHIFT = 0x10            # Ctrl+Shift+. (Ctrl+'>'): pre-battle menu (laser/prebattle.py)
VK_ALT   = 0x12
VK_ENTER = 0x0D
VK_Q     = 0x51
VK_R     = 0x52
VK_F4    = 0x73            # player control on / off (World.player_on, laser/player.py)
VK_F5    = 0x74            # reload characters from disk (World.reload_characters)
VK_F6    = 0x75            # preview the next clash explosion at the cursor (World.preview_clash_fx)
VK_F7    = 0x76
VK_F8    = 0x77
VK_F9    = 0x78
VK_F10   = 0x79            # freeze fighters (World.freeze_fighters)
VK_F11   = 0x7A            # first-picked fighter follows the cursor (World.puppet_on)
VK_F12   = 0x7B            # see-through boulders (World.boulders_ghost)
VK_UP    = 0x26
VK_DOWN  = 0x28            # arrow keys: player-controlled movement (laser/player.py)
VK_LEFT  = 0x25
VK_RIGHT = 0x27
VK_SPACE = 0x20            # Ctrl+Space: player fighter's HP to 25% (laser/player.py)
VK_Z     = 0x5A            # Ctrl+Z: player attack_normal chain
VK_X     = 0x58            # Ctrl+X: player attack_special chain
VK_C     = 0x43            # Ctrl+C: player ultimate chain
VK_0     = 0x30            # Ctrl+0: roster lock toggle (World.roster_locked)
VK_1     = 0x31
VK_2     = 0x32
VK_3     = 0x33            # default slot C key (laser/roster.py)
VK_4     = 0x34            # default slot D key (laser/roster.py)
VK_PERIOD = 0xBE           # VK_OEM_PERIOD: the '.' / '>' key

_BELOW_NORMAL = 0x00004000

# Resolve Win32 entry points once; stay None off-Windows. -------------------
try:
    _user32   = ctypes.windll.user32        # type: ignore[attr-defined]
    _kernel32 = ctypes.windll.kernel32      # type: ignore[attr-defined]
    _gaks     = _user32.GetAsyncKeyState
    IS_WINDOWS = True
except (AttributeError, OSError):
    _user32 = _kernel32 = _gaks = None
    IS_WINDOWS = False


def key_down(vk):
    """True while the given virtual-key is held (False off-Windows)."""
    if _gaks is None:
        return False
    return _gaks(vk) & 0x8000 != 0


def lower_process_priority():
    """Drop to below-normal priority so the overlay never starves the system."""
    if _kernel32 is None:
        return
    try:
        _kernel32.SetPriorityClass(_kernel32.GetCurrentProcess(), _BELOW_NORMAL)
    except OSError:
        pass
