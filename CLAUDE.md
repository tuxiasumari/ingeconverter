# IngeConverter — Convertidor S10 → IngePresupuestos

Complemento de **IngePresupuestos** (`~/ingepresupuestos-pyside6/`). Convierte
bases de datos nativas de S10 (`.S2K`, `.bak`, `.bkf`) a archivos `.db` SQLite
con el schema de IngePresupuestos.

**Autor:** Ing. Marco Sumari Tellez
**Iniciado:** 2026-05-22
**Estado:** Fase 0 completada — funcional contra `.S2K` reales (samples LLAMKASUN
y PATAPUJO). Próxima sesión: empaquetar para distribución (Fase 2).

---

## Estado funcional (2026-05-22 — Fase 0 ✅)

- 3 módulos completos en `core/`: `s10_reader.py` + `sqlite_writer.py` + `convertir.py`
- CLI con flags `--listar`, `--presupuesto`, `--subpresupuesto`, `--todos`, `--out`
- **9 `.db` reales generados** desde 2 samples y validados visualmente por Marco
  en IngePresupuestos:
  - `samples/llamkasun_AII.db` — LLAMKASUN AII (3 subs, 1028 partidas)
  - `samples/patapujo_todos/*.db` — 8 proyectos del .S2K PATAPUJO (Tacna)
- Validación 1:1 contra S10: los `CostoDirectoOferta1` por subpresupuesto
  coinciden EXACTOS al centavo
- 9 bugs encontrados y resueltos (ver sección abajo)
- Container Docker SQL Server 2022 sigue corriendo: `docker ps` → `mssql-s10`
  con 2 BDs restauradas (`S10_test` = LLAMKASUN, `s10_patapujo` = PATAPUJO)

---

## Arquitectura decidida — Plan A (complemento separado)

Decisión confirmada por Marco el 2026-05-22 tras evaluar opciones:

- **IngeConverter es producto separado**, NO se integra dentro de IngePresupuestos
- Se distribuye como **complemento descargable** desde IngePresupuestos
- **Multiplataforma** mediante backends distintos por OS:

| Plataforma | Backend SQL Server | Tamaño total al usuario |
|---|---|---|
| Windows | LocalDB (Microsoft, instalación nativa) | ~340 MB (todo bundleado en MSI) |
| Linux | Docker + `mssql-server` oficial | ~150 MB instalador + 2.3 GB descarga on-demand de imagen Docker |
| macOS | Docker Desktop + `mssql-server` | ~200 MB instalador + 2.3 GB on-demand |

### Flujo UX previsto

1. Usuario en IngePresupuestos → Archivo → Importar → ".S2K / .bak (S10)"
2. Si IngeConverter NO está instalado → diálogo "Descargar complemento (340 MB Win / 150 MB Linux)"
3. Si lo descarga → IngePresupuestos lo invoca como subproceso pasándole el archivo S10
4. IngeConverter genera un `.db` temporal → IngePresupuestos lo importa con `core/ingepresupuestos_db_importer.py` (que ya existe)

### Visibilidad y distribución — cerrado 2026-05-22

