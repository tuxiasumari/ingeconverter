# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari / Sumari SAC
# This file is part of IngeConverter — complemento libre de IngePresupuestos.
# Licensed under the GNU GPL v3.0 or later. See the LICENSE file.
"""Writer del archivo SQLite destino con schema de IngePresupuestos.

Genera un archivo `.db` que IngePresupuestos puede abrir directamente vía
`Importar > Archivo .db` (gestionado por `core/ingepresupuestos_db_importer.py`
del proyecto principal, que usa ATTACH DATABASE).

**Diseño**:
- API: clase `SQLiteWriter` que gestiona conexión + ids retornados al cliente.
- Es agnóstico del origen (S10, Delphin, PowerCost). Cualquier reader puede
  usarlo si traduce sus datos a las funciones `create_*` del writer.
- Schema se replica desde `~/ingepresupuestos-pyside6/core/database.py`. Si el
  schema target cambia, hay que sincronizar acá manualmente (es duplicación
  intencional, no se importa cross-projects para evitar acople fuerte).

**Schema sincronizado al**: 2026-05-22 (commit c115f98 de ingepresupuestos-pyside6).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Schema (copia textual de core/database.py de IngePresupuestos, sincronizado)
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    cliente TEXT DEFAULT '',
    ubicacion TEXT DEFAULT '',
    sub_presupuesto TEXT DEFAULT '',
    costo_al TEXT DEFAULT '',
    plazo INTEGER DEFAULT 60,
    gf_pct REAL DEFAULT 10.0,
    utilidad_pct REAL DEFAULT 5.0,
    igv_pct REAL DEFAULT 18.0,
    grupo_analisis TEXT DEFAULT '',
    jornada_laboral REAL DEFAULT 8.0,
    moneda TEXT DEFAULT 'Soles',
    modalidad TEXT DEFAULT 'Contrata',
    estado TEXT DEFAULT 'elaboracion',
    fecha_inicio TEXT DEFAULT '',
    feriados TEXT DEFAULT '',
    salta_no_laborables INTEGER DEFAULT 1,
    notas TEXT DEFAULT '',
    favorito INTEGER DEFAULT 0,
    usuario_id INTEGER,
    portafolio_id INTEGER,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sub_presupuestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    orden INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS partidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    sub_presupuesto_id INTEGER REFERENCES sub_presupuestos(id) ON DELETE SET NULL,
    item TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    unidad TEXT DEFAULT '',
    metrado REAL DEFAULT 0,
    precio_unitario REAL DEFAULT 0,
    nivel INTEGER DEFAULT 1,
    es_titulo INTEGER DEFAULT 0,
    especificaciones TEXT DEFAULT '',
    rendimiento REAL DEFAULT 1,
    grupo TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS recursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT DEFAULT '',
    descripcion TEXT NOT NULL,
    tipo TEXT NOT NULL,
    unidad TEXT DEFAULT '',
    precio REAL DEFAULT 0,
    indice_inei TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS acu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partida_id INTEGER NOT NULL REFERENCES partidas(id) ON DELETE CASCADE,
    recurso_id INTEGER NOT NULL REFERENCES recursos(id),
    cuadrilla REAL DEFAULT 0,
    cantidad REAL DEFAULT 0,
    precio REAL
);
CREATE TABLE IF NOT EXISTS pie_rubros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    pct REAL DEFAULT 0,
    activo INTEGER DEFAULT 1,
    orden INTEGER DEFAULT 0,
    tipo TEXT DEFAULT 'rubro',
    mostrar_pct INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS indices_inei (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    activo INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS indices_inei_areas (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    orden INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS indices_inei_valores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    area TEXT DEFAULT '01',
    valor REAL NOT NULL,
    UNIQUE(codigo, anio, mes, area)
);
CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS portafolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#667885',
    descripcion TEXT DEFAULT '',
    orden INTEGER DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS biblioteca_cu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL,
    unidad TEXT DEFAULT '',
    rendimiento REAL DEFAULT 1.0,
    costo_unitario REAL DEFAULT 0,
    grupo TEXT DEFAULT '',
    especificaciones TEXT DEFAULT '',
    usos INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS biblioteca_acu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cu_id INTEGER NOT NULL REFERENCES biblioteca_cu(id) ON DELETE CASCADE,
    recurso_id INTEGER NOT NULL REFERENCES recursos(id) ON DELETE CASCADE,
    cuadrilla REAL DEFAULT 0,
    cantidad REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pie_presupuesto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    rol TEXT NOT NULL,
    nombre TEXT DEFAULT '',
    cargo TEXT DEFAULT '',
    cip TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS metrados_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partida_id INTEGER NOT NULL REFERENCES partidas(id) ON DELETE CASCADE,
    orden INTEGER DEFAULT 0,
    descripcion TEXT DEFAULT '',
    n_estructuras REAL,
    n_elementos REAL,
    largo REAL,
    ancho REAL,
    alto REAL,
    area REAL,
    parcial REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cronograma_partidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partida_id INTEGER NOT NULL REFERENCES partidas(id) ON DELETE CASCADE UNIQUE,
    duracion INTEGER DEFAULT 1,
    inicio_dia INTEGER DEFAULT 1,
    predecesoras TEXT DEFAULT '',
    es_hito INTEGER DEFAULT 0,
    segmentos TEXT DEFAULT '',
    color TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS spec_imagenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partida_id INTEGER NOT NULL REFERENCES partidas(id) ON DELETE CASCADE,
    orden INTEGER DEFAULT 0,
    filename TEXT NOT NULL,
    caption TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS gastos_generales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    rubro TEXT DEFAULT 'GG',
    tipo TEXT DEFAULT 'item',
    descripcion TEXT DEFAULT '',
    unidad TEXT DEFAULT 'MES',
    n_personas REAL DEFAULT 1,
    tiempo REAL DEFAULT 1,
    pct_participacion REAL DEFAULT 100,
    precio REAL DEFAULT 0,
    orden INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS formula_monomios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    orden INTEGER DEFAULT 0,
    simbolo TEXT DEFAULT 'A',
    descripcion TEXT DEFAULT '',
    indice_inei TEXT DEFAULT '',
    coeficiente REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS formula_periodos (
    proyecto_id INTEGER PRIMARY KEY REFERENCES proyectos(id) ON DELETE CASCADE,
    oferta_anio INTEGER,
    oferta_mes INTEGER,
    reajuste_anio INTEGER,
    reajuste_mes INTEGER,
    area_inei TEXT DEFAULT '01'
);
CREATE TABLE IF NOT EXISTS acero_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partida_id INTEGER NOT NULL REFERENCES partidas(id) ON DELETE CASCADE,
    orden INTEGER DEFAULT 0,
    descripcion TEXT DEFAULT '',
    diametro TEXT DEFAULT '',
    n_veces REAL,
    n_estructuras REAL,
    n_elementos REAL,
    longitud REAL,
    kg_ml REAL,
    parcial REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tuxia_memos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    texto TEXT NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tuxia_memoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    texto TEXT NOT NULL DEFAULT '',
    fecha_modif TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    username TEXT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    rol TEXT DEFAULT 'usuario',
    activo INTEGER DEFAULT 1,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_partidas_proyecto ON partidas(proyecto_id)",
    "CREATE INDEX IF NOT EXISTS idx_partidas_sub      ON partidas(sub_presupuesto_id)",
    "CREATE INDEX IF NOT EXISTS idx_acu_items_partida ON acu_items(partida_id)",
    "CREATE INDEX IF NOT EXISTS idx_acu_items_recurso ON acu_items(recurso_id)",
    "CREATE INDEX IF NOT EXISTS idx_pie_proyecto      ON pie_rubros(proyecto_id)",
    "CREATE INDEX IF NOT EXISTS idx_subppto_proyecto  ON sub_presupuestos(proyecto_id)",
    "CREATE INDEX IF NOT EXISTS idx_recursos_codigo   ON recursos(codigo)",
    "CREATE INDEX IF NOT EXISTS idx_recursos_inei     ON recursos(indice_inei)",
]


# ─────────────────────────────────────────────────────────────────────────────
# Writer
# ─────────────────────────────────────────────────────────────────────────────

class SQLiteWriter:
    """Gestiona la generación del archivo `.db` destino.

    Uso típico:
        with SQLiteWriter("salida.db") as w:
            pid = w.create_proyecto(nombre="...", ...)
            sid = w.create_sub_presupuesto(pid, "ACTIVIDAD 1", orden=1)
            rid = w.create_recurso(codigo="01010001", descripcion="...", tipo="MO", ...)
            partida_id = w.create_partida(pid, sid, item="01.02", descripcion="...", ...)
            w.create_acu_item(partida_id, rid, cuadrilla=1.0, cantidad=0.16)
        # __exit__ hace commit + close
    """

    def __init__(self, path: str | Path, *, fresh: bool = True):
        self.path = Path(path)
        if fresh and self.path.exists():
            self.path.unlink()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA_DDL)
        for idx in _INDICES:
            self.conn.execute(idx)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        self.conn.close()
        return False

    def close(self):
        self.conn.commit()
        self.conn.close()

    # ── Proyecto ─────────────────────────────────────────────────────────────

    def create_proyecto(
        self,
        *,
        nombre: str,
        cliente: str = "",
        ubicacion: str = "",
        sub_presupuesto: str = "",
        plazo: int = 60,
        gf_pct: float = 10.0,
        utilidad_pct: float = 5.0,
        igv_pct: float = 18.0,
        jornada_laboral: float = 8.0,
        moneda: str = "Soles",
        modalidad: str = "Contrata",
        fecha_inicio: str = "",
        notas: str = "",
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO proyectos
               (nombre, cliente, ubicacion, sub_presupuesto, plazo, gf_pct,
                utilidad_pct, igv_pct, jornada_laboral, moneda, modalidad,
                fecha_inicio, notas)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (nombre, cliente, ubicacion, sub_presupuesto, plazo, gf_pct,
             utilidad_pct, igv_pct, jornada_laboral, moneda, modalidad,
             fecha_inicio, notas),
        )
        return cur.lastrowid

    # ── Sub-presupuesto ──────────────────────────────────────────────────────

    def create_sub_presupuesto(
        self, proyecto_id: int, nombre: str, *, orden: int = 0
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO sub_presupuestos (proyecto_id, nombre, orden) VALUES (?,?,?)",
            (proyecto_id, nombre, orden),
        )
        return cur.lastrowid

    # ── Recurso ──────────────────────────────────────────────────────────────

    def create_recurso(
        self,
        *,
        codigo: str,
        descripcion: str,
        tipo: str,          # 'MO' | 'MAT' | 'EQ' | 'SC'
        unidad: str = "",
        precio: float = 0.0,
        indice_inei: str = "",
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO recursos
               (codigo, descripcion, tipo, unidad, precio, indice_inei)
               VALUES (?,?,?,?,?,?)""",
            (codigo, descripcion, tipo, unidad, precio, indice_inei),
        )
        return cur.lastrowid

    # ── Partida (título o partida hoja) ──────────────────────────────────────

    def create_partida(
        self,
        proyecto_id: int,
        sub_presupuesto_id: Optional[int],
        *,
        item: str,
        descripcion: str,
        unidad: str = "",
        metrado: float = 0.0,
        precio_unitario: float = 0.0,
        nivel: int = 1,
        es_titulo: bool = False,
        rendimiento: float = 1.0,
        especificaciones: str = "",
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO partidas
               (proyecto_id, sub_presupuesto_id, item, descripcion, unidad,
                metrado, precio_unitario, nivel, es_titulo, rendimiento,
                especificaciones)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (proyecto_id, sub_presupuesto_id, item, descripcion, unidad,
             metrado, precio_unitario, nivel, int(es_titulo), rendimiento,
             especificaciones),
        )
        return cur.lastrowid

    # ── ACU item ─────────────────────────────────────────────────────────────

    def create_acu_item(
        self,
        partida_id: int,
        recurso_id: int,
        *,
        cuadrilla: float = 0.0,
        cantidad: float = 0.0,
        precio: Optional[float] = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO acu_items
               (partida_id, recurso_id, cuadrilla, cantidad, precio)
               VALUES (?,?,?,?,?)""",
            (partida_id, recurso_id, cuadrilla, cantidad, precio),
        )
        return cur.lastrowid

    # ── Pie de presupuesto (rubros: GG, Utilidad, IGV, etc.) ─────────────────

    def create_pie_rubro(
        self,
        proyecto_id: int,
        *,
        codigo: str,
        nombre: str,
        pct: float,
        orden: int = 0,
        activo: bool = True,
        tipo: str = "rubro",
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO pie_rubros
               (proyecto_id, codigo, nombre, pct, activo, orden, tipo)
               VALUES (?,?,?,?,?,?,?)""",
            (proyecto_id, codigo, nombre, pct, int(activo), orden, tipo),
        )
        return cur.lastrowid

    # ── Índice INEI ──────────────────────────────────────────────────────────

    def create_indice_inei(self, codigo: str, nombre: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO indices_inei (codigo, nombre) VALUES (?,?)",
            (codigo, nombre),
        )

    # ── Stats ────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Retorna conteos por tabla — útil para logging del fin de conversión."""
        return {
            tabla: self.conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            for tabla in (
                "proyectos", "sub_presupuestos", "partidas", "recursos",
                "acu_items", "pie_rubros", "indices_inei",
            )
        }
