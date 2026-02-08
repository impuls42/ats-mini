"""
PlatformIO post-upload hook for wait_monitor integration.

This script is loaded as a PlatformIO extra script but the actual wait_monitor
execution is handled by the Makefile for proper sequencing with upload.

When using PlatformIO directly without Make:
  pio run -t upload && python3 tools/wait_monitor.py

The Makefile handles this automatically:
  make upload        # Builds, uploads, and monitors
  make fullflash     # Full flash + monitor
"""

from __future__ import annotations
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from SCons.Script import Import as SConsImport  # type: ignore[reportMissingImports]
else:
    SConsImport = None  # type: ignore[assignment]

# --- Import the PlatformIO construction environment as "env"
if TYPE_CHECKING:
    # Tell Pylance that env exists and is "some object" with methods like AddPostAction, Execute, etc.
    env: Any
    cast(Any, None)  # no-op, just to keep linters quiet sometimes

if SConsImport is not None:
    SConsImport("env")
else:
    Import("env")  # type: ignore[name-defined]

env: Any = globals().get("env")


def after_upload(source, target, env):
    """Execute wait_monitor after upload completes."""
    if env is None:
        print("Warning: 'env' not found in globals. Skipping wait_monitor execution.")
        return

    project_dir = env.subst("${PROJECT_DIR}")
    script_path = os.path.join(project_dir, "tools", "wait_monitor.py")
    print(f"Post-upload hook: Running {script_path}...")
    venv_python = os.path.join(project_dir, ".venv", "bin", "python3")
    print(
        f"Using Python executable: {venv_python if os.path.exists(venv_python) else sys.executable}"
    )
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    print("\n" + "=" * 70)
    print("Upload complete. Running wait_monitor to capture boot logs...")
    print("=" * 70 + "\n")

    result = subprocess.run([python_exe, script_path], cwd=project_dir)

    if result.returncode != 0:
        print(f"wait_monitor exited with code {result.returncode}")
        return result.returncode


if env is not None:
    env.AddPostAction("upload", after_upload)
    env.AddPostAction("fullflash", after_upload)
