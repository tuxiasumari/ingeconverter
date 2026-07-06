# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari / Sumari SAC
# This file is part of IngeConverter — complemento libre de IngePresupuestos.
# Licensed under the GNU GPL v3.0 or later. See the LICENSE file.
"""Wizard principal de IngeConverter — UI standalone.

Para el caso "usuario que descarga IngeConverter directo, no desde
IngePresupuestos". Si vino desde IngePresupuestos, el subprocess se invoca
sin UI (ver `core/ingeconverter_bridge.py` en `~/ingepresupuestos-pyside6/`).

**Flujo (6 páginas en un `QStackedWidget`):**
1. Intro            — bienvenida + botón "Comenzar"
2. Backend check    — verifica Docker/LocalDB; instrucciones si falta
3. Elegir archivo   — QFileDialog del .S2K/.bak/.bkf
4. Elegir presup.   — diálogo multi-selección (tras restaurar el backup)
5. Conversión       — barra de progreso + log de stderr
6. Resultado        — listado de .db generados + "Abrir carpeta"

Paleta y look-and-feel replicados de `importar_view.py` de IngePresupuestos
para que ambos productos se sientan parte de la misma familia visual.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)


# ── Paleta (clonada de IngePresupuestos) ─────────────────────────────────────
ORANGE      = "#F37329"
ORANGE_DARK = "#C0621A"
ORANGE_SOFT = "#FEF5EB"
SLATE_700   = "#273445"
SLATE_500   = "#485A6C"
SLATE_300   = "#667885"
SILVER_100  = "#F8F9FA"
SILVER_200  = "#F0F1F2"
SILVER_300  = "#D4D4D4"
WHITE       = "#FFFFFF"
GREEN_500   = "#68B723"
RED_500     = "#C6262E"


def _btn_primary() -> str:
    return (
        f"QPushButton {{ background:{ORANGE}; color:white;"
        f" border:1px solid {ORANGE_DARK}; border-radius:6px;"
        f" padding:6px 22px; font-size:13px; font-weight:600; }}"
        f"QPushButton:hover:enabled {{ background:{ORANGE_DARK}; }}"
        f"QPushButton:disabled {{ background:{SILVER_300}; color:{SLATE_300};"
        f" border-color:{SILVER_300}; }}"
    )


def _btn_secondary() -> str:
    return (
        f"QPushButton {{ background:{WHITE}; color:{SLATE_700};"
        f" border:1px solid {SILVER_300}; border-radius:6px;"
        f" padding:6px 18px; font-size:12px; }}"
        f"QPushButton:hover:enabled {{ background:{SILVER_200}; }}"
        f"QPushButton:disabled {{ color:{SLATE_300}; border-color:{SILVER_300}; }}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# Workers (QThread)
# ═════════════════════════════════════════════════════════════════════════════

class _PrepararWorker(QThread):
    """Verifica que el backend (Docker/LocalDB) está instalado y operativo.

    Levanta el container/instancia si hace falta (Docker la primera vez puede
    tardar minutos por el `docker pull`). Emite `failed` si no se puede.
    """
    progreso = Signal(str)
    finished_ok = Signal(str)        # nombre legible del backend ("Docker"/"LocalDB")
    failed = Signal(str)

    def run(self):
        try:
            from core.backend import BackendError, crear_backend
            backend = crear_backend()
            self.progreso.emit("Detectando backend SQL Server…")
            if not backend.esta_disponible():
                self.failed.emit(backend.instrucciones_instalacion())
                return
            nombre = type(backend).__name__.replace("Backend", "")
            self.progreso.emit(f"{nombre} disponible. Preparando server…")
            backend.preparar()
            self.finished_ok.emit(nombre)
        except Exception as e:
            import traceback
            self.failed.emit(f"{e}\n\n{traceback.format_exc()[-600:]}")


class _ListarWorker(QThread):
    """Restaura el backup en SQL Server y lista los presupuestos."""
    progreso = Signal(str)
    finished_list = Signal(list)     # [{cod, descripcion}, ...]
    failed = Signal(str)

    def __init__(self, archivo: Path, parent=None):
        super().__init__(parent)
        self.archivo = archivo

    def run(self):
        try:
            from core.backend import (
                BackendError, BackupVersionTooOld, crear_backend,
            )
            backend = crear_backend()
            self.progreso.emit("Preparando backend…")
            backend.preparar()

            self.progreso.emit(f"Restaurando {self.archivo.name}…")
            backend.restaurar(self.archivo)

            self.progreso.emit("Listando presupuestos del backup…")
            conn = backend.conectar()
            try:
                from core.s10_reader import S10Reader
                reader = S10Reader(conn)
                presupuestos = reader.listar_presupuestos()
            finally:
                conn.close()
                backend.limpiar()

            self.finished_list.emit(
                [{"cod": c, "descripcion": d} for c, d in presupuestos]
            )
        except BackupVersionTooOld as e:
            self.failed.emit(str(e))
        except Exception as e:
            import traceback
            self.failed.emit(f"{e}\n\n{traceback.format_exc()[-600:]}")


class _ConvertirWorker(QThread):
    """Convierte los presupuestos elegidos a archivos .db en `dir_destino/`."""
    progreso = Signal(str)
    finished_ok = Signal(list, str)  # [paths .db generados], resumen
    failed = Signal(str)

    def __init__(self, archivo: Path, cods: list[str], dir_destino: Path,
                 parent=None):
        super().__init__(parent)
        self.archivo = archivo
        self.cods = cods
        self.dir_destino = dir_destino

    def run(self):
        import re

        try:
            from core.backend import crear_backend
            from core.convertir import convertir_proyecto
            from core.s10_reader import S10Reader
            from core.sqlite_writer import SQLiteWriter

            backend = crear_backend()
            self.progreso.emit("Preparando backend…")
            backend.preparar()

            self.progreso.emit(f"Restaurando {self.archivo.name}…")
            backend.restaurar(self.archivo)

            paths: list[Path] = []
            errores: list[str] = []
            total = len(self.cods)
            self.dir_destino.mkdir(parents=True, exist_ok=True)
            conn = backend.conectar()
            try:
                reader = S10Reader(conn)
                # Recuperar descripciones para nombres de archivo legibles
                todos = dict(reader.listar_presupuestos())
                for i, cod in enumerate(self.cods, 1):
                    desc = todos.get(cod, "")
                    safe = re.sub(r"[^\w\-]+", "_", desc[:60]).strip("_") or "proyecto"
                    out_path = self.dir_destino / f"{cod}_{safe}.db"
                    self.progreso.emit(
                        f"[{i}/{total}] Convirtiendo {cod} — {desc[:60]}…"
                    )
                    try:
                        with SQLiteWriter(str(out_path), fresh=True) as writer:
                            convertir_proyecto(reader, writer, cod, None)
                        paths.append(out_path)
                    except Exception as e:
                        errores.append(f"{cod}: {e}")
            finally:
                conn.close()
                backend.limpiar()

            resumen = f"{len(paths)} archivo(s) .db generado(s) en {self.dir_destino}"
            if errores:
                resumen += f"\n\n{len(errores)} con error:\n" + "\n".join(errores[:10])
            self.finished_ok.emit(paths, resumen)
        except Exception as e:
            import traceback
            self.failed.emit(f"{e}\n\n{traceback.format_exc()[-600:]}")


# ═════════════════════════════════════════════════════════════════════════════
# Páginas
# ═════════════════════════════════════════════════════════════════════════════

class _Pagina(QWidget):
    """Base de cualquier página del wizard. Aporta layout vertical + el método
    `_titulo(texto, subtexto)` para mantener consistencia visual."""

    def _titulo(self, texto: str, subtexto: str) -> QVBoxLayout:
        ttl = QLabel(texto)
        ft = QFont(); ft.setPointSize(15); ft.setWeight(QFont.DemiBold)
        ttl.setFont(ft)
        ttl.setStyleSheet(f"color:{SLATE_700}; background:transparent;")

        sub = QLabel(subtexto)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{SLATE_500}; font-size:12px; background:transparent;")

        l = QVBoxLayout()
        l.setSpacing(4)
        l.addWidget(ttl)
        l.addWidget(sub)
        return l


class _PaginaIntro(_Pagina):
    """Bienvenida + botón 'Comenzar'."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addLayout(self._titulo(
            "Bienvenido a IngeConverter",
            "Convertí tu base de datos nativa de S10 (.S2K, .bak, .bkf) al "
            "formato libre de IngePresupuestos."
        ))

        # Cards explicativos (los 3 pasos siguientes)
        for n, titulo, sub in [
            ("1", "Preparar SQL Server",
             "Detectamos Docker (Linux/Mac) o LocalDB (Windows) y lo "
             "configuramos por vos. Solo la primera vez tarda un poco."),
            ("2", "Elegir el archivo y los presupuestos",
             "Indicás el .S2K y elegís cuáles presupuestos querés convertir "
             "(uno, varios o todos los del archivo)."),
            ("3", "Generar archivos .db",
             "Generamos un archivo .db por cada presupuesto, listo para abrir "
             "desde IngePresupuestos → Importar → Base nativa (.db)."),
        ]:
            v.addWidget(_card_paso(n, titulo, sub))

        v.addStretch(1)


