# IngeConverter — Roadmap

## Fase 0 — Servicio manual (HOY · 2026-05-22) ✅ COMPLETADA

- [x] Setup SQL Server 2022 en Docker (Linux) — Microsoft oficial, gratis Developer Edition
- [x] Restaurar el `.bkf` de `~/Descargas/ACU_PARTIDAS_AII/` directamente (sin mtftar)
- [x] Listar tablas del schema → 199 tablas, mapeo en `docs/s10_schema_notes.md`
- [x] Identificar tablas clave: `Presupuesto`, `Subpresupuesto`, `SubpresupuestoDetalle`,
      `PresupuestoPartidaAnalisis`, `Insumo`, `PrecioParticularInsumo`, `IndiceUnificado`,
      `Unidad`, `Titulo`, `Partida`
- [x] Primer script de conversión completo: `core/s10_reader.py` + `core/sqlite_writer.py`
      + `core/convertir.py` (CLI orquestador)
- [x] **Validación 1:1 con S10**: los 3 subtotales (CONSOLIDADO $60,455.78,
      ACTIVIDAD 1 $87,474.96, ACTIVIDAD 2 $86,228.55) coinciden EXACTOS con
      `Subpresupuesto.CostoDirectoOferta1`
- [ ] Le devuelve al amigo el `.db` listo para abrir en IngePresupuestos
      (esperando que Marco abra `samples/llamkasun_AII.db` en IngePresupuestos
      para confirmar UX final)

### Cosas menores observadas (mejorables en Fase 1)

- [x] ~~`proyectos.ubicacion` guardaba código INEI ubigeo en vez del nombre.~~
      Fixed 2026-05-22: JOIN con `UbicacionGeografica` resolviendo los 3 niveles
      (depto, provincia, distrito) con dedup conservando orden estándar peruano.
      Resultado: "Lima, Jesús María" o "Tacna" en lugar de "150113"/"230101".
- [x] ~~Algunos títulos top-level salen con descripción 'REGISTRO RESTRINGIDO'~~
      Fixed 2026-05-22: `Partida.CodPartida='999999999999'` es un wildcard de S10
      con descripcion 'REGISTRO RESTRINGIDO'. Los títulos usan ese código como
      placeholder en `SubpresupuestoDetalle.CodPartida` y el JOIN matcheaba la
      fila wildcard. Fix: agregar `AND sd.Tipo=N AND code NOT LIKE '999%'` a los
      JOIN-ON de `Partida` y `Titulo`.

- [x] ~~Partidas del catálogo general (PropioPartida='99') sin descripción en proyectos con partidas propias~~
      Fixed 2026-05-22: el fix anterior (agregar `p.CodPresupuesto=sd.CodPresupuesto`)
      rompió las partidas del catálogo general porque ese catálogo usa
      `CodPresupuesto='9999999'`, no el del proyecto. Fix definitivo:
      `p.CodPresupuesto = CASE WHEN sd.PropioPartida='99' THEN '9999999' ELSE sd.CodPresupuesto END`.
      Detectado por Marco en LLAMKASUN CONSOLIDADO AII (680 de 903 partidas hoja
      quedaron sin descripción tras el fix anterior).

- [x] ~~El primer tab "Principal" aparece vacío al importar en IngePresupuestos~~
      Fixed 2026-05-22: IngePresupuestos siempre crea un tab sintético "Principal"
      con `sub_presupuesto_id IS NULL` ANTES de los sub_presupuestos reales (ver
      `views/proyecto_view.py::_cargar_sub_pptos`). Si todas las partidas tienen
      sub_presupuesto_id no-NULL, ese tab queda vacío y confunde al usuario.
      Fix en IngeConverter: el PRIMER subpresupuesto de S10 va al tab "Principal"
      (sub_presupuesto_id=NULL en partidas) y su nombre se guarda en
      `proyectos.sub_presupuesto` (campo TEXT legacy). Los demás subpresupuestos
      van como sub_presupuestos reales (tabs adicionales). Detectado por Marco.

- [x] ~~Partidas duplicadas (cada item aparece 5-8 veces) en proyectos con partidas propias~~
      Fixed 2026-05-22: La tabla `Partida` de S10 guarda **una fila por cada
      `CodPresupuesto` que usa la partida propia** (`PropioPartida='01'`). Si una
      partida propia es usada en 8 presupuestos, hay 8 filas con el mismo
      `(CodPartida, PropioPartida)` pero diferente `CodPresupuesto`. Mi JOIN
      original solo filtraba por las dos primeras columnas → producto cartesiano.
      Fix: agregar `AND p.CodPresupuesto = sd.CodPresupuesto` al JOIN.
      Detectado por Marco en el sample PATAPUJO (los totales eran 5x los reales).
      LLAMKASUN no estaba afectado porque sus partidas eran del catálogo general
      (`PropioPartida='99'`), no propias del proyecto.
