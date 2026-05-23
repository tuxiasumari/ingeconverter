"""Wizard principal de IngeConverter.

Esqueleto inicial. Por ahora muestra una ventana placeholder que documenta
los 3 pasos del flujo final:

1. Detectar / instalar SQL Server LocalDB.
2. Seleccionar archivo S10 (.S2K, .bak, .bkf) y attachear.
3. Convertir y generar .db destino.

Cada paso se irá construyendo en próximas sesiones.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy,
)


# Paleta — reutiliza la de IngePresupuestos para que ambos productos se sientan
# parte de la misma familia visual.
ORANGE      = "#F37329"
ORANGE_DARK = "#C0621A"
SLATE_700   = "#273445"
SLATE_500   = "#485A6C"
SLATE_300   = "#667885"
SILVER_100  = "#F8F9FA"
SILVER_300  = "#D4D4D4"
WHITE       = "#FFFFFF"


class WizardPrincipal(QWidget):
    """Ventana principal. Por ahora placeholder."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("IngeConverter — Migración de S10 a IngePresupuestos")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(f"QWidget {{ background:{WHITE}; color:{SLATE_700}; }}")
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 24, 30, 24)
        v.setSpacing(14)

        # Header
        h_head = QHBoxLayout()
        lbl_title = QLabel("IngeConverter")
        f = QFont()
        f.setPointSize(20)
        f.setWeight(QFont.DemiBold)
        lbl_title.setFont(f)
        lbl_title.setStyleSheet(
            f"color:{SLATE_700}; background:transparent; border:none;"
        )
        h_head.addWidget(lbl_title)
        h_head.addStretch(1)
        lbl_ver = QLabel("v0.1.0 — Esqueleto")
        lbl_ver.setStyleSheet(
            f"color:{SLATE_300}; font-size:11px;"
            f" background:transparent; border:none;"
        )
        h_head.addWidget(lbl_ver, alignment=Qt.AlignBottom)
        v.addLayout(h_head)

        lbl_sub = QLabel(
            "Convertí tu base de datos de S10 (.S2K, .bak, .bkf) "
            "al formato libre de IngePresupuestos."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet(
            f"color:{SLATE_500}; font-size:12px;"
            f" background:transparent; border:none;"
        )
        v.addWidget(lbl_sub)

        # Línea separadora
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{SILVER_300}; background:{SILVER_300};")
        sep.setFixedHeight(1)
        v.addWidget(sep)

        # Tres pasos
        for n, titulo, sub in [
            ("1", "Detectar SQL Server LocalDB",
             "Verificá que tu PC tenga LocalDB instalado. Si no lo tiene, te "
             "guiamos a descargarlo desde Microsoft (140 MB, gratis y oficial)."),
            ("2", "Seleccionar archivo de S10",
             "Indicá el .S2K, .bak o .bkf que querés migrar. Lo restauramos o "
             "atacheamos en LocalDB automáticamente."),
            ("3", "Convertir a IngePresupuestos",
             "Generamos un archivo .db SQLite con todas tus partidas, ACUs, "
             "recursos e índices INEI. Listo para abrir en IngePresupuestos."),
        ]:
            v.addWidget(self._build_paso(n, titulo, sub))

        v.addStretch(1)

        # Botones (placeholder)
        h_bot = QHBoxLayout()
        h_bot.addStretch(1)
        btn_empezar = QPushButton("Empezar  (próximamente)")
        btn_empezar.setEnabled(False)
        btn_empezar.setMinimumHeight(36)
        btn_empezar.setStyleSheet(
            f"QPushButton {{ background:{ORANGE}; color:white;"
            f" border:1px solid {ORANGE_DARK}; border-radius:6px;"
            f" padding:6px 24px; font-size:13px; font-weight:600; }}"
            f"QPushButton:hover:enabled {{ background:{ORANGE_DARK}; }}"
            f"QPushButton:disabled {{ background:{SILVER_300}; color:{SLATE_300};"
            f" border-color:{SILVER_300}; }}"
        )
        h_bot.addWidget(btn_empezar)
        v.addLayout(h_bot)

        # Pie
        lbl_pie = QLabel(
            "Esqueleto inicial. Funcionalidad en construcción — sesión 2026-05-22."
        )
        lbl_pie.setStyleSheet(
            f"color:{SLATE_300}; font-size:10px;"
            f" background:transparent; border:none;"
        )
        lbl_pie.setAlignment(Qt.AlignCenter)
        v.addWidget(lbl_pie)

    def _build_paso(self, n: str, titulo: str, sub: str) -> QFrame:
        card = QFrame()
        card.setObjectName("paso")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(
            f"QFrame#paso {{ background:{SILVER_100};"
            f" border:1px solid {SILVER_300}; border-radius:8px; }}"
        )
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(14)

        lbl_n = QLabel(n)
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        lbl_n.setFont(f)
        lbl_n.setFixedSize(40, 40)
        lbl_n.setAlignment(Qt.AlignCenter)
        lbl_n.setStyleSheet(
            f"color:white; background:{ORANGE}; border:none;"
            f" border-radius:20px;"
        )
        h.addWidget(lbl_n)

        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_t = QLabel(titulo)
        ft = QFont()
        ft.setBold(True)
        lbl_t.setFont(ft)
        lbl_t.setStyleSheet(
            f"color:{SLATE_700}; background:transparent; border:none;"
        )
        col.addWidget(lbl_t)
        lbl_s = QLabel(sub)
        lbl_s.setWordWrap(True)
        lbl_s.setStyleSheet(
            f"color:{SLATE_500}; font-size:11px;"
            f" background:transparent; border:none;"
        )
        col.addWidget(lbl_s)
        h.addLayout(col, 1)

        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return card
