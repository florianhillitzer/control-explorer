# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


control_datas, control_binaries, control_hiddenimports = collect_all("control")

a = Analysis(
    ["control_explorer_gui.py"],
    pathex=[],
    binaries=control_binaries,
    datas=[
        ("control_explorer.ico", "."),
        ("control_explorer_icon.png", "."),
        ("mrm_logo.png", "."),
        ("VERSION", "."),
        ("LICENSE", "."),
        ("NOTICE", "."),
        ("docs", "docs"),
    ] + control_datas,
    hiddenimports=control_hiddenimports,
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
    [],
    exclude_binaries=True,
    name="ControlExplorer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="control_explorer.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ControlExplorer",
)
