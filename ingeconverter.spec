# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — generado 2026-05-22.

Build:
    venv/bin/pyinstaller ingeconverter.spec --noconfirm

Genera `dist/ingeconverter` (~72 MB) como binario standalone Linux que NO
requiere Python ni venv en la máquina destino. Solo necesita Docker (que el
backend instala/guía si falta).

Para agregar icono, hidden imports o datas en el futuro, editar Analysis(...)
y EXE(...) abajo.
"""


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
)
