#!/usr/bin/env bash
# IngeConverter — instalador para Linux.
#
# Copia el binario y registra el .desktop + ícono en el escritorio del
# usuario actual (no requiere sudo). Si querés instalación global del sistema
# (todos los usuarios), pasá --system y corré con sudo.

set -e

MODE="user"
if [[ "${1:-}" == "--system" ]]; then
    MODE="system"
fi

if [[ "$MODE" == "system" ]]; then
    [[ "$EUID" -ne 0 ]] && { echo "Error: --system requiere sudo." >&2; exit 1; }
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor"
else
    BIN_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons/hicolor"
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Instalando IngeConverter ($MODE) …"
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR/256x256/apps" "$ICON_DIR/scalable/apps"

# 1. Binario
install -m 755 "$HERE/ingeconverter" "$BIN_DIR/ingeconverter"
echo "  ✓ Binario en $BIN_DIR/ingeconverter"

# 2. Íconos en jerarquía hicolor
install -m 644 "$HERE/ingeconverter.png"     "$ICON_DIR/scalable/apps/ingeconverter.png"
install -m 644 "$HERE/ingeconverter_256.png" "$ICON_DIR/256x256/apps/ingeconverter.png"
echo "  ✓ Íconos en $ICON_DIR/{scalable,256x256}/apps/"

# 3. .desktop con path real al binario
DESKTOP_FILE="$DESKTOP_DIR/ingeconverter.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=IngeConverter
GenericName=Convertidor S10
GenericName[es]=Convertidor S10
Comment=Convierte bases nativas de S10 (.S2K/.bak/.bkf) al formato de IngePresupuestos
Comment[es]=Convierte bases nativas de S10 (.S2K/.bak/.bkf) al formato de IngePresupuestos
Exec=$BIN_DIR/ingeconverter
Icon=ingeconverter
StartupWMClass=ingeconverter
StartupNotify=true
Categories=Office;Engineering;Utility;
Keywords=S10;presupuesto;ACU;S2K;BAK;BKF;convertidor;
Terminal=false
EOF
chmod 644 "$DESKTOP_FILE"
echo "  ✓ .desktop en $DESKTOP_FILE"

# 4. Refrescar caches del escritorio (best-effort, no críticos)
command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
command -v gtk-update-icon-cache   >/dev/null && gtk-update-icon-cache   "$ICON_DIR" 2>/dev/null || true

cat <<EOF

✓ IngeConverter instalado correctamente.

Cómo abrirlo:
  - Desde el menú de aplicaciones de tu distribución (puede que tengas
    que cerrar sesión y volver a entrar la primera vez).
  - Desde terminal:   $BIN_DIR/ingeconverter

Requisito: Docker debe estar instalado. IngeConverter te guía si falta.

Para desinstalar:
  rm $BIN_DIR/ingeconverter
  rm $DESKTOP_FILE
  rm $ICON_DIR/scalable/apps/ingeconverter.png
  rm $ICON_DIR/256x256/apps/ingeconverter.png
EOF
