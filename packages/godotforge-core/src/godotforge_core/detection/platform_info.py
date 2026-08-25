"""Platform information gathering."""

from __future__ import annotations

import platform
import sys


def platform_info() -> dict:
    """platform_info — production helper."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "executable": sys.executable,
        "on_windows": os_name_is_nt(),
    }


def os_name_is_nt() -> bool:
    """os_name_is_nt — production helper."""
    import os

    return os.name == "nt"
