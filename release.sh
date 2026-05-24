#!/usr/bin/env bash
# Release de IngeConverter: commit, tag, push → GitHub Actions compila.
#
# Uso:
#   ./release.sh 0.1.0
#
# Esto hace:
#   1. Valida que estés en main sin cambios pendientes
#   2. Crea tag v0.1.0
#   3. Push a origin (tag + main)
#   4. GitHub Actions compila Linux + Windows automáticamente
#   5. Los binarios aparecen en Releases

set -e
cd "$(dirname "$0")"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    echo "Uso: ./release.sh X.Y.Z"
    echo "Ejemplo: ./release.sh 0.1.0"
    exit 1
fi

# Validar formato semver
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "ERROR: versión '$VERSION' no es semver válido (X.Y.Z)"
    exit 1
fi

TAG="v$VERSION"

# Validar rama
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "ERROR: debes estar en la rama 'main' (estás en '$BRANCH')"
    exit 1
fi

# Validar sin cambios pendientes
if ! git diff --quiet HEAD 2>/dev/null; then
    echo "ERROR: hay cambios sin commitear. Haz commit primero."
    exit 1
fi

# Validar tag no existe
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "ERROR: el tag $TAG ya existe"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  IngeConverter — Release $TAG"
echo "═══════════════════════════════════════════════"
echo ""
echo "  Rama:   $BRANCH"
echo "  Tag:    $TAG"
echo "  Commit: $(git log --oneline -1)"
echo ""
read -p "¿Continuar? (s/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "Cancelado."
    exit 0
fi

echo "▸ Creando tag $TAG…"
git tag -a "$TAG" -m "Release $TAG"

echo "▸ Push a origin…"
git push origin main --tags

echo ""
echo "✓ Release $TAG publicado."
echo ""
echo "GitHub Actions ahora está compilando los binarios."
echo "Revisa el progreso en:"
echo "   https://github.com/tuxiasumari/ingeconverter/actions"
echo ""
echo "Cuando termine, los archivos estarán en:"
echo "   https://github.com/tuxiasumari/ingeconverter/releases/tag/$TAG"
