"""Backends de SQL Server por plataforma.

Abstrae cómo se levanta SQL Server según el OS, para que `convertir.py` no
tenga que saber si el SQL corre nativo (Windows LocalDB) o en un container
(Linux/Mac Docker).

**Interface**: `SQLServerBackend` con `esta_disponible / preparar / restaurar /
conectar / limpiar`. Factory `crear_backend()` elige según `sys.platform`.

**Convenciones**:
- Password SA fijo (`IngeConv2026!`) — el container/instancia es local-only
  y se descarta tras la conversión.
- BD destino siempre `s10_conv` (reusable, `RESTORE ... WITH REPLACE`).
- `.S2K`, `.bak`, `.bkf` son todos backups MTF idénticos. Se restauran igual.
- Versión mínima soportada: SQL Server 2005 (versión interna 611).
  Backups más antiguos (SQL 7.0/2000) fallan con error 3169 — propagar como
  `BackupVersionTooOld` para que el caller muestre un mensaje user-facing.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


log = logging.getLogger("ingeconverter.backend")


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

SA_PASSWORD = 'IngeConv2026!'
DB_NAME = 's10_conv'
CONTAINER_NAME = 'ingeconv-mssql'
IMAGE_NAME = 'mcr.microsoft.com/mssql/server:2022-latest'
SQLCMD_IN_CONTAINER = '/opt/mssql-tools18/bin/sqlcmd'
PORT = 1433


# ─────────────────────────────────────────────────────────────────────────────
# Errores
# ─────────────────────────────────────────────────────────────────────────────

class BackendError(Exception):
    """Error genérico del backend (Docker no instalado, container muerto, etc.)."""


class BackupVersionTooOld(BackendError):
    """El backup viene de SQL Server <2005 (versión interna <611).

    SQL Server 2022 no puede restaurarlo directamente. El usuario debe
    abrir el .S2K en una versión moderna de S10 y reexportarlo.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────────────────────────────────────

class SQLServerBackend(ABC):
    """Interface común para gestionar SQL Server local."""

    @abstractmethod
    def esta_disponible(self) -> bool:
        """True si el backend (Docker / LocalDB) está instalado y operativo."""

    @abstractmethod
    def instrucciones_instalacion(self) -> str:
        """Texto user-facing con cómo instalar el backend cuando falta."""

    @abstractmethod
    def preparar(self) -> None:
        """Asegura que SQL Server está corriendo y aceptando conexiones.
        Idempotente. Lanza `BackendError` si no puede dejar el server listo.
        """

    @abstractmethod
    def restaurar(self, archivo: Path) -> str:
        """Restaura un `.S2K/.bak/.bkf` y retorna el nombre de la BD destino.
        Lanza `BackupVersionTooOld` si SQL Server rechaza el backup por viejo.
        """

    @abstractmethod
    def conectar(self, database: Optional[str] = None):
        """Retorna una conexión pymssql (a la BD restaurada por default)."""

    @abstractmethod
    def limpiar(self, database: Optional[str] = None) -> None:
        """Elimina la BD temporal (no detiene el server)."""


# ─────────────────────────────────────────────────────────────────────────────
# Docker (Linux/Mac)
# ─────────────────────────────────────────────────────────────────────────────

