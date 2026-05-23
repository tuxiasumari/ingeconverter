# Schema de S10 — notas de reverse engineering

> Última actualización: **2026-05-22** — primer mapeo completo a partir del
> sample `~/Descargas/ACU_PARTIDAS_AII/ACU LLAMKASUN PERU AII`.

## Sample analizado

- **Archivo**: `ACU LLAMKASUN PERU AII` (86 MB, NTBackup .bkf con SQL Server backup adentro)
- **Origen Windows**: `C:\S102000\Data\` → S10 versión **2000** (clásico)
- **Versión SQL Server detectada**: muy vieja (~SQL 2000); SQL Server 2022 hizo
  upgrade automático al restaurar
- **Total filas (todas las tablas)**: ~46k
- **Filegroups**: PRIMARY + filegroup propio "DATOS" + LOG (formato dual típico
  de S10 para separar tablas críticas de catálogos)

## Procedimiento de restauración (Linux + Docker)

**No requiere extraer el .bak previamente.** SQL Server lee directamente el `.bkf`:

```bash
# 1. Container SQL Server con volumen al sample
docker run -d --name mssql-s10 \
  -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=IngeConv2026!" -e "MSSQL_PID=Developer" \
  -p 1433:1433 \
  -v "/home/sumaritux/Descargas/ACU_PARTIDAS_AII:/samples:ro" \
  -v "mssql-s10-data:/var/opt/mssql" \
  mcr.microsoft.com/mssql/server:2022-latest

# 2. Verificar archivos lógicos del backup
docker exec mssql-s10 /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P 'IngeConv2026!' -C -Q \
  "RESTORE FILELISTONLY FROM DISK = '/samples/ACU LLAMKASUN PERU AII'"

# 3. Restaurar
docker exec mssql-s10 /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P 'IngeConv2026!' -C -Q "
RESTORE DATABASE S10_test FROM DISK = '/samples/ACU LLAMKASUN PERU AII'
WITH
  MOVE 'S10_Data'  TO '/var/opt/mssql/data/S10_test.mdf',
  MOVE 'S10_Datos' TO '/var/opt/mssql/data/S10_test.ndf',
  MOVE 'S10_Log'   TO '/var/opt/mssql/data/S10_test.ldf',
  REPLACE"
```

`mtftar` NO se necesita — SQL Server lee MTF nativamente.

## Modelo de datos (mapa completo)

### Jerarquía conceptual

```
Proyecto (jerarquía por longitud de código)
  CodProyecto: "01" → "01001" → "01001000" → "01001001"
        │
        └── Subpresupuesto (CodPresupuesto + CodSubpresupuesto)
              CodPresupuesto: "0201001"
              CodSubpresupuesto: "001 CONSOLIDADO AII", "002 ACTIVIDAD 1", "999 COMODIN"
              │
              ├── PresupuestoTitulo (los títulos del árbol)
              │
              └── PresupuestoPartida (las partidas con metrado + precio)
                    │
                    └── PresupuestoPartidaAnalisis (ACU items)
                          │
                          └── Insumo (catálogo de recursos)
                                │
                                └── PrecioParticularInsumo (override de precio por proyecto)