class _PaginaBackend(_Pagina):
    """Detecta backend. Cuando OK pasa solo; cuando falla muestra ayuda."""

    listo = Signal(str)  # nombre legible del backend
    pedir_reintentar = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addLayout(self._titulo(
            "Preparando SQL Server",
            "Necesitamos SQL Server local para restaurar el backup de S10. "
            "Lo gestionamos por vos."
        ))

        self.lbl_estado = QLabel("Detectando…")
        self.lbl_estado.setStyleSheet(
            f"color:{SLATE_700}; font-size:12px; background:transparent;"
        )
        v.addWidget(self.lbl_estado)

        self.txt_ayuda = QTextEdit()
        self.txt_ayuda.setReadOnly(True)
        self.txt_ayuda.setVisible(False)
        self.txt_ayuda.setStyleSheet(
            f"QTextEdit {{ background:{SILVER_100}; color:{SLATE_700};"
            f" border:1px solid {SILVER_300}; border-radius:6px;"
            f" padding:10px; font-family:monospace; font-size:12px; }}"
        )
        v.addWidget(self.txt_ayuda, 1)

        self.btn_reintentar = QPushButton("Reintentar")
        self.btn_reintentar.setStyleSheet(_btn_secondary())
        self.btn_reintentar.setVisible(False)
        self.btn_reintentar.clicked.connect(self.pedir_reintentar.emit)
        h = QHBoxLayout(); h.addStretch(1); h.addWidget(self.btn_reintentar)
        v.addLayout(h)

        v.addStretch(1)

    def iniciar(self):
        self.txt_ayuda.setVisible(False)
        self.btn_reintentar.setVisible(False)
        self.lbl_estado.setText("Detectando backend…")
        self._worker = _PrepararWorker(self)
        self._worker.progreso.connect(self.lbl_estado.setText)
        self._worker.finished_ok.connect(self._ok)
        self._worker.failed.connect(self._fallo)
        self._worker.start()

    def _ok(self, nombre: str):
        self.lbl_estado.setText(f"✓ {nombre} operativo")
        self.listo.emit(nombre)

    def _fallo(self, mensaje: str):
        self.lbl_estado.setText("✗ No se pudo preparar SQL Server")
        self.txt_ayuda.setPlainText(mensaje)
        self.txt_ayuda.setVisible(True)
        self.btn_reintentar.setVisible(True)