class DockerBackend(SQLServerBackend):
    """SQL Server 2022 corriendo en un container Docker dedicado.

    Mantiene un container llamado `ingeconv-mssql` siempre listo:
    - Primera vez: `docker pull` (~2.3 GB) + `docker run -d` con volumen
      persistente para que la BD no se pierda entre reinicios.
    - Siguientes: `docker start` si está parado.

    Para cada `.S2K` el archivo se copia al container vía `docker cp` y se
    borra de adentro al terminar. El container no usa bind mounts dinámicos.
    """

    def __init__(self, container_name: str = CONTAINER_NAME):
        self.container_name = container_name
        self.ultima_db: Optional[str] = None

    # ── Docker helpers ───────────────────────────────────────────────────────

    def _docker(self, *args: str, check: bool = True,
                capture: bool = True) -> subprocess.CompletedProcess:
        cmd = ['docker', *args]
        log.debug(f"$ {' '.join(cmd)}")
        return subprocess.run(
            cmd, check=check,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
        )

    def _container_existe(self) -> bool:
        r = self._docker('inspect', '--type=container', self.container_name,
                         check=False)
        return r.returncode == 0

    def _container_corriendo(self) -> bool:
        r = self._docker('inspect', '-f', '{{.State.Running}}',
                         self.container_name, check=False)
        return r.returncode == 0 and r.stdout.strip() == 'true'

    def _imagen_existe(self) -> bool:
        r = self._docker('image', 'inspect', IMAGE_NAME, check=False)
        return r.returncode == 0

    # ── API ──────────────────────────────────────────────────────────────────

    def esta_disponible(self) -> bool:
        if shutil.which('docker') is None:
            return False
        try:
            self._docker('version')
            return True
        except subprocess.CalledProcessError:
            return False

    def instrucciones_instalacion(self) -> str:
        if sys.platform == 'darwin':
            return (
                "Docker Desktop no está instalado o no está corriendo.\n"
                "1. Descargalo de https://www.docker.com/products/docker-desktop/\n"
                "2. Instalalo y ábrelo (debe quedar el ícono de la ballena en la barra superior).\n"
                "3. Volvé a intentar.\n\n"
                "(IngeConverter descargará ~2.3 GB la primera vez para SQL Server 2022.)"
            )
        return (
            "Docker no está instalado o tu usuario no tiene permisos.\n"
            "1. Instalá Docker Engine: https://docs.docker.com/engine/install/\n"
            "2. Agregá tu usuario al grupo docker:\n"
            "       sudo usermod -aG docker $USER\n"
            "   y reiniciá sesión.\n"
            "3. Verificá que funciona:  docker version\n\n"
            "(IngeConverter descargará ~2.3 GB la primera vez para SQL Server 2022.)"
        )

    def preparar(self) -> None:
        if not self.esta_disponible():
            raise BackendError(self.instrucciones_instalacion())

        if not self._container_existe():
            self._crear_container()
        elif not self._container_corriendo():
            log.info(f"Iniciando container {self.container_name}…")
            self._docker('start', self.container_name)

        self._esperar_sql_listo()

    def _crear_container(self) -> None:
        if not self._imagen_existe():
            log.info(f"Descargando imagen {IMAGE_NAME} (~2.3 GB, una sola vez)…")
            # capture=False para que el progress de docker pull se vea en stdout
            self._docker('pull', IMAGE_NAME, capture=False)

        log.info(f"Creando container {self.container_name}…")
        self._docker(
            'run', '-d',
            '--name', self.container_name,
            '-e', 'ACCEPT_EULA=Y',
            '-e', f'MSSQL_SA_PASSWORD={SA_PASSWORD}',
            '-e', 'MSSQL_PID=Developer',
            '-p', f'127.0.0.1:{PORT}:1433',  # local-only
            '-v', f'{self.container_name}-data:/var/opt/mssql',
            IMAGE_NAME,
        )

    def _esperar_sql_listo(self, timeout: int = 90) -> None:
        """Hace polling con sqlcmd dentro del container hasta que responde."""
        deadline = time.time() + timeout
        ultimo_error = ''
        while time.time() < deadline:
            r = self._docker(
                'exec', self.container_name,
                SQLCMD_IN_CONTAINER,
                '-S', 'localhost', '-U', 'sa', '-P', SA_PASSWORD, '-C',
                '-Q', 'SELECT 1',
                check=False,
            )
            if r.returncode == 0:
                return
            ultimo_error = (r.stderr or r.stdout or '').strip()
            time.sleep(1)
        raise BackendError(
            f"SQL Server no respondió en {timeout}s. Último error:\n{ultimo_error}"
        )

    def restaurar(self, archivo: Path) -> str:
        archivo = Path(archivo).resolve()
        if not archivo.exists():
            raise BackendError(f"Archivo no existe: {archivo}")

        path_en_container = f'/tmp/{archivo.name}'
        log.info(f"Copiando {archivo.name} al container…")
        self._docker('cp', str(archivo),
                     f'{self.container_name}:{path_en_container}')

        try:
            # Conectar a master para hacer el RESTORE
            conn = self.conectar(database='master')
            try:
                files = _leer_filelist(conn, path_en_container)
                _restore_database(conn, DB_NAME, path_en_container, files)
            finally:
                conn.close()
        finally:
            # Borrar el .S2K del container (docker cp lo deja como root)
            self._docker('exec', '--user', 'root', self.container_name,
                         'rm', '-f', path_en_container, check=False)

        self.ultima_db = DB_NAME
        log.info(f"BD restaurada como {DB_NAME!r}")
        return DB_NAME

    def conectar(self, database: Optional[str] = None):
        import pymssql
        return pymssql.connect(
            server='127.0.0.1', port=PORT,
            user='sa', password=SA_PASSWORD,
            database=database or self.ultima_db or 'master',
            as_dict=False,
        )

    def limpiar(self, database: Optional[str] = None) -> None:
        db = database or self.ultima_db
        if not db:
            return
        log.info(f"Eliminando BD {db!r}…")
        try:
            conn = self.conectar(database='master')
            cur = conn.cursor()
            # autocommit para evitar "ALTER DATABASE inside transaction"
            conn.autocommit(True)
            cur.execute(
                f"IF DB_ID('{db}') IS NOT NULL BEGIN "
                f"ALTER DATABASE [{db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
                f"DROP DATABASE [{db}]; END"
            )
            conn.close()
        except Exception as e:
            log.warning(f"No se pudo limpiar la BD {db}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# LocalDB (Windows) — esqueleto
# ─────────────────────────────────────────────────────────────────────────────

class LocalDBBackend(SQLServerBackend):
    """SQL Server LocalDB (nativo Windows, distribuido por Microsoft).

    LocalDB es una versión gratuita y embebida de SQL Server Express:
    - Se instala con un MSI (~340 MB total con .NET incluido)
    - Corre on-demand (no es un servicio fijo)
    - Instance default: `(localdb)\\MSSQLLocalDB`
    - Auth: Windows Integrated (no usa SA password)

    NOTA: esta implementación NO está probada en Linux. Está acá para
    permitir desarrollo Windows futuro sin reorganizar todo.
    """

    INSTANCE = r'(localdb)\MSSQLLocalDB'

    def __init__(self):
        self.ultima_db: Optional[str] = None

    def esta_disponible(self) -> bool:
        if sys.platform != 'win32':
            return False
        # SqlLocalDB.exe es la utility oficial de Microsoft
        return shutil.which('SqlLocalDB.exe') is not None or \
               shutil.which('sqllocaldb') is not None

    def instrucciones_instalacion(self) -> str:
        return (
            "Microsoft SQL Server LocalDB no está instalado.\n"
            "Descargalo de:\n"
            "   https://www.microsoft.com/en-us/download/details.aspx?id=104781\n"
            "(busca 'SqlLocalDB.msi', ~60 MB; requiere .NET Framework 4.8)\n\n"
            "Después de instalar, abrí una terminal nueva e intentá de nuevo."
        )

    def preparar(self) -> None:
        if not self.esta_disponible():
            raise BackendError(self.instrucciones_instalacion())
        # Asegurar que la instancia default esté arrancada
        subprocess.run(['SqlLocalDB.exe', 'start', 'MSSQLLocalDB'], check=False)

    def restaurar(self, archivo: Path) -> str:
        import pymssql
        archivo = Path(archivo).resolve()
        if not archivo.exists():
            raise BackendError(f"Archivo no existe: {archivo}")

        # LocalDB se conecta vía named pipe — pymssql necesita la sintaxis
        # `np:\\.\pipe\LOCALDB#...\tsql\query`. Más simple: usar el
        # `server=(localdb)\MSSQLLocalDB` que pymssql/FreeTDS no soporta
        # bien. Por eso en Windows típicamente se usa `pyodbc` con
        # `Trusted_Connection=yes`. Acá dejamos un placeholder claro.
        raise NotImplementedError(
            "LocalDBBackend.restaurar() no está implementado todavía. "
            "Requiere pyodbc + driver ODBC nativo (no pymssql)."
        )

    def conectar(self, database: Optional[str] = None):
        raise NotImplementedError(
            "LocalDBBackend.conectar() no está implementado todavía."
        )

    def limpiar(self, database: Optional[str] = None) -> None:
        pass  # No-op hasta que conectar/restaurar estén implementados.


# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartidos (RESTORE FILELISTONLY / RESTORE DATABASE)
# ─────────────────────────────────────────────────────────────────────────────

def _leer_filelist(conn, path_backup: str) -> list[tuple[str, str]]:
    """Retorna [(LogicalName, Type), ...] del backup.

    Type: 'D' = datafile (mdf/ndf), 'L' = log (ldf).

    Nombres lógicos varían: S10 usa típicamente `S10_Data`, `S10_Datos`,
    `S10_Log`, pero versiones distintas pueden tener otros. Por eso siempre
    leemos el filelist en lugar de hardcodearlos.
    """
    cur = conn.cursor()
    try:
        cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{path_backup}'")
        rows = cur.fetchall()
    except Exception as e:
        msg = str(e)
        # SQL Server error 3169: backup version too old
        if '3169' in msg or 'older version' in msg.lower():
            raise BackupVersionTooOld(
                "Este backup viene de SQL Server 7.0 o 2000 (muy antiguo). "
                "SQL Server 2022 no puede restaurarlo directamente.\n"
                "Solución: abrí el archivo en una versión moderna de S10 "
                "(2009+) y volvé a exportar el backup."
            ) from e
        raise BackendError(f"RESTORE FILELISTONLY falló: {msg}") from e

    # Columnas 0, 1, 2 = LogicalName, PhysicalName, Type
    return [(r[0].strip(), r[2].strip()) for r in rows]


def _restore_database(conn, db_name: str, path_backup: str,
                      files: list[tuple[str, str]]) -> None:
    """Ejecuta `RESTORE DATABASE ... WITH MOVE ..., REPLACE`."""
    moves = []
    data_dir = '/var/opt/mssql/data'  # path dentro del container (Linux MSSQL)
    log_dir = '/var/opt/mssql/data'   # MSSQL Linux pone log en mismo dir
    for logical, file_type in files:
        ext = 'ldf' if file_type == 'L' else 'mdf'
        target = f"{log_dir if file_type == 'L' else data_dir}/{db_name}_{logical}.{ext}"
        moves.append(f"MOVE N'{logical}' TO N'{target}'")

    sql = (
        f"RESTORE DATABASE [{db_name}] FROM DISK = N'{path_backup}' "
        f"WITH {', '.join(moves)}, REPLACE"
    )
    log.debug(f"SQL: {sql}")
    cur = conn.cursor()
    conn.autocommit(True)  # RESTORE no puede ir dentro de transacción
    try:
        cur.execute(sql)
    except Exception as e:
        msg = str(e)
        if '3169' in msg or 'older version' in msg.lower():
            raise BackupVersionTooOld(
                "Este backup viene de SQL Server 7.0 o 2000 (muy antiguo). "
                "SQL Server 2022 no puede restaurarlo directamente."
            ) from e
        raise BackendError(f"RESTORE DATABASE falló: {msg}") from e


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def crear_backend() -> SQLServerBackend:
    """Retorna el backend apropiado para la plataforma actual."""
    if sys.platform == 'win32':
        return LocalDBBackend()
    return DockerBackend()