- [x] ~~Distribución de tipos de recurso parecía sesgada (1 MO vs 649 MAT)~~
      Confirmado 2026-05-22: NO era bug. La convención INEI peruana es 100%
      consistente en S10 (`01XX`=MO, `02XX`=MAT, `03XX`=EQ, `04XX`=SC,
      `99XX`=wildcard). Mi código toma el `Tipo` del primer ACU item — correcto.
      El "1 MO" en LLAMKASUN era literal: ese sample S10 vetusto solo tenía un
      único recurso MO ("PARTICIPANTE"). PATAPUJO confirmó 5 MO correctos
      (CAPATAZ, OPERARIO, OFICIAL, PEON, TOPÓGRAFO).
- [x] ~~Cuadrilla siempre 0 en items MO.~~
      Fixed 2026-05-22: implementada `cuadrilla = (cantidad × RendimientoMO) / Jornada`.
      `RendimientoMO` y `Jornada` se traen de la tabla `Partida` vía JOIN en
      `leer_arbol`. NodoArbol expone `rendimiento_mo` y `jornada` que
      `convertir.py` usa para crear los ACU items MO con cuadrilla calculada.
      Solo aplica a Tipo=1 (MO); otros tipos quedan en 0 (correcto). Cobertura
      100% en samples: 892/892 ACU items MO en LLAMKASUN, 551/551 en PATAPUJO.
      Validado contra la partida 01.01.01 de PATAPUJO: CAPATAZ=0.1, OPERARIO=1.0,
      PEON=2.0 (cantidades 0.8/8/16 HH con Rend=1, Jornada=8).
- [ ] Pie de presupuesto: el sample tenía `PorcentajeGG=0`, por eso solo aparece
      IGV en el .db generado. Validar con otro sample que sí tenga GG/Utilidad.

## Fase 1 — Más casos reales (2-4 semanas)

- [ ] Conseguir samples de 3-5 amigos beta con sus bases S10 reales.
- [ ] Refinar el script ad-hoc con cada caso nuevo.
- [ ] Detectar variaciones de schema entre versiones de S10.
- [ ] Empezar a estructurar `core/s10_reader.py` y `core/sqlite_writer.py` como
      módulos reusables (no más scripts sueltos).
- [ ] Cobrar USD 30-50 por migración manual a los primeros clientes.

## Fase 2 — Producto bundleado (2-3 meses)

- [ ] UI wizard PySide6 (3 pasos: LocalDB → Archivo → Convertir).
- [ ] Detección automática de LocalDB + guía de instalación si falta.
- [ ] Manejo de errores user-friendly (versión incompatible, corrupción, etc.).
- [ ] Logging detallado para debugging remoto.
- [ ] Empaquetar con PyInstaller como `IngeConverter-setup.exe`.
- [ ] Integrarlo como upsell de la licencia perpetua de IngePresupuestos
      ("Perpetua + Migración" = USD 200 vs perpetua sola USD 150).

## Fase 3 — Mantenimiento (continuo)

- [ ] Soporte para nuevas versiones de S10 cuando aparezcan.
- [ ] Posibles otros importadores nativos (Delphin `.dprj` cerrado, otros softwares
      peruanos) bajo la misma arquitectura de producto satélite.

## Cosas a NO hacer (decisiones tomadas)

- ❌ **NO meter pyodbc/LocalDB en IngePresupuestos directo.** Romper la
  arquitectura de producto satélite es la mayor tentación; resistirla.
- ❌ **NO soportar Linux/Mac.** Microsoft SQL Server LocalDB no existe ahí, y los
  usuarios de S10 son 100% Windows. Cero ROI.
- ❌ **NO hacer ingeniería inversa del formato binario `.mdf`.** OrcaMDF demuestra
  que es posible pero requeriría meses, y solo funciona con versiones viejas. El
  camino LocalDB+ODBC es más sustentable.
- ❌ **NO prometer migración 100% completa.** Tiene que quedar claro al usuario
  que ciertas cosas pueden no transferirse (fórmulas custom, plantillas raras,
  configuración local de S10) y eso está OK.
