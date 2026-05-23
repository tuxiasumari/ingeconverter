"""IngeConverter — Convertidor S10 → IngePresupuestos.

Entry point. Abre el wizard principal.

Windows-only. Requiere Microsoft SQL Server LocalDB instalado (el wizard asiste
en la instalación la primera vez).
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from views.wizard import WizardPrincipal


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("IngeConverter")
    app.setOrganizationName("IngePresupuestos")

    wiz = WizardPrincipal()
    wiz.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
