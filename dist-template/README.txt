IngeConverter — Convertidor de S10 a IngePresupuestos
=====================================================

Que es esto?
------------
IngeConverter convierte tus archivos de presupuesto de S10 (archivos .S2K,
.bak o .bkf) al formato de IngePresupuestos (.db). Es un complemento
gratuito de IngePresupuestos.

Una vez convertidos, los abres desde IngePresupuestos con:
  Importar -> ingePresupuestos -> seleccionar el archivo .db generado.


Como instalar en Linux (3 pasos)
---------------------------------
PASO 1 — Extraer los archivos:
  Abre una terminal (clic derecho en el escritorio -> "Abrir terminal",
  o busca "Terminal" en tu menu de aplicaciones) y escribe:

       tar -xzf ingeconverter-vX.Y.Z-linux-x86_64.tar.gz
       cd ingeconverter-vX.Y.Z-linux-x86_64

  (Reemplaza "vX.Y.Z" por la version que descargaste, por ej. v0.2.0)

PASO 2 — Instalar:
  En la misma terminal, escribe:

       ./install.sh

  Esto copia el programa a tu carpeta personal. No necesitas permisos
  de administrador (no usa "sudo").

PASO 3 — Abrir:
  Busca "IngeConverter" en tu menu de aplicaciones, o escribe en la
  terminal:

       ingeconverter


Requisito previo: instalar Docker
-----------------------------------
IngeConverter necesita un programa llamado "Docker" para funcionar.
Docker es gratuito y se instala una sola vez.

QUE ES DOCKER?
  Docker es un programa que permite correr otros programas dentro de
  un "contenedor" aislado. IngeConverter lo usa para correr el motor de
  base de datos de Microsoft (SQL Server), que es el que lee los archivos
  .S2K de S10. No necesitas saber nada mas de Docker — IngeConverter
  lo maneja automaticamente por ti.

COMO INSTALAR DOCKER:
  Abre una terminal y escribe estos comandos uno por uno. Cuando el
  sistema te pida tu contrasena, escribela (no se ve mientras la
  tecleas, eso es normal):

  En Ubuntu, Linux Mint o Debian:

       sudo apt install docker.io
       sudo usermod -aG docker $USER

  En Fedora:

       sudo dnf install docker
       sudo systemctl enable --now docker
       sudo usermod -aG docker $USER

  Que hacen estos comandos?
    - "sudo apt install docker.io" = instala Docker
    - "sudo usermod -aG docker $USER" = te da permiso para usar Docker
    - "sudo systemctl enable --now docker" = activa Docker (solo Fedora)

PASO OBLIGATORIO DESPUES DE INSTALAR:
  Debes CERRAR TU SESION del sistema operativo y volver a entrar.
  No basta con cerrar la terminal — tienes que cerrar sesion completa
  (o reiniciar el equipo). Esto es para que el permiso de Docker
  se active.

COMO VERIFICAR QUE TODO FUNCIONA:
  Abre una terminal y escribe:

       docker version

  Si aparece un texto con numeros de version (como "Server: 24.0.5..."),
  todo esta correcto. Si dice "permission denied" o "command not found",
  revisa los pasos anteriores.

PRIMERA CONVERSION — DESCARGA AUTOMATICA:
  La primera vez que conviertas un archivo .S2K, IngeConverter descargara
  automaticamente el motor de base de datos de Microsoft (~2.3 GB).
  Esto tarda unos minutos dependiendo de tu internet, pero solo ocurre
  una vez. Las conversiones siguientes tardan unos 20 segundos.


Limitaciones
------------
- Backups muy antiguos de S10 (de la epoca de SQL Server 7.0 o 2000,
  anteriores a S10 2005) no se pueden restaurar. Si tienes un backup
  asi, abrelo en una version moderna de S10 y vuelve a exportarlo.


Licencia
--------
Ver LICENSE.txt en este mismo directorio.

Contacto
--------
Ing. Marco Sumari Tellez — ing.sumari@gmail.com