- **Repo privado** en `github.com/tuxiasumari/ingeconverter` (NO público).
- **Código cerrado** — el reverse-engineering del schema S10 (9 bugs + queries
  específicas + CASE de PropioPartida + cálculo de cuadrilla + fix #9 de %MO)
  es el activo competitivo. Si PowerCost/Delphin lo ven, copian la feature
  en su producto y desaparece la ventaja única.
- **Distribución solo del binario** (PyInstaller-empaquetado), no del código
  fuente. EULA del binario debería prohibir reverse-engineering (pendiente
  redactar al empaquetar).
- **Caveat técnico**: PyInstaller no es invencible — `pyinstxtractor` +
  `uncompyle6` pueden recuperar el bytecode. Si en el futuro la protección
  importa más, considerar Cython compilation del core (`s10_reader.py` +
  `sqlite_writer.py` + `convertir.py` → `.so`/`.pyd` binarios C reales).

### Modelo comercial — cerrado 2026-05-22

**IngeConverter es complemento GRATIS, sin licencia, sin límites.** Su única
función es convertir S10 → `.db` de IngePresupuestos. **NO** exporta a otros
formatos.

Razones (Marco, 2026-05-22):
- Forzar el funnel hacia IngePresupuestos. Quien viene de S10 solo tiene un
  camino gratis: migrar a IngePresupuestos.
- Si IngeConverter exportara a `.prs` (PowerCost) o `.sqlite` (Delphin) abrirías
  una válvula de escape hacia competidores.
- El gating monetario sigue siendo IngePresupuestos perpetua (Excel/Word/ODS/MPP).

**Decisiones derivadas:**
- ❌ NO implementar exporters `.prs` / `.sqlite` aunque sea técnicamente posible
- ❌ NO implementar sistema de licencias en IngeConverter
- ❌ NO meter UI de gating ni botones "Comprar"
- ✅ Wizard standalone simplificado (solo .db destino)
- ✅ El binario se distribuye sin contrato comercial — pura herramienta gancho

---

## Hallazgos críticos del schema de S10 (no obvios — LEER antes de tocar el reader)

### 1. `.S2K` ≡ `.bkf` ≡ `.bak`
Todos son backups MTF / NTBackup con SQL Server backup adentro. Diferencia: solo
el nombre. SQL Server 2022 los lee igual vía `RESTORE FROM DISK`. NO se necesita
`mtftar` ni nada externo. La extensión `.S2K` es solo rebrand que S10 le puso
a un .bkf estándar.

### 2. Versión mínima soportada: SQL Server 2005 (versión interna 611)
Backups más antiguos (SQL 7.0/2000, versión 515-539) NO se restauran en SQL
Server 2022. Requerirían cascada via SQL 2008 R2 que **no existe como imagen
Docker Linux oficial de Microsoft**. Marco recibió un sample (LOSA SAN MARCOS,
versión 515) que quedó fuera de alcance. Documentar como limitación al usuario.

### 3. Modelo de datos central
```
Presupuesto (jerárquico por longitud — '02', '0201', '0201001')
  └── Subpresupuesto (CodPresupuesto + CodSubpresupuesto, ej. '001', '003', '004')
        └── SubpresupuestoDetalle ← TABLA DEL ÁRBOL (Item, Orden, Tipo, Metrado, Precio1)
              ├── Tipo=5 → título → catálogo Titulo (descripción)
              └── Tipo=1 → partida → catálogo Partida (RendimientoMO, Jornada, descripción)
                    └── PresupuestoPartidaAnalisis ← ACU items
                          └── Insumo (CodInsumo, CodIndiceUnificado, CodUnidad)
                                └── PrecioParticularInsumo (overrides por proyecto)
```

**NO confundir** `Presupuesto` (tabla con la jerarquía real) con `Proyecto`
(catálogo separado, sin relación directa con presupuestos reales).

### 4. Wildcards de catálogo (filtrar SIEMPRE)
- `Partida.CodPartida = '999999999999'` con `Descripcion='REGISTRO RESTRINGIDO'`
- `Titulo.CodTitulo = '9999999'` con misma descripción
- `Insumo.CodInsumo = '9999999999'` (subpartida)

Los JOINs deben excluirlos: `AND code NOT LIKE '999%%'`.

### 5. PropioPartida: '99' vs '01'/'02'
- `PropioPartida='99'` = catálogo general, vive en `CodPresupuesto='9999999'`
- `PropioPartida='01'`/`'02'` = propias del proyecto, vive en `CodPresupuesto`
  del proyecto real
- El JOIN con `Partida` requiere:
  ```sql
  AND p.CodPresupuesto = CASE
      WHEN sd.PropioPartida = '99' THEN '9999999'
      ELSE sd.CodPresupuesto
  END
  ```
- Sin este CASE: o duplicación masiva (5-8x) en partidas propias, o pérdida
  total de descripciones en partidas del catálogo general

### 6. IngePresupuestos siempre crea un tab "Principal"
Ver `views/proyecto_view.py::_cargar_sub_pptos`. Si TODOS los subppto de S10 van
como sub_presupuestos reales, el tab Principal queda vacío y confunde.
**Fix**: el PRIMER subppto S10 va al Principal:
- `partidas.sub_presupuesto_id = NULL` para esas partidas
- `proyectos.sub_presupuesto = <nombre_del_primer_subppto>` (campo TEXT legacy)
- Los demás subppto se crean como `sub_presupuestos` reales (tabs adicionales)

### 7. Convención INEI peruana para tipos de recurso (100% consistente en S10)
- `01XXXX` = MO (Mano de Obra)
- `02XXXX` = MAT (Materiales)
- `03XXXX` = EQ (Equipos)
- `04XXXX` = SC (Subcontratos)
- `99XXXXX` = wildcard / subpartida

El `Tipo` en `PresupuestoPartidaAnalisis` es estable por recurso — no varía
entre usos. Mi código usa el Tipo del primer ACU item; está bien.

### 8. Cuadrilla NO se almacena en S10 — se infiere
S10 calcula `cantidad_HH = (cuadrilla × Jornada) / RendimientoMO`. Despejada:
`cuadrilla = (cantidad × RendimientoMO) / Jornada`. Datos en `Partida`:
- `RendimientoMO` (unidades/día)
- `Jornada` (horas/día, típicamente 8)

Solo aplica a Tipo=1 (MO); otros tipos quedan en cuadrilla=0 (correcto).

### 9. Ubicación = CodLugar (INEI ubigeo Perú)
`Presupuesto.CodLugar` es jerárquico:
- 2 caracteres = departamento ('15' = Lima, '23' = Tacna)
- 4 caracteres = provincia
- 6 caracteres = distrito

Resolver con 3 JOINs a `UbicacionGeografica` por nivel + dedup conservando
orden estándar peruano (depto → prov → distrito). Resultado: "Tacna" en lugar
de "230101", o "Lima, Jesús María" en lugar de "150113".

### 10. `Partida` tiene `CodPresupuesto` propio (clave de discriminación)
La tabla `Partida` guarda UNA fila por cada `CodPresupuesto` que usa la
partida propia. Si una partida propia es usada en 8 presupuestos, hay 8 filas
con el mismo `(CodPartida, PropioPartida)`. El JOIN debe incluir
`p.CodPresupuesto = sd.CodPresupuesto` para evitar producto cartesiano.

### 11. Insumos porcentuales (`%MO`, `%MAT`) — doble convención
Recursos como HERRAMIENTAS MANUALES (`Unidad='%MO'`) representan overhead
sobre el total MO/MAT de la partida. **S10 e IngePresupuestos almacenan el
porcentaje con escalas distintas**:

- **S10**: `PresupuestoPartidaAnalisis.Cantidad = 0.03` (fracción decimal); el
  reporte multiplica ×100 al renderear ("3.0000 %MO"). El `Precio1` guardado
  es el total MO de UNA partida específica — NO un precio universal del
  recurso, varía por fila.
- **IngePresupuestos**: `acu_items.cantidad = 3.0` (porcentaje entero); el
  cálculo interno hace `cantidad / 100 × total_MO_partida`. El `precio` se
  recalcula en runtime, NO se almacena.

Por lo tanto, al convertir:
- `acu_items.cantidad = s10.Cantidad × 100` cuando la unidad empieza con `%`
- `acu_items.precio = NULL` (IngePresupuestos lo recalcula)
- `recursos.precio = 0` para insumos porcentuales (no hay precio unitario real)

Sin esta corrección el parcial sale 100× menor (0.14 en vez de 14.26).

---

## Bugs encontrados y resueltos en Fase 0

(Todos en `docs/ROADMAP.md` con detalle técnico)

1. **mtftar no necesario** → SQL Server 2022 lee el .bkf nativo vía `RESTORE FROM DISK`
2. **Wildcards 999 contaminan títulos** ("REGISTRO RESTRINGIDO") → agregar `NOT LIKE '999%'`
3. **Partidas duplicadas 5-8x** en proyectos con `PropioPartida='01'` → JOIN con `CodPresupuesto`
4. **Partidas catálogo general (99) sin descripción** → `CASE WHEN ... THEN '9999999' ELSE sd.CodPresupuesto END`
5. **Tab "Principal" vacío** en IngePresupuestos → primer subppto va a `sub_presupuesto_id=NULL`
6. **Ubicación crudo INEI** → JOIN con `UbicacionGeografica`, 3 niveles + dedup
7. **Cuadrilla siempre 0 en MO** → `cuadrilla = (cantidad × RendimientoMO) / Jornada`
8. **Tipos sesgados (1 MO)** → resultó NO ser bug, era el sample S10 vetusto
9. **Insumos `%MO` con parcial 100× menor** → S10 guarda cantidad como fracción
   (0.03), IngePresupuestos espera porcentaje entero (3.0). Fix: multiplicar
   ×100 al exportar cuando `unidad LIKE '%...'`, dejar `acu_items.precio=NULL`
   y `recursos.precio=0`. Detalle en sección "Schema #11" arriba.

---

## Setup de desarrollo (Linux con Docker)

```bash
# 1. Levantar SQL Server 2022 — imagen oficial Microsoft (2.3 GB, una vez)
docker run -d --name mssql-s10 \
  -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=IngeConv2026!" -e "MSSQL_PID=Developer" \
  -p 1433:1433 \
  -v "/home/sumaritux/Descargas/ACU_PARTIDAS_AII:/samples:ro" \
  -v "mssql-s10-data:/var/opt/mssql" \
  mcr.microsoft.com/mssql/server:2022-latest

# 2. Restaurar .S2K (mismo comando para .bkf o .bak)
docker exec mssql-s10 /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P 'IngeConv2026!' -C -Q \
  "RESTORE DATABASE s10_db FROM DISK = '/samples/archivo.S2K'
   WITH MOVE 'S10_Data' TO '/var/opt/mssql/data/s10_db.mdf',
        MOVE 'S10_Datos' TO '/var/opt/mssql/data/s10_db.ndf',
        MOVE 'S10_Log' TO '/var/opt/mssql/data/s10_db.ldf',
        REPLACE"

# 3. Setup venv
cd ~/ingeconverter
python3 -m venv venv
venv/bin/pip install -r requirements.txt   # pymssql, PySide6

# 4. Listar presupuestos
venv/bin/python -m core.convertir \
  --server localhost --user sa --password 'IngeConv2026!' \
  --database s10_db --listar

# 5. Convertir uno
venv/bin/python -m core.convertir \
  --server localhost --user sa --password 'IngeConv2026!' \
  --database s10_db --presupuesto <COD> --out salida.db

# 6. Convertir todos los presupuestos de la BD
venv/bin/python -m core.convertir … --todos --out dir_destino/
```

### Comandos para los samples actuales

```bash
# LLAMKASUN
venv/bin/python -m core.convertir \
  --server localhost --user sa --password 'IngeConv2026!' \
  --database S10_test --presupuesto 0201001 \
  --out samples/llamkasun_AII.db

# Todos los 8 de PATAPUJO
venv/bin/python -m core.convertir \
  --server localhost --user sa --password 'IngeConv2026!' \
  --database s10_patapujo --todos \
  --out samples/patapujo_todos
```

### Si el container está apagado:
```bash
docker start mssql-s10   # los datos persisten en el volumen mssql-s10-data
```

---

## Estructura del proyecto

```
~/ingeconverter/
├── main.py                          # Entry point (UI wizard — esqueleto, falta lógica)
├── requirements.txt                 # PySide6, pymssql
├── README.md                        # Descripción público-facing
├── CLAUDE.md                        # ← este archivo
├── .gitignore                       # samples/ y venv/ excluidos
├── core/
│   ├── __init__.py
│   ├── s10_reader.py                # ✅ lee SQL Server + queries S10
│   ├── sqlite_writer.py             # ✅ genera .db con schema IngePresupuestos
│   └── convertir.py                 # ✅ orquestador + CLI
├── views/
│   ├── __init__.py
│   └── wizard.py                    # 🚧 UI placeholder (3 cards de pasos)
├── resources/icons/                 # (vacío — pendiente iconografía)
├── docs/
│   ├── ROADMAP.md                   # ✅ Fase 0→3 + bugs resueltos
│   └── s10_schema_notes.md          # ✅ documentación completa del schema
└── samples/
    ├── ACU_PARTIDAS_AII/            # source .bkf de LLAMKASUN
    ├── llamkasun_AII.db             # ✅ .db generado de LLAMKASUN
    ├── LOSA SAN MARCOS AGOSTO.S2K   # ⚠ SQL 7.0, fuera de alcance
    ├── S10 PATAPUJO JUL.S2K         # source de los 8 PATAPUJO
    ├── patapujo_todos/
    │   ├── 0501039_*.db             # ✅ 8 .db generados
    │   ├── 0501040_*.db
    │   ├── 0501041_*.db (Represa Yarabamba — el más grande)
    │   ├── 0501042_*.db
    │   ├── 0501043_*.db
    │   ├── 0501044_*.db
    │   ├── 0501045_*.db
    │   └── 0501048_*.db (Patapujo KM 24+640 — el validado por Marco)
    └── captura.png                  # screenshot de la UI con bug ya resuelto
```

---

## Próximos pasos (Fase 2 — Empaquetado)

Pendiente para la próxima sesión:

### 1. Abstracción de backend SQL Server ✅ (2026-05-22)

Hecho — `core/backend.py` con interface `SQLServerBackend` y dos impls:

- `DockerBackend` (Linux/Mac) — **funcional end-to-end**:
  - Gestiona container `ingeconv-mssql` con volumen `ingeconv-mssql-data`
  - Auto-pull de imagen + `docker run` la primera vez; `docker start` después
  - `docker cp` del .S2K (NO usa bind mount → portable)
  - `RESTORE FILELISTONLY` para leer nombres lógicos dinámicamente (no
    hardcoded, así soporta backups con nombres distintos a `S10_Data`)
  - `RESTORE DATABASE ... WITH REPLACE` a la BD `s10_conv`
  - `limpiar()` hace `DROP DATABASE` pero deja el container vivo (reuso)
  - Detecta SQL Server <2005 → lanza `BackupVersionTooOld` user-facing

- `LocalDBBackend` (Windows) — **esqueleto**:
  - `esta_disponible()` detecta `SqlLocalDB.exe`
  - `restaurar/conectar` lanzan `NotImplementedError`
  - Pendiente: requiere `pyodbc` + driver ODBC nativo Windows (pymssql no
    habla bien con LocalDB named pipes). Implementar al portar a Win.

- Factory `crear_backend()` despacha según `sys.platform`.

CLI nuevo modo producción:
```bash
venv/bin/python -m core.convertir \
  --archivo "samples/S10 PATAPUJO JUL.S2K" \
  --presupuesto 0501048 --out salida.db
```

El modo dev (`--server --database --password`) sigue funcionando para
iteración rápida con BDs ya restauradas.

### 2. Integración con IngePresupuestos ✅ (2026-05-22)

Hecho — en `~/ingepresupuestos-pyside6/`:

- `core/ingeconverter_bridge.py` — cliente del CLI como subprocess. Detección
  por plataforma (`INGECONVERTER_BIN` env → bundled path → dev fallback al
  repo). Métodos `listar_presupuestos()` y `convertir()` con callback `on_log`
  para progreso line-by-line.
- `views/importar_view.py` — formato `s10_s2k` bajo programa "S10" como
  "Base nativa (.S2K)". Flujo en 2 workers:
  1. `_S10ListWorker`: levanta Docker/LocalDB y lista presupuestos (async)
  2. `_SelectPptoDialog` (reusado de .prs/.db, parametrizado con `origen_texto`):
     diálogo modal con búsqueda incremental + multi-selección + "Seleccionar todos"
  3. `_ImportWorker` con `cods_s10` filtrados → convierte + importa con
     `importar_proyecto_db_directo`
- Validado en UI real por Marco (8 PATAPUJO importados, ~3 min).

CLI nuevo en IngeConverter para el bridge: `--listar --json` emite array
estructurado a stdout para parsing desde subprocess.

### 3. UI del wizard standalone ✅ (2026-05-22)

Hecho — `views/wizard.py` con 6 páginas en QStackedWidget:
1. Intro (cards explicativos planos, sin borde)
2. Backend check (auto-prepare con worker async)
3. Elegir archivo (.S2K/.bak/.bkf)
4. Selección (multi-pick con búsqueda + elegir dir destino)
5. Conversión (progress bar + log de stderr)
6. Resultado (lista de .db generados + "Abrir carpeta")

Tres workers internos: `_PrepararWorker`, `_ListarWorker`, `_ConvertirWorker`.
Paleta replicada de IngePresupuestos para consistencia visual.

### 4. Empaquetado Linux ✅ (2026-05-22)

PyInstaller onefile + windowed:
```bash
venv/bin/pyinstaller ingeconverter.spec --noconfirm
```

Genera `dist/ingeconverter` (~72 MB) como binario standalone que **NO**
requiere Python ni venv en la máquina destino. Probado lanzando desde shell
limpia (`env -u VIRTUAL_ENV -u PYTHONPATH PATH=/usr/bin:/bin ...`) — wizard
abre y flujo completo funciona.

`ingeconverter.spec` versionado; `build/` y `dist/` en .gitignore.

Pendiente: AppImage (envoltorio para distribución Linux estándar), o tarball
con README. Decidir al subir a `downloads.ingepresupuestos.com/`.

### 5. Pendientes para llegar a v1.0

- **AppImage** (envoltorio Linux estándar) o tarball con README. Decidir al
  subir el binario a `downloads.ingepresupuestos.com/ingeconverter/v0.1.0/linux/`.
- **`LocalDBBackend` Windows real** (no solo esqueleto): requiere `pyodbc` +
  driver ODBC nativo. No probable en Linux sin Wine/VM.
- **Empaquetado Windows**: Inno Setup con LocalDB MSI bundleado (~340 MB).
- **Iconografía**: el ícono de la ventana es el genérico de Qt. Crear/encargar
  un .ico (Windows) + .png/.svg (Linux/Mac).
- **EULA** corto que prohíba reverse-engineering (3-5 líneas).
- **Subir el binario** a R2 y conectar la URL real al `IngeConverterBridge`
  de IngePresupuestos (hoy es placeholder).

### 6. Limitaciones conocidas a comunicar al usuario
- SQL 7.0/2000 (versión <611) no se puede migrar directo. El backend ya lanza
  `BackupVersionTooOld` con mensaje user-facing.
- El primer uso descarga ~2.3 GB en Linux/Mac (imagen Docker SQL Server).
  Comunicar al usuario antes de empezar.

---

## Decisiones arquitectónicas a no revertir sin alinear con Marco

1. **Plan A** (complemento separado descargable). NO integrar el código dentro
   de IngePresupuestos como `core/s10_import/`. Si IngeConverter se rompe por
   un cambio de S10, IngePresupuestos sigue funcionando.

2. **pymssql** en vez de `pyodbc`. Wheel binario puro Python, sin drivers ODBC
   extras. Placeholders `%s`, no `?`. Funciona idéntico Linux/Windows.

3. **Output `.db` SQLite con schema completo de IngePresupuestos** (no solo las
   tablas con datos). El importer espera ~25 tablas — algunas pueden estar
   vacías pero todas deben existir. Si no, falla con "no such table: portafolios".

4. **Schema target sincronizado manualmente** desde `~/ingepresupuestos-pyside6/
   core/database.py`. Si ese schema cambia (nuevos `ALTER TABLE ... ADD COLUMN`),
   sincronizar acá. Hay un comentario al inicio de `core/sqlite_writer.py` con
   la fecha de sincronización.

5. **El PRIMER subpresupuesto S10 va al "Principal"** de IngePresupuestos (con
   `sub_presupuesto_id=NULL`). NO crear sub_presupuestos para TODOS los subppto
   de S10.

---

## Memoria relacionada (IngePresupuestos)

- `[[project_modelo_comercial]]` — pricing IngePresupuestos (USD 30/150)
- `[[project_licencia_premium]]` — sistema técnico de licencias
- `[[reference_importadores_nativos]]` — estado de importadores existentes
- `[[project_visibilidad_repo]]` — decisión pendiente sobre repo público/privado
