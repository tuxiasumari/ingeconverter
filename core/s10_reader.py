"""Reader del schema de S10 (Microsoft SQL Server).

Lee tablas críticas de una base de datos de S10 restaurada en SQL Server
(LocalDB en producción Windows, `mssql-server` en Docker para desarrollo Linux).

**Conexión**: usa `pymssql` (FreeTDS-based, wheel puro Python — sin drivers
nativos extra). Funciona idéntico en Linux/Windows. El caller construye y pasa
la conexión.

**Decisiones de mapeo (ver `docs/s10_schema_notes.md`)**:
- Solo Base (`*1`) — ignoramos Oferta (`*2`)
- `Tipo` de `PresupuestoPartidaAnalisis`: 1=MO · 2=MAT · 3=EQ · 4=SC · 5=Subpartida
- Fechas `1899-12-30` → None
- Códigos jerárquicos en `Orden` (no en `Item`, que es padding numérico interno)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Tipos
# ─────────────────────────────────────────────────────────────────────────────

#: Mapeo de S10 Tipo (int) a tipo de recurso de IngePresupuestos (str)
TIPO_RECURSO_MAP = {
    1: 'MO',   # Mano de Obra
    2: 'MAT',  # Materiales
    3: 'EQ',   # Equipos
    4: 'SC',   # Subcontratos
    5: 'MAT',  # Subpartidas → tratadas como MAT (no hay equivalente directo)
}

#: Tipo en SubpresupuestoDetalle: 1=partida hoja, 5=título
TIPO_TITULO = 5
TIPO_PARTIDA = 1

#: Fecha "vacía" de S10 (heredado de Visual Basic 6 / Delphi)
FECHA_VACIA_S10 = datetime(1899, 12, 30)


@dataclass
class ProyectoS10:
    """Snapshot de un proyecto S10 antes de mapear a IngePresupuestos."""
    cod_presupuesto: str        # Código del presupuesto (ej. '0201001')
    nombre: str
    cliente: str = ''
    ubicacion: str = ''
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    plazo: int = 60
    igv_pct: float = 18.0
    gf_pct_fijo: float = 0.0
    gf_pct_variable: float = 0.0
    utilidad_pct: float = 0.0
    moneda: str = 'Soles'
    subpresupuestos: list['SubpresupuestoS10'] = field(default_factory=list)


@dataclass
class SubpresupuestoS10:
    cod_subpresupuesto: str     # ej. '001'
    descripcion: str            # ej. 'ACTIVIDAD 1'
    costo_directo: float = 0.0
    costo_mo: float = 0.0
    costo_mat: float = 0.0
    costo_eq: float = 0.0
    costo_sc: float = 0.0


@dataclass
class NodoArbol:
    """Una entrada en `SubpresupuestoDetalle` — puede ser título o partida."""
    orden: str                  # '01', '01.02', '01.02.03' — código jerárquico visible
    nivel: int                  # profundidad (0/1/2/3...)
    es_titulo: bool             # True si Tipo=5, False si Tipo=1
    descripcion: str            # del catálogo Partida o Titulo
    unidad: Optional[str]       # solo en partidas hoja
    metrado: float
    precio_unitario: float
    horas_hombre: float         # HH/unidad — suma de cantidades MO de la partida
    rendimiento_mo: float       # Partida.RendimientoMO — unidades/día (para cuadrilla)
    jornada: float              # Partida.Jornada — horas/día (default 8)
    cod_partida: Optional[str]  # solo en partidas (apunta a Partida.CodPartida)
    cod_titulo: Optional[str]   # solo en títulos
    propio_partida: str         # '99' = no propia, otros = propias


@dataclass
class ACUItem:
    """Una línea del ACU — relación partida → insumo."""
    cod_partida: str
    propio_partida: str
    cod_insumo: str
    tipo: int                   # 1=MO, 2=MAT, 3=EQ, 4=SC, 5=Subpartida
    unidad: str
    cantidad: float
    precio: float
    parcial: float


@dataclass
class Insumo:
    """Recurso del catálogo de S10."""
    cod_insumo: str
    descripcion: str
    cod_unidad: str
    cod_indice_unificado: str   # INEI
    nivel: int                  # nivel jerárquico (más útil descartar nodos no-hoja)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de saneamiento
# ─────────────────────────────────────────────────────────────────────────────

def _fecha_o_none(f: Optional[datetime]) -> Optional[datetime]:
    if f is None or f == FECHA_VACIA_S10:
        return None
    return f


def _str_o_default(s: Optional[str], default: str = '') -> str:
    return (s or '').strip() or default


def _num_o_default(n, default: float = 0.0) -> float:
    if n is None:
        return default
    try:
        return float(n)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Reader
# ─────────────────────────────────────────────────────────────────────────────

class S10Reader:
    """Lee tablas de una base de datos S10 restaurada en SQL Server.

    Args:
        conn: conexión pyodbc a la BD de S10 (ya con USE de la BD restaurada).
    """

    def __init__(self, conn):
        self.conn = conn

    # ── Listar proyectos disponibles ─────────────────────────────────────────

    def listar_presupuestos(self) -> list[tuple[str, str]]:
        """Retorna (CodPresupuesto, Descripcion) de los presupuestos disponibles.

        Solo los presupuestos hoja (con subpresupuestos asociados). En S10 la
        tabla `Presupuesto` tiene jerarquía por longitud del código — los
        niveles intermedios (ej. '02', '0201') son categorías, los hoja
        (ej. '0201001') son los presupuestos reales.
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT p.CodPresupuesto, p.Descripcion
            FROM Presupuesto p
            INNER JOIN Subpresupuesto s ON s.CodPresupuesto = p.CodPresupuesto
            WHERE p.CodPresupuesto <> '9999999'
            ORDER BY p.CodPresupuesto
        """)
        return [(r[0].strip(), (r[1] or '').strip()) for r in cur.fetchall()]

    def listar_subpresupuestos(self, cod_presupuesto: str) -> list[SubpresupuestoS10]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT CodSubpresupuesto, Descripcion,
                   CostoDirectoOferta1, CostoManoDeObra1, CostoMaterial1,
                   CostoEquipo1, CostoSubcontrato1
            FROM Subpresupuesto
            WHERE CodPresupuesto = %s
            ORDER BY CodSubpresupuesto
        """, (cod_presupuesto,))
        return [
            SubpresupuestoS10(
                cod_subpresupuesto=(r[0] or '').strip(),
                descripcion=_str_o_default(r[1]),
                costo_directo=_num_o_default(r[2]),
                costo_mo=_num_o_default(r[3]),
                costo_mat=_num_o_default(r[4]),
                costo_eq=_num_o_default(r[5]),
                costo_sc=_num_o_default(r[6]),
            )
            for r in cur.fetchall()
        ]

    # ── Info del proyecto ────────────────────────────────────────────────────

    def leer_proyecto(self, cod_presupuesto: str) -> ProyectoS10:
        """Lee info general del presupuesto desde tabla `Presupuesto`.

        S10 separa:
        - `Presupuesto`: árbol jerárquico de presupuestos (por longitud de código).
          El nivel hoja es el presupuesto real con sus datos (plazo, fecha, IGV,
          moneda, ubicación INEI, etc.).
        - `Proyecto`: catálogo separado de proyectos del sistema (templates),
          típicamente sin relación directa con presupuestos reales.
        """
        cur = self.conn.cursor()
        # JOINs con UbicacionGeografica para resolver el código INEI ubigeo
        # (ej. '150113') al nombre completo (ej. "Jesús María, Lima, Lima").
        # El código jerárquico es: 2 chars=departamento, 4=provincia, 6=distrito.
        cur.execute("""
            SELECT
                p.CodPresupuesto, p.Descripcion, p.Fecha, p.Plazo, p.Jornada,
                p.CodLugar, p.CodMoneda1, p.PorcentajeGG, p.PorcentajeGG2,
                p.FechaProceso,
                u3.Descripcion AS distrito,
                u2.Descripcion AS provincia,
                u1.Descripcion AS departamento
            FROM Presupuesto p
            LEFT JOIN UbicacionGeografica u3
                   ON u3.CodLugar = p.CodLugar AND u3.Nivel = 3
            LEFT JOIN UbicacionGeografica u2
                   ON u2.CodLugar = LEFT(p.CodLugar, 4) AND u2.Nivel = 2
            LEFT JOIN UbicacionGeografica u1
                   ON u1.CodLugar = LEFT(p.CodLugar, 2) AND u1.Nivel = 1
            WHERE p.CodPresupuesto = %s
        """, (cod_presupuesto,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"No se encontró Presupuesto con CodPresupuesto={cod_presupuesto}"
            )

        # Moneda: S10 usa códigos cortos. '01' suele ser Soles, '02' USD.
        cod_moneda = (row[6] or '').strip()
        moneda = {
            '01': 'Soles',
            '02': 'Dólares',
        }.get(cod_moneda, 'Soles')

        # Jornada laboral
        jornada = _num_o_default(row[4], 8.0)
        if jornada <= 0:
            jornada = 8.0

        # Ubicación: armar "Departamento, Provincia, Distrito" (orden estándar
        # peruano: de general a específico). Dedup conservando orden — evita
        # "Tacna, Tacna, Tacna" cuando los 3 niveles tienen el mismo nombre
        # (frecuente en capitales departamentales).
        partes = [_str_o_default(row[12]),  # departamento
                  _str_o_default(row[11]),  # provincia
                  _str_o_default(row[10])]  # distrito
        # Capitalizar (S10 los guarda en MAYÚSCULAS) + filtrar vacíos
        partes = [p.title() for p in partes if p]
        if partes:
            # Dedup conservando orden de aparición
            seen = set()
            unique = [p for p in partes if not (p in seen or seen.add(p))]
            ubicacion = ', '.join(unique)
        else:
            ubicacion = _str_o_default(row[5])  # fallback al código crudo

        return ProyectoS10(
            cod_presupuesto=cod_presupuesto,
            nombre=_str_o_default(row[1], default=f'Proyecto S10 {cod_presupuesto}'),
            ubicacion=ubicacion,
            cliente='',
            fecha_inicio=_fecha_o_none(row[2]),
            fecha_fin=None,
            plazo=int(row[3] or 60),
            igv_pct=18.0,  # S10 no almacena IGV directo, asumir 18% Perú
            gf_pct_fijo=_num_o_default(row[7]),
            gf_pct_variable=_num_o_default(row[8]),
            utilidad_pct=0.0,
            moneda=moneda,
        )

    # ── Árbol de partidas + títulos ──────────────────────────────────────────

    def leer_arbol(
        self, cod_presupuesto: str, cod_subpresupuesto: str
    ) -> list[NodoArbol]:
        """Lee el árbol completo (títulos + partidas) de un subpresupuesto.

        El árbol se ordena por `Item` (padding interno de S10) — ese es el
        orden natural de inserción. El campo visible para el usuario es `Orden`
        (ej. '01.02').
        """
        cur = self.conn.cursor()
        # JOINs filtran los wildcards de S10:
        # - Partida.CodPartida='999999999999' es placeholder con Descripcion
        #   "REGISTRO RESTRINGIDO" — los títulos usan ese código pero NO deben
        #   tomar la descripcion del wildcard, deben ir al catálogo Titulo.
        # - Titulo.CodTitulo='9999999'/'9999998' son wildcards similares.
        cur.execute("""
            SELECT
                sd.Orden, sd.Nivel, sd.Tipo,
                sd.Metrado, sd.Precio1, sd.HorasHombre,
                sd.CodTitulo, sd.CodPartida, sd.PropioPartida,
                COALESCE(NULLIF(LTRIM(RTRIM(sd.Descripcion)), ''),
                         NULLIF(LTRIM(RTRIM(p.Descripcion)), ''),
                         NULLIF(LTRIM(RTRIM(t.Descripcion)), ''),
                         '') AS descripcion,
                COALESCE(NULLIF(LTRIM(RTRIM(sd.Unidad)), ''),
                         u.Simbolo,
                         '') AS unidad,
                COALESCE(p.RendimientoMO, 1.0) AS rendimiento_mo,
                COALESCE(p.Jornada, 8.0)       AS jornada
            FROM SubpresupuestoDetalle sd
            LEFT JOIN Partida p
                   ON p.CodPartida = sd.CodPartida
                  AND p.PropioPartida = sd.PropioPartida
                  AND p.CodPresupuesto = (
                      CASE WHEN sd.PropioPartida = '99' THEN '9999999'
                           ELSE sd.CodPresupuesto END
                  )
                  AND sd.Tipo = 1
                  AND p.CodPartida NOT LIKE '999%%'
            LEFT JOIN Titulo t
                   ON t.CodTitulo = sd.CodTitulo
                  AND sd.Tipo = 5
                  AND t.CodTitulo NOT LIKE '999%%'
            LEFT JOIN Unidad u
                   ON u.CodUnidad = COALESCE(p.CodUnidad, '')
            WHERE sd.CodPresupuesto = %s AND sd.CodSubpresupuesto = %s
            ORDER BY sd.Item
        """, (cod_presupuesto, cod_subpresupuesto))

        nodos: list[NodoArbol] = []
        for r in cur.fetchall():
            orden = (r[0] or '').strip()
            tipo = int(r[2] or 0)
            es_titulo = (tipo == TIPO_TITULO)
            # Saltar entradas sin orden visible (filas de control internas)
            if not orden:
                continue
            nodos.append(NodoArbol(
                orden=orden,
                nivel=int(r[1] or 0),
                es_titulo=es_titulo,
                descripcion=_str_o_default(r[9]),
                unidad=(_str_o_default(r[10]) or None) if not es_titulo else None,
                metrado=_num_o_default(r[3]),
                precio_unitario=_num_o_default(r[4]),
                horas_hombre=_num_o_default(r[5]),
                rendimiento_mo=_num_o_default(r[11], 1.0),
                jornada=_num_o_default(r[12], 8.0),
                cod_partida=(_str_o_default(r[7]) or None),
                cod_titulo=(_str_o_default(r[6]) or None),
                propio_partida=_str_o_default(r[8], '99'),
            ))
        return nodos

    # ── ACU items por subpresupuesto ─────────────────────────────────────────

    def leer_acu_items(
        self, cod_presupuesto: str, cod_subpresupuesto: str
    ) -> list[ACUItem]:
        """Lee TODOS los ACU items del subpresupuesto."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                a.CodPartida, a.PropioPartida, a.CodInsumo, a.Tipo,
                a.Unidad, a.Cantidad, a.Precio1, a.Parcial1
            FROM PresupuestoPartidaAnalisis a
            WHERE a.CodPresupuesto = %s AND a.CodSubpresupuesto = %s
            ORDER BY a.CodPartida, a.PropioPartida, a.Tipo, a.CodInsumo
        """, (cod_presupuesto, cod_subpresupuesto))
        return [
            ACUItem(
                cod_partida=(r[0] or '').strip(),
                propio_partida=_str_o_default(r[1], '99'),
                cod_insumo=(r[2] or '').strip(),
                tipo=int(r[3] or 0),
                unidad=_str_o_default(r[4]),
                cantidad=_num_o_default(r[5]),
                precio=_num_o_default(r[6]),
                parcial=_num_o_default(r[7]),
            )
            for r in cur.fetchall()
        ]

    # ── Insumos usados (con descripción del catálogo) ────────────────────────

    def leer_insumos(self, cods_insumo: set[str]) -> dict[str, Insumo]:
        """Lee los insumos referenciados (catálogo Insumo).

        Devuelve dict {cod_insumo: Insumo} para los códigos pedidos. Si un
        código no existe en el catálogo, no aparece en el dict.
        """
        if not cods_insumo:
            return {}
        # SQL Server tiene límite ~2100 parámetros — partir en chunks
        result: dict[str, Insumo] = {}
        cods_list = list(cods_insumo)
        chunk_size = 1500
        cur = self.conn.cursor()
        for i in range(0, len(cods_list), chunk_size):
            chunk = cods_list[i:i + chunk_size]
            placeholders = ','.join(['%s'] * len(chunk))
            cur.execute(f"""
                SELECT
                    i.CodInsumo, i.Descripcion, i.CodUnidad,
                    i.CodIndiceUnificado, i.Nivel,
                    u.Simbolo
                FROM Insumo i
                LEFT JOIN Unidad u ON u.CodUnidad = i.CodUnidad
                WHERE i.CodInsumo IN ({placeholders})
            """, tuple(chunk))
            for r in cur.fetchall():
                cod = (r[0] or '').strip()
                result[cod] = Insumo(
                    cod_insumo=cod,
                    descripcion=_str_o_default(r[1]),
                    cod_unidad=_str_o_default(r[5] or r[2]),  # prefiere símbolo
                    cod_indice_unificado=_str_o_default(r[3]),
                    nivel=int(r[4] or 0),
                )
        return result

    # ── Precios particulares (overrides por proyecto) ────────────────────────

    def leer_precios_particulares(
        self, cod_presupuesto: str
    ) -> dict[str, float]:
        """Lee `PrecioParticularInsumo` — overrides de precio por proyecto.
        Devuelve dict {cod_insumo: precio_particular}."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT CodInsumo, Precio1
            FROM PrecioParticularInsumo
            WHERE CodPresupuesto = %s
        """, (cod_presupuesto,))
        return {
            (r[0] or '').strip(): _num_o_default(r[1])
            for r in cur.fetchall()
        }

    # ── Índices INEI ─────────────────────────────────────────────────────────

    def leer_indices_inei(self) -> list[tuple[str, str]]:
        """Retorna lista (codigo, nombre) del catálogo IndiceUnificado."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT CodIndiceUnificado, Descripcion
            FROM IndiceUnificado
            ORDER BY CodIndiceUnificado
        """)
        return [
            ((r[0] or '').strip(), _str_o_default(r[1]))
            for r in cur.fetchall()
        ]