```

### Tablas centrales (las que importan para migrar)

| Tabla S10 | Filas (sample) | Propósito | Mapeo IngePresupuestos |
|---|---|---|---|
| **Proyecto** | 13 | Árbol nested de proyectos por código jerárquico | `proyectos` (filtrar solo niveles hoja, ej. CodProyecto largo) |
| **Subpresupuesto** | 4 | Subdivisión del proyecto (ACTIVIDAD 1, ACTIVIDAD 2, etc.) | `sub_presupuestos` |
| **PresupuestoTitulo** + Detalle | 109 + 1474 | Títulos del árbol | `partidas` con `es_titulo=1` |
| **PresupuestoPartida** + Detalle | 906 + 3282 | Partidas con metrado y precio unitario | `partidas` con `es_titulo=0` |
| **PresupuestoPartidaAnalisis** | 3282 | ACU items (relación partida → insumo) | `acu_items` |
| **Insumo** | 935 | Catálogo de recursos (incluye jerarquía interna) | `recursos` |
| **PrecioParticularInsumo** | 804 | Override de precio del insumo en este proyecto | `acu_items.precio` (cuando difiere de `recursos.precio`) |
| **IndiceUnificado** | 76 | Índices INEI (oficiales de Perú) | `indices_inei` |
| **Unidad** | 82 | Catálogo de unidades de medida (incluye `%mo`, `%mt`, `%pu`, `%cd`) | `recursos.unidad` |
| **Partida** | 2498 | Catálogo general (biblioteca) — NO del proyecto | Opcional: cargar a `biblioteca_cu` |

### Tablas administrativas (probablemente NO migrar)

- Documento, TipoDocumentoSunat, GuiaAlmacenMovimiento → facturas/logística
- Usuario, Rol, Permiso, AccesoCatalogo → seguridad
- Pedido, PedidoEstado → orden de compra
- ConfiguracionCronograma → configuración de UI
- FormatoImpresion → plantillas de reporte (1.7 MB en 15 filas — binarios de Crystal Reports probablemente)
- ConfiguracionVsflex → 6983 filas — configuración de grids VSFlexGrid (componente VB6)

### Tablas auxiliares (catálogos de soporte)

- TipoCambio (305) — monedas y tipos de cambio histórico
- Escenario (320) — versiones del presupuesto (Base vs Oferta)
- AccesoCatalogo (506) — permisos por catálogo
- Tabla + AgrupacionTabla (584 + 406) — catálogos genéricos
- Syscatalogo (384) — meta-catálogo

## Patrones críticos del schema

### 1. PK compuestos por todos lados
S10 usa PKs compuestos con muchas columnas. Para `PresupuestoPartida`:
`(CodPresupuesto, CodSubpresupuesto, CodPartida, CodPresupuestoPartida)`. Hay
que respetar esto al hacer joins.

### 2. Sufijo "1" / "2" en columnas → dual escenario
Casi todas las columnas de precio/costo tienen versión `1` y `2`:
`Precio1`/`Precio2`, `ManoDeObra1`/`ManoDeObra2`, etc. Es para almacenar
**Base** (presupuesto referencial) y **Oferta** (propuesta). En el sample
los `*2` están casi todos en NULL/0 — solo se usó Base. Para migración: usar
`Precio1` y los `*1`, ignorar `*2`.

### 3. Códigos jerárquicos por longitud
Tanto `Proyecto.CodProyecto` como `Insumo.CodInsumo` usan **longitud de string
como nivel jerárquico**:
- `01` → nivel 1
- `0101` → nivel 2 (hijo del anterior)
- `010101` → nivel 3
- `0101010007` → nivel 4 (hoja)

Para reconstruir el árbol en IngePresupuestos: ordenar por longitud + ordenar
alfabético, y usar prefijo común para identificar padre.

### 4. Tipo de recurso codificado en `PresupuestoPartidaAnalisis.Tipo`
- `1` = Mano de Obra (MO)
- `2` = Materiales (MAT)
- `3` = Equipos (EQ) — pendiente confirmar
- `4` = Subcontratos (SC) — pendiente confirmar
- `5` = Subpartidas — pendiente confirmar

Mapeo a tu `tipo` actual: `MO/MAT/EQ/SC` directo.

### 5. Unidades "porcentaje" para overhead
S10 maneja overhead (%MO/%MAT/%EQ) como **insumos con unidad especial**:
- `%mo` (CodUnidad=006) = porcentaje de mano de obra
- `%mt` (CodUnidad=007) = porcentaje de materiales
- `%eq` (CodUnidad=003) = porcentaje de equipos
- `%pu` (CodUnidad=008) = porcentaje del precio unitario
- `%cd` (CodUnidad=002) = porcentaje del costo directo

Esto coincide EXACTO con como IngePresupuestos maneja overhead. Mapeo directo.

### 6. Decimales configurables por proyecto
`Proyecto.DecimalesPrecio`, `DecimalesCantidad`, `DecimalesParcial`,
`DecimalesFactorGlobal`. En este sample: precio=4, cantidad=4, parcial=2.
IngePresupuestos usa redondeos hardcoded — al migrar respetar los del proyecto
S10 (o normalizar a los de IngePresupuestos avisando al usuario).

### 7. Fechas "1899-12-30" = NULL
S10 usa `1899-12-30 00:00:00.000` como "fecha vacía" en vez de NULL.
Al migrar: convertir esos valores a NULL.

## Datos del proyecto sample

- **Proyecto**: "Vivienda Unifamiliar" en Av. San Borja Sur 754, San Borja, Lima
- **Ubicación INEI**: 150130 (Lima Metropolitana)
- **Plazo**: 90 días
- **Empresa origen**: S10 sample (`01001001`)
- **3 Subpresupuestos**: CONSOLIDADO AII, ACTIVIDAD 1, ACTIVIDAD 2 + COMODIN
- **Total** (CostoDirectoOferta1):
  - CONSOLIDADO: USD 60,455.78
  - ACTIVIDAD 1: USD 87,474.96
  - ACTIVIDAD 2: USD 86,228.55
- **906 partidas** en `PresupuestoPartida`, **3282 ACU items** en `PresupuestoPartidaAnalisis`

## Próximos pasos

- [x] Restaurar .bkf y listar tablas
- [x] Identificar tablas centrales
- [x] Mapear schema a IngePresupuestos
- [ ] Confirmar valores de `PresupuestoPartidaAnalisis.Tipo` (cuál es EQ vs SC)
- [ ] Inspeccionar `PresupuestoTitulo` con joins a `PresupuestoPartida` para
      reconstruir el árbol exacto del sample
- [ ] Mapear `Subpresupuesto.GastoGeneralFijo + GastoGeneralvariable + Utilidad + IGV`
      a `pie_rubros` de IngePresupuestos
- [ ] Verificar `PrecioParticularInsumo` — entender cuándo el precio del insumo
      varía del catálogo general
- [ ] Escribir primer script de conversión `core/s10_reader.py` + `core/sqlite_writer.py`
- [ ] Validar resultado contra el `.xls` exportado por el usuario (que debería
      coincidir 1:1 con las partidas migradas)

## Variaciones de schema entre versiones de S10

> Por descubrir conforme aparezcan diferentes samples. Este es S10 **2000**
> según el path `C:\S102000\Data\`. Versiones más nuevas (S10 2005, 2010, 2015,
> 2020, 2024) pueden tener:
> - Tablas adicionales (workflow, integraciones nuevas)
> - Columnas nuevas en tablas existentes
> - Renombrados (raros, S10 cuida compatibilidad)
> Estrategia: el reader debe usar `SELECT col1, col2, ...` con COALESCE y
> manejo gracefully de columnas faltantes.
