# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Z:\\Tools\\app\\Auto_CRM.py'],
    pathex=['Z:\\Tools', 'Z:\\Tools\\app'],
    binaries=[],
    datas=[],
    hiddenimports=['selenium.webdriver.chrome.options', 'selenium.webdriver.chrome.service', 'selenium.webdriver.chrome.webdriver'],
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
    name='Auto_CRM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
