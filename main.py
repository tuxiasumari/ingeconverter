# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari / Sumari SAC
# This file is part of IngeConverter — complemento libre de IngePresupuestos.
# Licensed under the GNU GPL v3.0 or later. See the LICENSE file.
"""IngeConverter — Convertidor S10 → IngePresupuestos.

Entry point. Si recibe args CLI (--archivo, --listar, etc.) despacha al CLI
de `core.convertir`; si no, abre el wizard GUI.

Multiplataforma: usa Docker (Linux/Mac) o LocalDB (Windows) detectado por
`core/backend.py`. El wizard asiste en la instalación si el backend falta.
"""
from __future__ import annotations

import sys
from pathlib import Path


_CLI_FLAGS = {'--archivo', '--listar', '--todos', '--presupuesto', '--server',
              '--database', '--password', '--out', '--json', '--subpresupuesto',
              '--verbose', '-v'}


def _is_cli_invocation() -> bool:
    return any(arg in _CLI_FLAGS for arg in sys.argv[1:])


def _resource_path(rel: str) -> Path:
    """Resuelve un path relativo al repo (dev) o al bundle PyInstaller (prod).

    PyInstaller con --onefile extrae los datos a un dir temporal accesible
    como `sys._MEIPASS`. En dev usamos el dir del propio main.py.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / rel


def main() -> int:
    if _is_cli_invocation():
        from core.convertir import main as cli_main
        return cli_main()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from views.wizard import WizardPrincipal

    app = QApplication(sys.argv)
    app.setApplicationName("IngeConverter")
    app.setOrganizationName("IngePresupuestos")
    app.setDesktopFileName("ingeconverter")

    icon_path = _resource_path("resources/icons/ingeconverter.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    wiz = WizardPrincipal()
    wiz.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
