"""Keeps a second copy of the launcher/overlay from starting by holding a
named Windows mutex for the life of the process."""
import ctypes

_ERROR_ALREADY_EXISTS = 183
_held = []  # keeps the handle alive until the process exits


def acquire(name: str) -> bool:
    """Returns True if this is the only instance holding `name`."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\" + name)
    already_running = kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    if handle:
        _held.append(handle)
    return not already_running