class _PaginaArchivo(_Pagina):
    """Elegir el .S2K/.bak/.bkf que se va a convertir."""

    archivo_listo = Signal(Path)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addLayout(self._titulo(
            "Seleccionar archivo de S10",
            "Buscá tu archivo .S2K, .bak o .bkf. Si tu backup viene de "
            "SQL Server 7.0 o 2000 (muy antiguo, pre-2005), no se puede "
            "migrar — exportá uno nuevo desde una versión moderna de S10."
        ))

        # Card de archivo seleccionado
        self.card = QFrame()
        self.card.setObjectName("filecard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        self.card.setStyleSheet(
            f"QFrame#filecard {{ background:{SILVER_100};"
            f" border:1px solid {SILVER_300}; border-radius:8px; }}"
        )
        ch = QHBoxLayout(self.card)
        ch.setContentsMargins(16, 12, 16, 12)
        ch.setSpacing(12)

        self.lbl_path = QLabel("Ningún archivo seleccionado")
        self.lbl_path.setStyleSheet(
            f"color:{SLATE_500}; font-size:12px; background:transparent;"
        )
        ch.addWidget(self.lbl_path, 1)

        self.btn_elegir = QPushButton("Elegir archivo…")
        self.btn_elegir.setStyleSheet(_btn_secondary())
        self.btn_elegir.clicked.connect(self._elegir)
        ch.addWidget(self.btn_elegir)
        v.addWidget(self.card)
        v.addStretch(1)

        self._archivo: Optional[Path] = None

    def _elegir(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegí un backup de S10",
            str(Path.home()),
            "Backups S10 (*.S2K *.s2k *.bak *.bkf);;Todos los archivos (*)",
        )
        if not path:
            return
        p = Path(path)
        self._archivo = p
        self.lbl_path.setText(f"📦 {p.name}\n<small style='color:{SLATE_300}'>{p.parent}</small>".replace('<small', '\n<small'))
        self.lbl_path.setStyleSheet(f"color:{SLATE_700}; font-size:13px; background:transparent;")
        self.archivo_listo.emit(p)

    def archivo(self) -> Optional[Path]:
        return self._archivo


