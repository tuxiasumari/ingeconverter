IngeConverter — Convertidor de S10 a IngePresupuestos
=====================================================

¿Qué es esto?
-------------
Convierte bases de datos nativas de S10 (archivos .S2K, .bak o .bkf) a
archivos .db de IngePresupuestos. Es un complemento gratuito de
IngePresupuestos.

Cómo instalar (Linux)
---------------------
1. Extraé este tarball:
       tar -xzf ingeconverter-vX.Y.Z-linux-x86_64.tar.gz
       cd ingeconverter-vX.Y.Z-linux-x86_64

2. Ejecutá el instalador (solo tu usuario, no requiere sudo):
       ./install.sh

   Para instalación global del sistema (todos los usuarios):
       sudo ./install.sh --system

3. Abrí IngeConverter desde el menú de aplicaciones, o ejecutá:
       ingeconverter

Requisito previo
----------------
Docker debe estar instalado. Si no lo tenés, la propia aplicación te muestra
las instrucciones cuando arranca.

Ubuntu/Debian:  sudo apt install docker.io
Fedora:         sudo dnf install docker
Asegurate de que tu usuario esté en el grupo docker:
       sudo usermod -aG docker $USER
       (cerrá sesión y volvé a entrar)

La primera vez que uses IngeConverter, va a descargar la imagen oficial de
Microsoft SQL Server 2022 (~2.3 GB). Esa descarga es una sola vez.

Limitaciones
------------
- Backups muy antiguos de S10 (SQL Server 7.0 o 2000, pre-2005) no se
  pueden restaurar en SQL Server 2022. Reexportá el backup desde una
  versión moderna de S10.

Licencia
--------
Ver LICENSE.txt en este mismo directorio.

Contacto
--------
Ing. Marco Sumari Tellez — ing.sumari@gmail.com
