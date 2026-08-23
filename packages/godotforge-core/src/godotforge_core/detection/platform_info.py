"""Platform information gathering."""

from __future__ import annotations

import platform
import sys


def platform_info() -> dict:
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
    import os

    return os.name == "nt"
