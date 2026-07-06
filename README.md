<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Marco Sumari / Sumari SAC
-->

# IngeConverter

**Complemento libre** de [IngePresupuestos](https://github.com/tuxiasumari/ingepresupuestos) que convierte bases de datos de **S10** (`.S2K`, `.bak`, `.bkf`) al formato `.db` SQLite de IngePresupuestos.

**Autor:** Ing. Marco Sumari · **Licencia:** [GPL-3.0-or-later](LICENSE) — software libre ✊

## Cómo funciona

Wizard standalone que:

1. Detecta / asiste a instalar el motor de SQL Server (LocalDB en Windows, contenedor Docker en Linux).
2. Restaura o attachea el archivo de S10.
3. Lee las tablas de S10 vía ODBC/pymssql.
4. Mapea a la estructura SQLite de IngePresupuestos.
5. Genera un `.db` que IngePresupuestos abre directamente.

## ¿Por qué un producto separado?

- **IngePresupuestos** queda liviano y multiplataforma, sin dependencia de SQL Server.
- **IngeConverter** aísla la dependencia pesada (SQL Server) que S10 necesita.
- Si S10 cambia y esto se rompe, IngePresupuestos sigue funcionando. Acople bajo intencional.
- La frontera entre ambos es **un `.db` SQLite** con el schema de IngePresupuestos. Limpia y estable.

## Plataforma

- **Windows** — Microsoft SQL Server **LocalDB** (~140 MB).
- **Linux** — **SQL Server en Docker** (contenedor local efímero solo para la conversión).
- Python 3.10+ · PySide6 · pyodbc / pymssql.

> Nota: la contraseña `IngeConv2026!` que verás en el código es la de un contenedor SQL Server **local y efímero** en tu propia máquina — no es un secreto (no hay servidor remoto).

## Estado

Funcional contra archivos `.S2K` reales de S10 (validado 1:1). En evolución con cada base real que aparece. Ver `docs/`.

## Licencia

Distribuido bajo la **Licencia Pública General de GNU v3.0 o posterior (GPL-3.0-or-later)**. Ver [LICENSE](LICENSE).

© 2026 Marco Sumari · Sumari SAC
