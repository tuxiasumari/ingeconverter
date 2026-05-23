"""IngeConverter — Convertidor S10 → IngePresupuestos.

Entry point. Abre el wizard principal.

Multiplataforma: usa Docker (Linux/Mac) o LocalDB (Windows) detectado por
`core/backend.py`. El wizard asiste en la instalación si el backend falta.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from views.wizard import WizardPrincipal


def _resource_path(rel: str) -> Path:
    """Resuelve un path relativo al repo (dev) o al bundle PyInstaller (prod).

    PyInstaller con --onefile extrae los datos a un dir temporal accesible
    como `sys._MEIPASS`. En dev usamos el dir del propio main.py.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / rel


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("IngeConverter")
    app.setOrganizationName("IngePresupuestos")
    # Vincula la ventana con un .desktop "ingeconverter.desktop" para que
    # GNOME/KDE muestren el ícono correcto en el dock/taskbar. Sin esto en
    # Ubuntu (Wayland) sale el genérico de Python aunque setWindowIcon esté.
    app.setDesktopFileName("ingeconverter")

    # Ícono — se setea a nivel QApplication para que aplique a TODA la app
    # (ventanas y diálogos). Para el dock/taskbar de GNOME hace falta además
    # el .desktop file instalado (ver `resources/ingeconverter.desktop`).
    icon_path = _resource_path("resources/icons/ingeconverter.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    wiz = WizardPrincipal()
    wiz.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
