"""
Windows platform layer — keyboard polling, process priority, cursor position.

All Win32 access is isolated here and guarded: on a non-Windows host (or if
user32/kernel32 are unavailable) the functions degrade to safe no-ops so the
rest of the package still imports and can be unit-tested off-Windows.
"""

import ctypes

# Virtual-key codes ---------------------------------------------------------
VK_CTRL  = 0x11
VK_ALT   = 0x12
VK_ENTER = 0x0D
VK_Q     = 0x51
VK_R     = 0x52
VK_F7    = 0x76
VK_F8    = 0x77
VK_F9    = 0x78
VK_UP    = 0x26
VK_LEFT  = 0x25
VK_RIGHT = 0x27
VK_1     = 0x31
VK_2     = 0x32

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
