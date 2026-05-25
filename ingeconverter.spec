# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — multiplataforma (Linux + Windows).

Build:
    Linux:   venv/bin/pyinstaller ingeconverter.spec --noconfirm
    Windows: pyinstaller ingeconverter.spec --noconfirm

Linux → binario standalone onefile (~72 MB), requiere Docker.
Windows → carpeta onedir (evita warning _MEI de cleanup), requiere LocalDB + ODBC.
"""
import sys

_is_windows = sys.platform == 'win32'

_hidden = ['pymssql']
if _is_windows:
    _hidden.append('pyodbc')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources/icons/ingeconverter.png', 'resources/icons'),
        ('resources/icons/ingeconverter_256.png', 'resources/icons'),
    ],
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if _is_windows:
    # Windows: onedir — no _MEI temp extraction, no cleanup warning.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        name='ingeconverter',
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
        icon='resources/icons/ingeconverter.ico',
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='ingeconverter',
    )
else:
    # Linux/macOS: onefile — binario único, más simple para distribución.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='ingeconverter',
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
        icon='resources/icons/ingeconverter.ico',
    )
