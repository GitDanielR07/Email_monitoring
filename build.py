#!/usr/bin/env python3
"""
Build script to compile monitor_email_push.py into monitor_email_push.exe.

Run it with the project's virtual environment so the exe bundles the right packages:
    .venv\\Scripts\\python.exe build.py
"""

import subprocess
import sys
import os
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)  # exe is written to the project root, next to .env and config/

EXE_NAME = 'monitor_email_push.exe'
SPEC_FILE = os.path.join('packaging', 'monitor_email_push.spec')
# The old polling monitor competes with the push monitor (both mark emails read),
# so stop it too.
PROCESSES_TO_STOP = {EXE_NAME, 'monitor_email.exe'}


def stop_running_process():
    """Stop any running monitor processes so the exe can be replaced."""
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] in PROCESSES_TO_STOP:
                print(f"Stopping {proc.info['name']} (PID: {proc.info['pid']})...")
                proc.kill()
                time.sleep(1)
    except ImportError:
        print("Note: psutil not available, skipping process check")
    except Exception as e:
        print(f"Warning: Could not stop process: {e}")


def clean_old_exe():
    """Remove old executable."""
    if os.path.exists(EXE_NAME):
        try:
            os.remove(EXE_NAME)
            print(f"Removed old {EXE_NAME}")
        except Exception as e:
            print(f"Warning: Could not remove old exe: {e}")


def build_exe():
    """Run PyInstaller (from this same Python environment) to build the executable."""
    print(f"Building {EXE_NAME} with {sys.executable} ...")
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        SPEC_FILE,
        '--distpath', '.',
        '--workpath', 'build',
        '-y'
    ]

    try:
        subprocess.run(cmd, check=True)
        print("\nBuild completed successfully!")
        print(f"Executable: {os.path.abspath(EXE_NAME)}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error code {e.returncode}")
        return False
    except Exception as e:
        print(f"\nBuild error: {e}")
        return False


def main():
    print("=" * 60)
    print("Monitor Email Push - Build Script")
    print("=" * 60)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed in this environment. Run:")
        print(f"  {sys.executable} -m pip install pyinstaller")
        sys.exit(1)

    stop_running_process()
    clean_old_exe()
    success = build_exe()

    print("=" * 60)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
