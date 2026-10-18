"""Native platform input implementations."""
import platform


def create_backend(emit):
    if platform.system() == "Windows":
        from .windows import WindowsBackend
        return WindowsBackend(emit)
    if platform.system() == "Darwin":
        from .macos import MacBackend
        return MacBackend(emit)
    if platform.system() == "Linux":
        from .linux import LinuxBackend
        return LinuxBackend(emit)
    from .base import NullBackend
    return NullBackend(emit)