class _PaginaSeleccion(_Pagina):
    """Tras listar presupuestos, mostrar lista multi-selección + elegir destino."""

    listo_para_convertir = Signal(list, Path)  # cods, dir_destino

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addLayout(self._titulo(
            "Elegir presupuestos a convertir",
            "El archivo contiene los siguientes presupuestos. Elegí los que "
            "querés convertir (Ctrl+Click suma, Shift+Click rango)."
        ))

        # Barra de búsqueda + acciones rápidas
        top = QHBoxLayout(); top.setSpacing(8)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Buscar por nombre o código…")
        self.inp.setFixedHeight(34)
        self.inp.setStyleSheet(
            f"QLineEdit {{ background:white; border:1px solid {SILVER_300};"
            f" border-radius:6px; padding:0 12px; font-size:13px; }}"
        )
        self.inp.textChanged.connect(self._filtrar)
        top.addWidget(self.inp, 1)
        self.btn_all = QPushButton("Seleccionar todos")
        self.btn_all.setStyleSheet(_btn_secondary())
        self.btn_all.clicked.connect(self._sel_todos)
        top.addWidget(self.btn_all)
        self.btn_none = QPushButton("Deseleccionar")
        self.btn_none.setStyleSheet(_btn_secondary())
        self.btn_none.clicked.connect(lambda: self.lst.clearSelection())
        top.addWidget(self.btn_none)
        v.addLayout(top)

        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lst.setStyleSheet(
            f"QListWidget {{ background:white; border:1px solid {SILVER_300};"
            f" border-radius:8px; padding:4px; font-size:12px; }}"
            f"QListWidget::item {{ padding:6px 10px; border-bottom:1px solid {SILVER_200}; }}"
            f"QListWidget::item:selected {{ background:{ORANGE_SOFT}; color:{ORANGE_DARK};"
            f" border-radius:4px; }}"
        )
        self.lst.itemSelectionChanged.connect(self._actualizar_contador)
        v.addWidget(self.lst, 1)

        # Footer: contador + destino + botón convertir
        self.lbl_count = QLabel("0 seleccionados")
        self.lbl_count.setStyleSheet(f"color:{SLATE_500}; font-size:12px; font-weight:600;")
        v.addWidget(self.lbl_count)

        h_dest = QHBoxLayout(); h_dest.setSpacing(8)
        h_dest.addWidget(QLabel("Carpeta destino:"))
        self.lbl_dest = QLabel("(elegir)")
        self.lbl_dest.setStyleSheet(f"color:{SLATE_500}; font-size:12px;")
        h_dest.addWidget(self.lbl_dest, 1)
        self.btn_dest = QPushButton("Elegir carpeta…")
        self.btn_dest.setStyleSheet(_btn_secondary())
        self.btn_dest.clicked.connect(self._elegir_dest)
        h_dest.addWidget(self.btn_dest)
        v.addLayout(h_dest)

        self._presupuestos: list[dict] = []
        self._dir_dest: Optional[Path] = None

    def cargar(self, presupuestos: list[dict], archivo: Path):
        self._presupuestos = presupuestos
        self._dir_dest = archivo.parent / f"{archivo.stem}_db"
        self.lbl_dest.setText(str(self._dir_dest))
        self._refrescar()

    def _refrescar(self, filtro: str = ""):
        self.lst.clear()
        f = filtro.strip().lower()
        for p in self._presupuestos:
            if f and f not in p["descripcion"].lower() and f not in p["cod"]:
                continue
            it = QListWidgetItem(f"{p['cod']}    {p['descripcion']}")
            it.setData(Qt.UserRole, p["cod"])
            self.lst.addItem(it)
        self._actualizar_contador()

    def _filtrar(self, t: str):
        if len(t) < 2 and t != "":
            return
        self._refrescar(t)

    def _sel_todos(self):
        for i in range(self.lst.count()):
            self.lst.item(i).setSelected(True)

    def _actualizar_contador(self):
        n = len(self.lst.selectedItems())
        self.lbl_count.setText(f"{n} seleccionado(s)  ·  total visible: {self.lst.count()}")

    def _elegir_dest(self):
        d = QFileDialog.getExistingDirectory(
            self, "Carpeta destino para los .db",
            str(self._dir_dest.parent if self._dir_dest else Path.home()),
        )
        if d:
            self._dir_dest = Path(d)
            self.lbl_dest.setText(d)

    def selection(self) -> tuple[list[str], Optional[Path]]:
        cods = [it.data(Qt.UserRole) for it in self.lst.selectedItems()]
        return cods, self._dir_dest


