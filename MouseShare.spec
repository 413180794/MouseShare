# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['ApplicationServices', 'CoreFoundation']
hiddenimports += collect_submodules('mouseshare')


a = Analysis(
    ['/Users/z/ai_workspace/MouseShare/launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MouseShare',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/z/ai_workspace/MouseShare/build/icons/MouseShare.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MouseShare',
)
app = BUNDLE(
    coll,
    name='MouseShare.app',
    icon='/Users/z/ai_workspace/MouseShare/build/icons/MouseShare.icns',
    bundle_identifier='io.github.makesail.mouseshare',
)
