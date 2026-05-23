#!/usr/bin/env bash
# Empaqueta IngeConverter como tarball Linux distribuible.
#
# Output:
#   dist/ingeconverter-vX.Y.Z-linux-x86_64.tar.gz
#
# El tarball contiene:
#   - ingeconverter            (binario PyInstaller standalone, ~72 MB)
#   - install.sh               (instalador)
#   - README.txt
#   - LICENSE.txt
#   - ingeconverter.png        (ícono escalable)
#   - ingeconverter_256.png    (ícono fijo)
#
# Uso:
#   ./dist-linux.sh                    # toma version del git tag o de VERSION
#   ./dist-linux.sh 0.1.0              # versión explícita

set -e
cd "$(dirname "$0")"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    if git describe --tags --abbrev=0 >/dev/null 2>&1; then
        VERSION="$(git describe --tags --abbrev=0 | sed 's/^v//')"
    else
        VERSION="0.1.0"
        echo "ℹ Sin git tag; usando versión por defecto $VERSION"
    fi
fi

NAME="ingeconverter-v${VERSION}-linux-x86_64"
STAGING="dist/$NAME"
TARBALL="dist/$NAME.tar.gz"

echo "▸ Empaquetando IngeConverter v$VERSION para Linux x86_64"

# 1. Buildear binario si no existe o está desactualizado
if [[ ! -x dist/ingeconverter || dist/ingeconverter -ot main.py ]]; then
    echo "▸ Buildeando binario con PyInstaller…"
    venv/bin/pyinstaller ingeconverter.spec --noconfirm >/dev/null
fi

# 2. Crear directorio de staging
rm -rf "$STAGING"
mkdir -p "$STAGING"

# 3. Copiar archivos
cp dist/ingeconverter                       "$STAGING/ingeconverter"
cp dist-template/install.sh                 "$STAGING/install.sh"
cp dist-template/README.txt                 "$STAGING/README.txt"
cp LICENSE.txt                              "$STAGING/LICENSE.txt"
cp resources/icons/ingeconverter.png        "$STAGING/ingeconverter.png"
cp resources/icons/ingeconverter_256.png    "$STAGING/ingeconverter_256.png"

chmod 755 "$STAGING/ingeconverter" "$STAGING/install.sh"
chmod 644 "$STAGING/README.txt" "$STAGING/LICENSE.txt" \
          "$STAGING/ingeconverter.png" "$STAGING/ingeconverter_256.png"

# 4. Tar.gz
rm -f "$TARBALL"
tar -czf "$TARBALL" -C dist "$NAME"
SIZE=$(du -h "$TARBALL" | cut -f1)

echo ""
echo "✓ $TARBALL  ($SIZE)"
echo ""
echo "Próximos pasos:"
echo "  1. Subir el archivo a Cloudflare R2:"
echo "       downloads.ingepresupuestos.com/ingeconverter/v$VERSION/linux/$NAME.tar.gz"
echo "  2. Actualizar DOWNLOAD_URL en"
echo "       ~/ingepresupuestos-pyside6/core/ingeconverter_bridge.py"