class _PaginaConversion(_Pagina):
    """Progreso de conversión (no es interactiva)."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addLayout(self._titulo(
            "Convirtiendo…",
            "Estamos generando los archivos .db. No cierres la ventana."
        ))

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # indeterminado
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background:{SILVER_200}; border:none; border-radius:4px; }}"
            f"QProgressBar::chunk {{ background:{ORANGE}; border-radius:4px; }}"
        )
        v.addWidget(self.bar)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(f"color:{SLATE_700}; font-size:12px; background:transparent;")
        v.addWidget(self.lbl_estado)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            f"QTextEdit {{ background:{SILVER_100}; color:{SLATE_500};"
            f" border:1px solid {SILVER_300}; border-radius:6px;"
            f" padding:8px; font-family:monospace; font-size:11px; }}"
        )
        v.addWidget(self.log, 1)

    def reset(self):
        self.log.clear()
        self.lbl_estado.setText("Iniciando…")

    def linea(self, texto: str):
        self.lbl_estado.setText(texto)
        self.log.append(texto)


class _PaginaResultado(_Pagina):
    """Lista de archivos generados + 'Abrir carpeta' + 'Convertir otro'."""

    pedir_otro = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addLayout(self._titulo(
            "Conversión completa ✓",
            "Tus archivos .db están listos. Abrilos desde IngePresupuestos → "
            "Importar → Base nativa (.db)."
        ))

        self.lst = QListWidget()
        self.lst.setStyleSheet(
            f"QListWidget {{ background:{SILVER_100}; color:{SLATE_700};"
            f" border:1px solid {SILVER_300}; border-radius:6px;"
            f" padding:4px; font-size:12px; }}"
        )
        v.addWidget(self.lst, 1)

        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setStyleSheet(f"color:{SLATE_500}; font-size:12px;")
        v.addWidget(self.lbl_resumen)

        h = QHBoxLayout()
        self.btn_abrir = QPushButton("Abrir carpeta")
        self.btn_abrir.setStyleSheet(_btn_secondary())
        self.btn_abrir.clicked.connect(self._abrir_carpeta)
        h.addWidget(self.btn_abrir)
        h.addStretch(1)
        self.btn_otro = QPushButton("Convertir otro archivo")
        self.btn_otro.setStyleSheet(_btn_secondary())
        self.btn_otro.clicked.connect(self.pedir_otro.emit)
        h.addWidget(self.btn_otro)
        v.addLayout(h)

        self._dir: Optional[Path] = None

    def mostrar(self, paths: list[Path], resumen: str):
        self.lst.clear()
        for p in paths:
            it = QListWidgetItem(f"   {p.name}    ({p.stat().st_size:,} bytes)")
            self.lst.addItem(it)
        self.lbl_resumen.setText(resumen)
        self._dir = paths[0].parent if paths else None
        self.btn_abrir.setEnabled(self._dir is not None)

    def _abrir_carpeta(self):
        if self._dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._dir)))


# ── Helper: card "1 — Paso" usado en la página de intro ──────────────────────
def _card_paso(n: str, titulo: str, sub: str) -> QFrame:
    card = QFrame()
    card.setAttribute(Qt.WA_StyledBackground, True)
    card.setStyleSheet(
        f"QFrame {{ background:{SILVER_100}; border:none; border-radius:8px; }}"
    )
    h = QHBoxLayout(card)
    h.setContentsMargins(14, 10, 14, 10)
    h.setSpacing(14)

    bola = QLabel(n)
    f = QFont(); f.setPointSize(15); f.setBold(True); bola.setFont(f)
    bola.setFixedSize(36, 36)
    bola.setAlignment(Qt.AlignCenter)
    bola.setStyleSheet(
        f"color:white; background:{ORANGE}; border:none; border-radius:18px;"
    )
    h.addWidget(bola)

    col = QVBoxLayout(); col.setSpacing(2)
    lbl_t = QLabel(titulo)
    ft = QFont(); ft.setBold(True); lbl_t.setFont(ft)
    lbl_t.setStyleSheet(f"color:{SLATE_700}; background:transparent;")
    col.addWidget(lbl_t)
    lbl_s = QLabel(sub)
    lbl_s.setWordWrap(True)
    lbl_s.setStyleSheet(f"color:{SLATE_500}; font-size:11px; background:transparent;")
    col.addWidget(lbl_s)
    h.addLayout(col, 1)

    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return card


# ═════════════════════════════════════════════════════════════════════════════
# Wizard principal
# ═════════════════════════════════════════════════════════════════════════════

# Índices de página (legibilidad)
P_INTRO, P_BACKEND, P_ARCHIVO, P_SELECCION, P_CONVERSION, P_RESULTADO = range(6)


class WizardPrincipal(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("IngeConverter — Migración de S10 a IngePresupuestos")
        self.setMinimumSize(820, 600)
        self.setStyleSheet(f"QWidget {{ background:{WHITE}; color:{SLATE_700}; }}")

        self._worker: Optional[QThread] = None
        self._build()

    # ── construcción ─────────────────────────────────────────────────────────

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 24, 30, 18)
        v.setSpacing(14)

        # Header
        h = QHBoxLayout()
        ttl = QLabel("IngeConverter")
        f = QFont(); f.setPointSize(20); f.setWeight(QFont.DemiBold)
        ttl.setFont(f)
        ttl.setStyleSheet(f"color:{SLATE_700}; background:transparent;")
        h.addWidget(ttl)
        h.addStretch(1)
        ver = QLabel("v0.1.0")
        ver.setStyleSheet(f"color:{SLATE_300}; font-size:11px; background:transparent;")
        h.addWidget(ver, alignment=Qt.AlignBottom)
        v.addLayout(h)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{SILVER_300}; background:{SILVER_300};")
        sep.setFixedHeight(1)
        v.addWidget(sep)

        # Stack de páginas
        self.stack = QStackedWidget()
        self.p_intro = _PaginaIntro()
        self.p_backend = _PaginaBackend()
        self.p_archivo = _PaginaArchivo()
        self.p_seleccion = _PaginaSeleccion()
        self.p_conversion = _PaginaConversion()
        self.p_resultado = _PaginaResultado()
        for w in (self.p_intro, self.p_backend, self.p_archivo,
                  self.p_seleccion, self.p_conversion, self.p_resultado):
            self.stack.addWidget(w)
        v.addWidget(self.stack, 1)

        # Footer: botones Atrás / Siguiente
        h_btn = QHBoxLayout()
        self.btn_back = QPushButton("Atrás")
        self.btn_back.setStyleSheet(_btn_secondary())
        self.btn_back.clicked.connect(self._on_back)
        h_btn.addWidget(self.btn_back)
        h_btn.addStretch(1)
        self.btn_next = QPushButton("Comenzar")
        self.btn_next.setStyleSheet(_btn_primary())
        self.btn_next.clicked.connect(self._on_next)
        h_btn.addWidget(self.btn_next)
        v.addLayout(h_btn)

        # Wiring de señales entre páginas
        self.p_backend.listo.connect(self._on_backend_listo)
        self.p_backend.pedir_reintentar.connect(self.p_backend.iniciar)
        self.p_archivo.archivo_listo.connect(self._on_archivo_listo)
        self.p_resultado.pedir_otro.connect(self._reiniciar)

        self._ir(P_INTRO)

    # ── navegación ───────────────────────────────────────────────────────────

    def _ir(self, idx: int):
        self.stack.setCurrentIndex(idx)
        # Estado de botones por página
        self.btn_back.setEnabled(idx not in (P_INTRO, P_CONVERSION))
        if idx == P_INTRO:
            self.btn_next.setText("Comenzar"); self.btn_next.setEnabled(True)
        elif idx == P_BACKEND:
            self.btn_next.setText("Continuar"); self.btn_next.setEnabled(False)
            self.p_backend.iniciar()
        elif idx == P_ARCHIVO:
            self.btn_next.setText("Listar presupuestos")
            self.btn_next.setEnabled(self.p_archivo.archivo() is not None)
        elif idx == P_SELECCION:
            self.btn_next.setText("Convertir"); self.btn_next.setEnabled(True)
        elif idx == P_CONVERSION:
            self.btn_next.setText("Convirtiendo…"); self.btn_next.setEnabled(False)
        elif idx == P_RESULTADO:
            self.btn_next.setText("Cerrar"); self.btn_next.setEnabled(True)

    def _on_back(self):
        idx = self.stack.currentIndex()
        if idx == P_RESULTADO:
            self._reiniciar()
            return
        if idx > 0:
            self._ir(idx - 1)

    def _on_next(self):
        idx = self.stack.currentIndex()
        if idx == P_INTRO:
            self._ir(P_BACKEND)
        elif idx == P_BACKEND:
            self._ir(P_ARCHIVO)
        elif idx == P_ARCHIVO:
            self._iniciar_listar()
        elif idx == P_SELECCION:
            self._iniciar_convertir()
        elif idx == P_RESULTADO:
            self.close()

    # ── handlers de cada paso ────────────────────────────────────────────────

    def _on_backend_listo(self, _nombre: str):
        # Habilitar "Continuar" cuando el backend está OK
        if self.stack.currentIndex() == P_BACKEND:
            self.btn_next.setEnabled(True)

    def _on_archivo_listo(self, _p: Path):
        if self.stack.currentIndex() == P_ARCHIVO:
            self.btn_next.setEnabled(True)

    def _iniciar_listar(self):
        archivo = self.p_archivo.archivo()
        if not archivo:
            return
        self._ir(P_CONVERSION)  # reusamos la página de progreso para el listado
        self.p_conversion.reset()
        self.p_conversion.lbl_estado.setText("Restaurando backup y listando presupuestos…")
        self._worker = _ListarWorker(archivo, self)
        self._worker.progreso.connect(self.p_conversion.linea)
        self._worker.finished_list.connect(self._on_listado_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_listado_ok(self, presupuestos: list):
        self._worker = None
        if not presupuestos:
            QMessageBox.warning(self, "Sin presupuestos",
                                "El backup no contiene presupuestos reconocibles.")
            self._ir(P_ARCHIVO)
            return
        self.p_seleccion.cargar(presupuestos, self.p_archivo.archivo())
        self._ir(P_SELECCION)

    def _iniciar_convertir(self):
        cods, dir_dest = self.p_seleccion.selection()
        if not cods:
            QMessageBox.information(self, "Falta selección",
                                    "Elegí al menos un presupuesto.")
            return
        if dir_dest is None:
            QMessageBox.information(self, "Falta carpeta",
                                    "Elegí una carpeta destino.")
            return
        self._ir(P_CONVERSION)
        self.p_conversion.reset()
        self._worker = _ConvertirWorker(
            self.p_archivo.archivo(), cods, dir_dest, self,
        )
        self._worker.progreso.connect(self.p_conversion.linea)
        self._worker.finished_ok.connect(self._on_convertir_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_convertir_ok(self, paths: list, resumen: str):
        self._worker = None
        self.p_resultado.mostrar(paths, resumen)
        self._ir(P_RESULTADO)

    def _on_fail(self, mensaje: str):
        self._worker = None
        QMessageBox.critical(self, "Error en la conversión", mensaje)
        # Volver al paso de archivo para reintentar
        self._ir(P_ARCHIVO)

    def _reiniciar(self):
        """Volver al estado inicial para convertir otro archivo."""
        self._ir(P_INTRO)
