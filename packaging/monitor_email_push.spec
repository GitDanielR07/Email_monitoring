# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# google-cloud-pubsub / grpc look up their package metadata at runtime.
datas = []
for pkg in ("google-cloud-pubsub", "google-api-core", "grpcio", "google-api-python-client"):
    datas += copy_metadata(pkg)

hiddenimports = collect_submodules("google.cloud.pubsub_v1") + ["googleapiclient.discovery_cache"]


a = Analysis(
    [os.path.join(ROOT, 'src', 'monitor_email_push.py')],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='monitor_email_push',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, 'assets', 'gmail.ico')],
)
