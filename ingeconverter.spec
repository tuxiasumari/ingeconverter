# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — multiplataforma (Linux + Windows).

Build:
    Linux:   venv/bin/pyinstaller ingeconverter.spec --noconfirm
    Windows: pyinstaller ingeconverter.spec --noconfirm

Linux → binario standalone onefile (~72 MB), requiere Docker.
Windows → binario standalone onefile, requiere LocalDB + driver ODBC.
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
