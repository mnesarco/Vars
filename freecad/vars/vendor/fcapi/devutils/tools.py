# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

import os
from pathlib import Path
import subprocess  # nosec B404: False positive
import sys
import PySide6 as ref_mod


def qt_tool_wrapper(
    qt_tool: str,
    args: list[str],
    *,
    libexec: bool = False,
    shell: bool = False,
) -> None:
    """
    Modified version of PySide6.scripts.pyside_tool.qt_tool_wrapper.

    Does not exit if succeeded.
    """
    pyside_dir = Path(ref_mod.__file__).resolve().parent
    if libexec and sys.platform != "win32":
        exe = pyside_dir / "Qt" / "libexec" / qt_tool
    else:
        exe = pyside_dir / qt_tool

    cmd = [os.fspath(exe), *args]
    returncode = subprocess.call(cmd, shell=shell)  # nosec B602: No user input
    if returncode != 0:
        command = " ".join(cmd)
        print(f"'{command}' returned {returncode}", file=sys.stderr)
        sys.exit(returncode)
