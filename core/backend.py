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
import os
import shutil
import subprocess
import sys
import tempfile
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
                "═══ Falta instalar Docker Desktop ═══\n\n"
                "Docker es un programa gratuito que IngeConverter necesita\n"
                "para leer los archivos de S10. Solo se instala una vez.\n\n"
                "PASOS PARA INSTALAR:\n\n"
                "  1. Abre tu navegador (Safari, Chrome, etc.) y ve a:\n"
                "     https://www.docker.com/products/docker-desktop/\n\n"
                "  2. Descarga e instala Docker Desktop\n"
                "     (sigue el asistente como cualquier programa)\n\n"
                "  3. Abre Docker Desktop desde Aplicaciones\n"
                "     (aparece un icono de ballena arriba en la barra)\n\n"
                "  4. Vuelve aqui y haz clic en «Reintentar»\n\n"
                "IMPORTANTE: la primera vez que conviertas un archivo .S2K,\n"
                "se descargaran ~2.3 GB adicionales (el motor de base de datos\n"
                "de Microsoft). Esto es automatico y solo pasa una vez.\n"
                "Las conversiones siguientes tardan ~20 segundos."
            )
        docker_installed = shutil.which('docker') is not None
        if docker_installed:
            return (
                "═══ Docker necesita un permiso adicional ═══\n\n"
                "Docker ya esta instalado en tu equipo, pero tu usuario\n"
                "no tiene permiso para usarlo. Hay que agregarlo al grupo\n"
                "de Docker. Solo se hace una vez.\n\n"
                "COMO SOLUCIONARLO (3 pasos):\n\n"
                "  1. Abre una terminal:\n"
                "     - En Ubuntu/Mint: clic derecho en el escritorio\n"
                "       y elige \"Abrir terminal\", o busca \"Terminal\"\n"
                "       en el menu de aplicaciones.\n\n"
                "  2. Copia y pega este comando (te pedira tu contrasena):\n\n"
                "     sudo usermod -aG docker $USER\n\n"
                "     (Este comando le dice al sistema: \"agrega mi usuario\n"
                "      al grupo de personas que pueden usar Docker\")\n\n"
                "  3. CIERRA TU SESION del sistema operativo y vuelve\n"
                "     a entrar (no basta cerrar la terminal, hay que\n"
                "     cerrar sesion completa o reiniciar el equipo).\n\n"
                "PARA VERIFICAR QUE FUNCIONO:\n"
                "  Abre una terminal y escribe:\n\n"
                "     docker version\n\n"
                "  Si aparece informacion de version (numeros y texto),\n"
                "  todo esta bien. Vuelve aqui y haz clic en «Reintentar»."
            )
        return (
            "═══ Falta instalar Docker ═══\n\n"
            "Docker es un programa gratuito que IngeConverter necesita\n"
            "para leer los archivos .S2K de S10. Es como un contenedor\n"
            "virtual donde corre el motor de base de datos de Microsoft.\n"
            "Solo se instala una vez.\n\n"
            "COMO INSTALARLO (4 pasos):\n\n"
            "  1. Abre una terminal:\n"
            "     - En Ubuntu/Mint: clic derecho en el escritorio\n"
            "       y elige \"Abrir terminal\", o busca \"Terminal\"\n"
            "       en el menu de aplicaciones.\n"
            "     - En Fedora: busca \"Terminal\" en Actividades.\n\n"
            "  2. Copia y pega ESTOS DOS comandos (te pedira tu\n"
            "     contrasena de usuario):\n\n"
            "     Ubuntu / Debian / Linux Mint:\n"
            "       sudo apt install docker.io\n"
            "       sudo usermod -aG docker $USER\n\n"
            "     Fedora:\n"
            "       sudo dnf install docker\n"
            "       sudo systemctl enable --now docker\n"
            "       sudo usermod -aG docker $USER\n\n"
            "     (El primer comando instala Docker.\n"
            "      El segundo te da permiso para usarlo.)\n\n"
            "  3. CIERRA TU SESION del sistema operativo y vuelve\n"
            "     a entrar (no basta cerrar la terminal, hay que\n"
            "     cerrar sesion completa o reiniciar el equipo).\n\n"
            "  4. Verifica que funciono. Abre una terminal y escribe:\n\n"
            "       docker version\n\n"
            "     Si aparece informacion de version (numeros y texto),\n"
            "     todo esta bien. Vuelve aqui y haz clic en «Reintentar».\n\n"
            "IMPORTANTE: la primera vez que conviertas un archivo .S2K,\n"
            "se descargaran ~2.3 GB adicionales (el motor de base de datos\n"
            "de Microsoft). Esto es automatico y solo pasa una vez.\n"
            "Las conversiones siguientes tardan ~20 segundos."
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
    - Se instala con un MSI (~60 MB; con .NET runtime ~340 MB total bundleado)
    - Corre on-demand (no es un servicio fijo — arranca al conectarte)
    - Instance default: ``(localdb)\\MSSQLLocalDB``
    - Auth: Windows Integrated (no usa SA password)

    Conexión vía ``pyodbc`` con ``Trusted_Connection=yes`` y el driver
    ``ODBC Driver 17 for SQL Server`` (o 18). pymssql/FreeTDS no soporta
    bien las named pipes de LocalDB.
    """

    INSTANCE = r'(localdb)\MSSQLLocalDB'

    def __init__(self):
        self.ultima_db: Optional[str] = None
        self._data_dir: Optional[str] = None

    def esta_disponible(self) -> bool:
        if sys.platform != 'win32':
            return False
        return shutil.which('SqlLocalDB.exe') is not None or \
               shutil.which('sqllocaldb') is not None

    @staticmethod
    def _find_odbc_driver() -> Optional[str]:
        """Busca un driver ODBC de SQL Server instalado (18 preferido, 17 fallback)."""
        try:
            import pyodbc
            drivers = pyodbc.drivers()
        except (ImportError, Exception):
            return None
        for ver in ('18', '17', '13'):
            name = f'ODBC Driver {ver} for SQL Server'
            if name in drivers:
                return name
        for d in drivers:
            if 'sql server' in d.lower():
                return d
        return None

    def instrucciones_instalacion(self) -> str:
        driver = self._find_odbc_driver()
        msg = (
            "═══ SQL Server LocalDB no encontrado ═══\n\n"
            "IngeConverter necesita LocalDB para restaurar backups de S10.\n\n"
            "Si usaste el INSTALADOR de IngeConverter, LocalDB debería\n"
            "haberse instalado automáticamente. Reinicia e intenta de nuevo.\n\n"
            "Si usaste el ZIP portable, instala manualmente:\n\n"
            "  1. Descarga SqlLocalDB.msi (~60 MB) de:\n"
            "     https://learn.microsoft.com/sql/database-engine/configure-windows/sql-server-express-localdb\n\n"
            "  2. Ejecuta el MSI y reinicia si lo pide.\n\n"
        )
        if not driver:
            msg += (
                "  3. También necesitas el driver ODBC:\n"
                "     https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server\n"
                "     (elige «ODBC Driver 18 for SQL Server»)\n\n"
            )
        msg += "Haz clic en «Reintentar» cuando estén instalados."
        return msg

    def preparar(self) -> None:
        if not self.esta_disponible():
            raise BackendError(self.instrucciones_instalacion())

        driver = self._find_odbc_driver()
        if not driver:
            raise BackendError(
                "No se encontro un driver ODBC de SQL Server.\n"
                "Descargalo de:\n"
                "   https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server\n"
                "   (busca 'ODBC Driver 18 for SQL Server')"
            )

        localdb_exe = shutil.which('SqlLocalDB.exe') or 'SqlLocalDB.exe'

        self._iniciar_instancia(localdb_exe)
        self._resolver_data_dir(localdb_exe)

        try:
            self._esperar_sql_listo(timeout=90)
            return
        except BackendError:
            pass

        log.info("LocalDB no responde tras 90s, intentando reparar instancia...")
        self._reparar_instancia(localdb_exe)
        self._resolver_data_dir(localdb_exe)
        self._esperar_sql_listo(timeout=90)

    def _iniciar_instancia(self, localdb_exe: str) -> bool:
        """Crea (si no existe) e inicia la instancia MSSQLLocalDB.
        Retorna True si el start fue exitoso."""
        subprocess.run(
            [localdb_exe, 'create', 'MSSQLLocalDB'],
            check=False, capture_output=True, text=True,
        )
        r = subprocess.run(
            [localdb_exe, 'start', 'MSSQLLocalDB'],
            check=False, capture_output=True, text=True,
        )
        if r.returncode == 0:
            return True
        out = (r.stdout or '') + (r.stderr or '')
        log.warning(f"SqlLocalDB start fallo ({r.returncode}): {out.strip()}")
        return False

    def _reparar_instancia(self, localdb_exe: str) -> None:
        """Elimina la instancia corrupta, limpia archivos residuales y recrea.
        Ocurre cuando se desinstala y reinstala LocalDB (los archivos .mdf/.ldf
        del instance anterior quedan y corrompen el arranque)."""
        log.info("Deteniendo instancia...")
        subprocess.run([localdb_exe, 'stop', 'MSSQLLocalDB'],
                       check=False, capture_output=True)
        log.info("Eliminando instancia corrupta...")
        subprocess.run([localdb_exe, 'delete', 'MSSQLLocalDB'],
                       check=False, capture_output=True)

        # Limpiar archivos residuales del instance anterior
        local_app = os.environ.get('LOCALAPPDATA', '')
        if local_app:
            instance_dir = os.path.join(
                local_app,
                'Microsoft', 'Microsoft SQL Server Local DB', 'Instances',
                'MSSQLLocalDB',
            )
            if os.path.isdir(instance_dir):
                log.info(f"Limpiando directorio residual: {instance_dir}")
                try:
                    shutil.rmtree(instance_dir, ignore_errors=True)
                except Exception as e:
                    log.warning(f"No se pudo limpiar {instance_dir}: {e}")

        log.info("Recreando instancia MSSQLLocalDB...")
        r_create = subprocess.run(
            [localdb_exe, 'create', 'MSSQLLocalDB'],
            check=False, capture_output=True, text=True,
        )
        if r_create.returncode != 0:
            out = (r_create.stdout or '') + (r_create.stderr or '')
            log.warning(f"Recrear instancia retorno {r_create.returncode}: {out.strip()}")

        log.info("Iniciando instancia reparada...")
        r_start = subprocess.run(
            [localdb_exe, 'start', 'MSSQLLocalDB'],
            check=False, capture_output=True, text=True,
        )
        if r_start.returncode != 0:
            out = (r_start.stdout or '') + (r_start.stderr or '')
            nvme_hint = ""
            if 'no se pudo iniciar' in out.lower() or 'cannot start' in out.lower():
                nvme_hint = (
                    "\n\nSi tu laptop tiene disco NVMe, abre PowerShell como "
                    "Administrador y ejecuta:\n"
                    '  New-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet'
                    '\\Services\\stornvme\\Parameters\\Device" '
                    '-Name "ForcedPhysicalSectorSizeInBytes" '
                    '-PropertyType MultiString -Force -Value "* 4095"\n'
                    "Luego reinicia Windows e intenta de nuevo."
                )
            raise BackendError(
                f"LocalDB no pudo iniciar despues de reparar la instancia.\n"
                f"Error: {out.strip()}"
                f"{nvme_hint}"
            )

    def _resolver_data_dir(self, localdb_exe: str) -> None:
        """Resuelve el directorio de datos de la instancia para RESTORE MOVE."""
        r = subprocess.run(
            [localdb_exe, 'info', 'MSSQLLocalDB'],
            capture_output=True, text=True, check=False,
        )
        self._data_dir = None
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if 'instance pipe name' in line.lower():
                    continue
                stripped = line.strip()
                if '\\' in stripped and ('AppData' in stripped or 'MSSQL' in stripped):
                    break

        if not self._data_dir:
            local_app = os.environ.get('LOCALAPPDATA', '')
            if local_app:
                candidate = os.path.join(
                    local_app,
                    'Microsoft', 'Microsoft SQL Server Local DB', 'Instances',
                    'MSSQLLocalDB',
                )
                if os.path.isdir(candidate):
                    self._data_dir = candidate
            if not self._data_dir:
                self._data_dir = tempfile.gettempdir()

    def _esperar_sql_listo(self, timeout: int = 90) -> None:
        deadline = time.time() + timeout
        ultimo_error = ''
        while time.time() < deadline:
            try:
                conn = self.conectar(database='master')
                cur = conn.cursor()
                cur.execute('SELECT 1')
                cur.close()
                conn.close()
                return
            except Exception as e:
                ultimo_error = str(e)
                time.sleep(2)
        raise BackendError(
            f"LocalDB no respondió en {timeout}s. Último error:\n{ultimo_error}"
        )

    def restaurar(self, archivo: Path) -> str:
        archivo = Path(archivo).resolve()
        if not archivo.exists():
            raise BackendError(f"Archivo no existe: {archivo}")

        path_backup = str(archivo).replace("'", "''")

        conn = self.conectar(database='master')
        try:
            files = _leer_filelist_odbc(conn, path_backup)
            _restore_database_odbc(conn, DB_NAME, path_backup, files,
                                   self._data_dir or tempfile.gettempdir())
        finally:
            conn.close()

        self.ultima_db = DB_NAME
        log.info(f"BD restaurada como {DB_NAME!r}")
        return DB_NAME

    def conectar(self, database: Optional[str] = None):
        import pyodbc
        driver = self._find_odbc_driver()
        if not driver:
            raise BackendError("No se encontró driver ODBC de SQL Server.")

        conn_str = (
            f"Driver={{{driver}}};"
            f"Server={self.INSTANCE};"
            f"Database={database or self.ultima_db or 'master'};"
            f"Trusted_Connection=yes;"
        )
        # Driver 18 requiere TrustServerCertificate explícito para LocalDB
        if '18' in driver:
            conn_str += "TrustServerCertificate=yes;"
        return pyodbc.connect(conn_str, autocommit=True)

    def limpiar(self, database: Optional[str] = None) -> None:
        db = database or self.ultima_db
        if not db:
            return
        log.info(f"Eliminando BD {db!r}…")
        try:
            conn = self.conectar(database='master')
            cur = conn.cursor()
            cur.execute(
                f"IF DB_ID('{db}') IS NOT NULL BEGIN "
                f"ALTER DATABASE [{db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
                f"DROP DATABASE [{db}]; END"
            )
            conn.close()
        except Exception as e:
            log.warning(f"No se pudo limpiar la BD {db}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartidos (RESTORE FILELISTONLY / RESTORE DATABASE)
# ─────────────────────────────────────────────────────────────────────────────

def _check_backup_version_error(msg: str) -> None:
    """Lanza BackupVersionTooOld si el mensaje indica SQL Server <2005."""
    if '3169' in msg or 'older version' in msg.lower():
        raise BackupVersionTooOld(
            "Este backup viene de SQL Server 7.0 o 2000 (muy antiguo). "
            "SQL Server 2022 no puede restaurarlo directamente.\n"
            "Solución: abre el archivo en una versión moderna de S10 "
            "(2009+) y vuelve a exportar el backup."
        )


# ── pymssql (Docker backend) ────────────────────────────────────────────────

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
        _check_backup_version_error(msg)
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
        _check_backup_version_error(msg)
        raise BackendError(f"RESTORE DATABASE falló: {msg}") from e


# ── pyodbc (LocalDB backend) ────────────────────────────────────────────────

def _leer_filelist_odbc(conn, path_backup: str) -> list[tuple[str, str]]:
    """Versión pyodbc de _leer_filelist (pyodbc usa autocommit en la conexión,
    no en el cursor como pymssql)."""
    cur = conn.cursor()
    try:
        cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{path_backup}'")
        rows = cur.fetchall()
        while cur.nextset():
            pass
    except Exception as e:
        msg = str(e)
        _check_backup_version_error(msg)
        raise BackendError(f"RESTORE FILELISTONLY falló: {msg}") from e
    return [(r[0].strip(), r[2].strip()) for r in rows]


def _restore_database_odbc(conn, db_name: str, path_backup: str,
                           files: list[tuple[str, str]],
                           data_dir: str) -> None:
    """Versión pyodbc de _restore_database. Usa paths de Windows."""
    moves = []
    for logical, file_type in files:
        ext = 'ldf' if file_type == 'L' else 'mdf'
        target = os.path.join(data_dir, f"{db_name}_{logical}.{ext}")
        target_escaped = target.replace("'", "''")
        moves.append(f"MOVE N'{logical}' TO N'{target_escaped}'")

    sql = (
        f"RESTORE DATABASE [{db_name}] FROM DISK = N'{path_backup}' "
        f"WITH {', '.join(moves)}, REPLACE"
    )
    log.debug(f"SQL: {sql}")
    cur = conn.cursor()
    try:
        cur.execute(sql)
        # RESTORE produce múltiples result sets (mensajes informativos).
        # Sin consumirlos, pyodbc retorna antes de que el RESTORE termine
        # y cerrar la conexión aborta la operación.
        while cur.nextset():
            pass
    except Exception as e:
        msg = str(e)
        _check_backup_version_error(msg)
        raise BackendError(f"RESTORE DATABASE falló: {msg}") from e

    # Verificar que la BD quedó ONLINE
    cur.execute(
        "SELECT state_desc FROM sys.databases WHERE name = ?", (db_name,)
    )
    row = cur.fetchone()
    if row is None:
        raise BackendError(
            f"RESTORE no creó la base de datos '{db_name}'. "
            "Revisá que el archivo de backup no esté corrupto."
        )
    if row[0] != 'ONLINE':
        raise BackendError(
            f"La base de datos '{db_name}' quedó en estado {row[0]} "
            "tras el RESTORE. Puede que el backup esté dañado."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def crear_backend() -> SQLServerBackend:
    """Retorna el backend apropiado para la plataforma actual."""
    if sys.platform == 'win32':
        return LocalDBBackend()
    return DockerBackend()
