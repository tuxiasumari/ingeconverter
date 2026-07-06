# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari / Sumari SAC
# This file is part of IngeConverter — complemento libre de IngePresupuestos.
# Licensed under the GNU GPL v3.0 or later. See the LICENSE file.
"""Orquestador: conecta a S10 (SQL Server) y genera el .db de IngePresupuestos.

Uso CLI — modo producción (usuario final): el backend gestiona SQL Server
solo (Docker en Linux/Mac, LocalDB en Windows).
    python -m core.convertir \\
        --archivo "samples/S10 PATAPUJO JUL.S2K" \\
        --todos --out salida_dir/

Uso CLI — modo dev (BD ya restaurada manualmente): conexión directa.
    python -m core.convertir \\
        --server localhost --user sa --password 'IngeConv2026!' \\
        --database S10_test \\
        --presupuesto 0201001 \\
        --out salida.db

Si `--subpresupuesto` se omite, convierte TODOS los subpresupuestos del
presupuesto en un solo .db (cada uno como un `sub_presupuesto` en IngePresupuestos).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .backend import (
    BackendError, BackupVersionTooOld, SQLServerBackend, crear_backend,
)
from .s10_reader import (
    S10Reader, NodoArbol, ACUItem, TIPO_RECURSO_MAP, TIPO_TITULO,
)
from .sqlite_writer import SQLiteWriter


log = logging.getLogger("ingeconverter")


# ─────────────────────────────────────────────────────────────────────────────
# Connection (pymssql)
# ─────────────────────────────────────────────────────────────────────────────

def conectar_sql(server: str, port: int, database: str, user: str, password: str):
    """Abre conexión a SQL Server vía pymssql. Lanza ImportError si pymssql
    no está instalado."""
    import pymssql
    return pymssql.connect(
        server=server, port=port,
        user=user, password=password,
        database=database,
        as_dict=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Conversión de un subpresupuesto
# ─────────────────────────────────────────────────────────────────────────────

def convertir_subpresupuesto(
    reader: S10Reader,
    writer: SQLiteWriter,
    proyecto_id: int,
    cod_presupuesto: str,
    cod_subpresupuesto: str,
    nombre_sub: str,
    *,
    orden: int,
    recurso_id_por_codigo: dict[str, int],
    precios_particulares: dict[str, float],
    es_principal: bool = False,
) -> dict:
    """Convierte un subpresupuesto completo a SQLite.

    Args:
        recurso_id_por_codigo: cache compartido entre subpresupuestos —
            permite reusar `recursos` ya creados (si el mismo insumo aparece
            en varios subpresupuestos, NO se duplica).
        es_principal: si True, las partidas van al tab "Principal" de
            IngePresupuestos (sub_presupuesto_id=NULL en lugar de un sub_id real).

    Returns:
        Stats dict: {partidas, titulos, acu_items}
    """
    log.info(f"  Convirtiendo subpresupuesto {cod_subpresupuesto} ({nombre_sub})"
             + (" [principal]" if es_principal else ""))

    # 1. Crear sub_presupuesto en SQLite (salvo el principal — ese vive como tab
    #    'Principal' sintético de IngePresupuestos con sub_presupuesto_id=NULL)
    sub_id = None if es_principal else writer.create_sub_presupuesto(
        proyecto_id, nombre_sub, orden=orden,
    )

    # 2. Leer árbol (títulos + partidas)
    arbol = reader.leer_arbol(cod_presupuesto, cod_subpresupuesto)
    log.info(f"     Árbol: {len(arbol)} nodos")

    # 3. Leer todos los ACU items del subpresupuesto y agruparlos por partida
    acu_items = reader.leer_acu_items(cod_presupuesto, cod_subpresupuesto)
    acus_por_partida: dict[tuple[str, str], list[ACUItem]] = {}
    for item in acu_items:
        key = (item.cod_partida, item.propio_partida)
        acus_por_partida.setdefault(key, []).append(item)
    log.info(f"     ACU items: {len(acu_items)}")

    # 4. Identificar insumos referenciados y cargar de catálogo
    cods_insumo = {item.cod_insumo for item in acu_items}
    insumos = reader.leer_insumos(cods_insumo)
    log.info(f"     Insumos en catálogo: {len(insumos)} de {len(cods_insumo)} referenciados")

    # 5. Crear recursos en SQLite (solo los que faltan)
    for cod_insumo in cods_insumo:
        if cod_insumo in recurso_id_por_codigo:
            continue
        ins = insumos.get(cod_insumo)
        # Determinar tipo a partir del primer ACUItem que lo usa
        primer_uso = next((a for a in acu_items if a.cod_insumo == cod_insumo), None)
        tipo_int = primer_uso.tipo if primer_uso else 2
        tipo_str = TIPO_RECURSO_MAP.get(tipo_int, 'MAT')
        descripcion = ins.descripcion if ins else f"Insumo {cod_insumo}"
        unidad = ins.cod_unidad if ins else (primer_uso.unidad if primer_uso else '')
        # Recursos porcentuales (%MO, %MAT...) no tienen precio unitario real:
        # S10 guarda en Precio1 el total MO/MAT de UNA partida específica (no
        # un precio universal). IngePresupuestos recalcula el "precio" en
        # runtime contra el total de la partida, así que dejar 0.
        es_porcentual = unidad.startswith('%')
        if es_porcentual:
            precio = 0.0
        else:
            precio = precios_particulares.get(cod_insumo) or (
                primer_uso.precio if primer_uso else 0.0
            )
        indice_inei = ins.cod_indice_unificado if ins else ''

        rid = writer.create_recurso(
            codigo=cod_insumo,
            descripcion=descripcion,
            tipo=tipo_str,
            unidad=unidad,
            precio=precio,
            indice_inei=indice_inei,
        )
        recurso_id_por_codigo[cod_insumo] = rid

    # 6. Crear partidas/títulos en SQLite, en orden del árbol
    partida_id_por_codigo: dict[tuple[str, str], int] = {}
    stats = {'partidas': 0, 'titulos': 0, 'acu_items': 0}

    for nodo in arbol:
        # Calcular nivel a partir del orden ("01.02.03" → nivel 3)
        nivel = len([p for p in nodo.orden.split('.') if p.strip()])

        # Rendimiento real (Partida.RendimientoMO) — unidades/día.
        # Para títulos usamos 1.0 (no aplica).
        rendimiento = nodo.rendimiento_mo if not nodo.es_titulo else 1.0

        partida_id = writer.create_partida(
            proyecto_id,
            sub_id,
            item=nodo.orden,
            descripcion=nodo.descripcion,
            unidad=nodo.unidad or '',
            metrado=nodo.metrado,
            precio_unitario=nodo.precio_unitario,
            nivel=nivel,
            es_titulo=nodo.es_titulo,
            rendimiento=rendimiento,
        )

        if nodo.es_titulo:
            stats['titulos'] += 1
        else:
            stats['partidas'] += 1
            # Crear ACU items de esta partida
            key = (nodo.cod_partida or '', nodo.propio_partida)
            jornada = nodo.jornada or 8.0
            for ai in acus_por_partida.get(key, []):
                rid = recurso_id_por_codigo.get(ai.cod_insumo)
                if rid is None:
                    log.warning(f"     ⚠ ACU item ignorado — recurso no creado: {ai.cod_insumo}")
                    continue
                # Cuadrilla: S10 no la guarda directo en PresupuestoPartidaAnalisis.
                # Despejada de la fórmula: cantidad_MO = (cuadrilla/rendimiento) × jornada
                # → cuadrilla = (cantidad × rendimiento) / jornada
                # Solo aplica a MO (Tipo=1); otros tipos quedan en 0.
                cuadrilla = 0.0
                if ai.tipo == 1 and rendimiento > 0 and jornada > 0:
                    cuadrilla = round((ai.cantidad * rendimiento) / jornada, 4)
                # Recursos porcentuales (HERRAMIENTAS MANUALES con %MO, etc.):
                # S10 almacena la cantidad como FRACCIÓN (0.03 = 3%) y multiplica
                # ×100 al renderear. IngePresupuestos espera el porcentaje entero
                # (3.0) porque internamente hace `cantidad / 100 * base_MO`.
                # Sin esta corrección, el parcial sale 100× menor.
                cantidad = ai.cantidad
                precio_acu = ai.precio
                if (ai.unidad or '').startswith('%'):
                    cantidad = ai.cantidad * 100.0
                    precio_acu = None  # IngePresupuestos lo recalcula en runtime
                writer.create_acu_item(
                    partida_id, rid,
                    cuadrilla=cuadrilla,
                    cantidad=cantidad,
                    precio=precio_acu,
                )
                stats['acu_items'] += 1

    log.info(f"     OK: {stats['titulos']} titulos, {stats['partidas']} partidas, "
             f"{stats['acu_items']} ACU items")
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Conversión completa (todos los subpresupuestos)
# ─────────────────────────────────────────────────────────────────────────────

def convertir_proyecto(
    reader: S10Reader,
    writer: SQLiteWriter,
    cod_presupuesto: str,
    cod_subpresupuesto: Optional[str] = None,
) -> dict:
    """Convierte un presupuesto entero (todos los subpresupuestos) o uno solo
    si se especifica `cod_subpresupuesto`."""

    # 1. Info general del proyecto
    proyecto = reader.leer_proyecto(cod_presupuesto)
    log.info(f"Proyecto: {proyecto.nombre} ({proyecto.cod_presupuesto})")

    # 2. Subpresupuestos
    subs = reader.listar_subpresupuestos(cod_presupuesto)
    if cod_subpresupuesto:
        subs = [s for s in subs if s.cod_subpresupuesto == cod_subpresupuesto]
        if not subs:
            raise ValueError(
                f"Subpresupuesto {cod_subpresupuesto} no existe en {cod_presupuesto}"
            )
    # Filtrar el subpresupuesto "999 COMODIN" (es un placeholder de S10 sin partidas reales)
    subs = [s for s in subs if s.cod_subpresupuesto != '999']
    log.info(f"Subpresupuestos a convertir: {len(subs)}")

    # 3. Crear proyecto en SQLite
    # El nombre del primer subpresupuesto va a `proyectos.sub_presupuesto` (TEXT
    # legacy) — IngePresupuestos siempre crea un tab "Principal" sintético con
    # ese nombre, antes de los sub_presupuestos reales. Si no lo seteamos, queda
    # vacío y confunde al usuario.
    nombre_principal = subs[0].descripcion if subs else 'Principal'
    proyecto_id = writer.create_proyecto(
        nombre=proyecto.nombre,
        ubicacion=proyecto.ubicacion,
        plazo=proyecto.plazo,
        gf_pct=proyecto.gf_pct_fijo + proyecto.gf_pct_variable,
        utilidad_pct=proyecto.utilidad_pct,
        igv_pct=proyecto.igv_pct,
        moneda=proyecto.moneda,
        sub_presupuesto=nombre_principal,
        fecha_inicio=(
            proyecto.fecha_inicio.strftime('%Y-%m-%d')
            if proyecto.fecha_inicio else ''
        ),
        notas=f"Migrado desde S10 — CodPresupuesto={proyecto.cod_presupuesto}",
    )

    # 4. Pie de presupuesto base (rubros típicos)
    if proyecto.gf_pct_fijo > 0 or proyecto.gf_pct_variable > 0:
        writer.create_pie_rubro(
            proyecto_id, codigo='GG', nombre='Gastos generales',
            pct=proyecto.gf_pct_fijo + proyecto.gf_pct_variable,
            orden=1, activo=True,
        )
    if proyecto.utilidad_pct > 0:
        writer.create_pie_rubro(
            proyecto_id, codigo='UT', nombre='Utilidad',
            pct=proyecto.utilidad_pct, orden=2, activo=True,
        )
    writer.create_pie_rubro(
        proyecto_id, codigo='IGV', nombre='IGV',
        pct=proyecto.igv_pct or 18.0, orden=3, activo=True,
    )

    # 5. Cargar catálogo INEI primero
    inei = reader.leer_indices_inei()
    for codigo, nombre in inei:
        writer.create_indice_inei(codigo, nombre)
    log.info(f"Índices INEI cargados: {len(inei)}")

    # 6. Precios particulares del proyecto (overrides)
    precios_particulares = reader.leer_precios_particulares(cod_presupuesto)
    log.info(f"Precios particulares: {len(precios_particulares)}")

    # 7. Convertir cada subpresupuesto.
    # El PRIMERO va al tab "Principal" de IngePresupuestos (sub_presupuesto_id=NULL).
    # Los demás como sub_presupuestos reales.
    recurso_id_por_codigo: dict[str, int] = {}
    stats_total = {'partidas': 0, 'titulos': 0, 'acu_items': 0}
    for idx, sub in enumerate(subs):
        es_principal = (idx == 0)
        stats_sub = convertir_subpresupuesto(
            reader, writer, proyecto_id,
            cod_presupuesto, sub.cod_subpresupuesto,
            sub.descripcion,
            orden=idx,
            recurso_id_por_codigo=recurso_id_por_codigo,
            precios_particulares=precios_particulares,
            es_principal=es_principal,
        )
        for k in stats_total:
            stats_total[k] += stats_sub[k]

    stats_total['recursos'] = len(recurso_id_por_codigo)
    stats_total['subpresupuestos'] = len(subs)
    return stats_total


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte una BD de S10 a archivo .db de IngePresupuestos"
    )
    parser.add_argument('--archivo', default=None,
                        help='Ruta a un .S2K/.bak/.bkf. Si se pasa, el backend '
                             '(Docker en Linux/Mac, LocalDB en Windows) lo restaura '
                             'automáticamente. Reemplaza a --server/--database.')
    parser.add_argument('--server',      default='localhost', help='[modo dev] Host SQL Server')
    parser.add_argument('--port',        default=1433, type=int)
    parser.add_argument('--user',        default='sa')
    parser.add_argument('--password',    default=None,
                        help='[modo dev] Password SA (requerido si no se usa --archivo)')
    parser.add_argument('--database',    default=None,
                        help='[modo dev] Nombre de la BD ya restaurada (requerido si no se usa --archivo)')
    parser.add_argument('--presupuesto', default=None,
                        help='CodPresupuesto a convertir (ej. 0201001). Omitir si --todos.')
    parser.add_argument('--subpresupuesto', default=None,
                        help='CodSubpresupuesto específico (omitir = todos)')
    parser.add_argument('--todos', action='store_true',
                        help='Convertir TODOS los presupuestos disponibles de la BD. '
                             '`--out` se interpreta como directorio destino.')
    parser.add_argument('--out', default='salida.db',
                        help='Archivo .db destino (o directorio si --todos)')
    parser.add_argument('--verbose', '-v', action='count', default=0)
    parser.add_argument('--listar', action='store_true',
                        help='Solo listar presupuestos disponibles y salir')
    parser.add_argument('--json', action='store_true',
                        help='Con --listar: emite JSON estructurado a stdout '
                             '(para parsing desde subprocesos, ej. IngePresupuestos)')
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose >= 2 else (
            logging.INFO if args.verbose >= 1 else logging.WARNING
        ),
        format='%(message)s',
    )

    # Validar modos mutuamente excluyentes
    if not args.archivo and not (args.database and args.password):
        print("ERROR: se requiere --archivo (modo producción) o "
              "--database + --password (modo dev).", file=sys.stderr)
        return 1

    backend: Optional[SQLServerBackend] = None
    if args.archivo:
        # Modo producción: backend gestiona SQL Server automáticamente.
        # Mensajes informativos a stderr para no contaminar stdout (que es
        # JSON cuando se invoca con --listar --json desde un subprocess).
        backend = crear_backend()
        print(f"Backend: {type(backend).__name__}", file=sys.stderr)
        try:
            backend.preparar()
        except BackendError as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            return 1

        archivo = Path(args.archivo)
        print(f"Restaurando {archivo.name}...", file=sys.stderr)
        try:
            db_name = backend.restaurar(archivo)
        except BackupVersionTooOld as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            return 2
        except BackendError as e:
            print(f"\nERROR al restaurar: {e}", file=sys.stderr)
            return 1

        try:
            conn = backend.conectar(database=db_name)
        except Exception as e:
            print(f"ERROR conectando a la BD restaurada: {e}", file=sys.stderr)
            backend.limpiar()
            return 1
    else:
        # Modo dev: conexión directa a una BD ya restaurada
        log.info(f"Conectando a {args.server}:{args.port} / {args.database}...")
        try:
            conn = conectar_sql(
                args.server, args.port, args.database, args.user, args.password,
            )
        except ImportError:
            print("ERROR: pymssql no instalado. Instalá con: pip install pymssql",
                  file=sys.stderr)
            return 1
        except Exception as e:
            print(f"ERROR conectando a SQL Server: {e}", file=sys.stderr)
            return 1

    reader = S10Reader(conn)
    try:
        return _ejecutar_conversion(args, reader)
    finally:
        if backend is not None:
            backend.limpiar()


def _ejecutar_conversion(args, reader: S10Reader) -> int:
    """Lógica de --listar / --todos / --presupuesto. Separada de main() para
    que el limpiado del backend (finally) sea simétrico."""
    if args.listar:
        presupuestos = reader.listar_presupuestos()
        if args.json:
            import json as _json
            _json.dump(
                [{'cod': cod, 'descripcion': desc} for cod, desc in presupuestos],
                sys.stdout, ensure_ascii=False,
            )
            sys.stdout.write('\n')
        else:
            print("Presupuestos disponibles:")
            for cod, desc in presupuestos:
                print(f"  {cod}  {desc}")
        return 0

    if args.todos:
        # Convertir todos los presupuestos de la BD en archivos separados
        import re as _re
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        if out_dir.is_file():
            print(f"ERROR: --todos requiere un DIRECTORIO en --out (no archivo): {out_dir}",
                  file=sys.stderr)
            return 1

        todos = reader.listar_presupuestos()
        print(f"Convirtiendo {len(todos)} presupuestos a {out_dir}/")
        resumen = []
        for cod, desc in todos:
            # Filename seguro: solo alfanuméricos + guión + descripción truncada
            safe = _re.sub(r'[^\w\-]+', '_', desc[:60]).strip('_')
            filename = out_dir / f"{cod}_{safe}.db"
            print(f"\n► [{cod}] {desc[:80]}")
            try:
                with SQLiteWriter(str(filename), fresh=True) as writer:
                    stats = convertir_proyecto(reader, writer, cod, None)
                resumen.append((cod, desc, filename, stats))
            except Exception as e:
                print(f"   [X] Error: {e}", file=sys.stderr)
                resumen.append((cod, desc, None, None))

        print(f"\n{'=' * 70}\nRESUMEN\n{'=' * 70}")
        for cod, desc, fname, stats in resumen:
            if stats is None:
                print(f"  [X] {cod}  {desc[:60]} - FALLO")
            else:
                print(f"  [OK] {cod}  ({stats['subpresupuestos']} sub, "
                      f"{stats['titulos']+stats['partidas']} partidas, "
                      f"{stats['acu_items']} acu) -> {fname.name}")
        return 0

    if not args.presupuesto:
        print("ERROR: se requiere --presupuesto (o --todos para convertir todos)",
              file=sys.stderr)
        return 1

    log.info(f"Generando {args.out}...")
    with SQLiteWriter(args.out, fresh=True) as writer:
        stats = convertir_proyecto(
            reader, writer,
            args.presupuesto, args.subpresupuesto,
        )

    print(f"\n[OK] Conversion completa: {args.out}")
    print(f"  Subpresupuestos: {stats['subpresupuestos']}")
    print(f"  Títulos        : {stats['titulos']}")
    print(f"  Partidas       : {stats['partidas']}")
    print(f"  ACU items      : {stats['acu_items']}")
    print(f"  Recursos       : {stats['recursos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
