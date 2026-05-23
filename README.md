# IngeConverter

Convertidor de bases de datos de S10 (`.S2K`, `.bak`, `.bkf`) a formato `.db` SQLite
de **IngePresupuestos**.

Producto satélite de IngePresupuestos. Funciona como wizard standalone que:

1. Detecta o asiste a instalar **Microsoft SQL Server LocalDB** (~140 MB).
2. Restaura o attachea el archivo S10 sobre LocalDB.
3. Lee las tablas de S10 vía ODBC.
4. Mapea a la estructura SQLite de IngePresupuestos.
5. Genera un archivo `.db` que IngePresupuestos puede abrir directamente
   (ya soportado vía `core/ingepresupuestos_db_importer.py`).

## ¿Por qué un producto separado?

- **IngePresupuestos** queda liviano, multiplataforma, sin dependencia de SQL Server.
- **IngeConverter** es Windows-only (todos los usuarios de S10 ya están en Windows).
- Si IngeConverter se rompe por un cambio futuro de S10, IngePresupuestos sigue
  funcionando perfecto. Acople bajo intencional.
- La frontera entre los dos productos es **un archivo `.db` SQLite con el schema
  de IngePresupuestos**. Limpia y estable.

## Plataforma

- **Windows-only** (Microsoft SQL Server LocalDB no existe en Linux/Mac).
- Python 3.10+ · PySide6 · pyodbc.

## Estado

🚧 **Esqueleto inicial — sesión 2026-05-22.** No funcional aún. Se va construyendo
con cada migración real que aparezca de los amigos beta. Ver `docs/ROADMAP.md`.

Autor: Ing. Marco Sumari Tellez
