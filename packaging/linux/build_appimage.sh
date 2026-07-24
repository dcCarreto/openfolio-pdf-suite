#!/usr/bin/env bash
# Monta um AppImage a partir do build "onedir" do PyInstaller.
#
# Espera que dist/OpenFolioPDFSuite ja exista (gerado por:
#   pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
# ), rodando a partir da raiz do repositorio:
#   bash packaging/linux/build_appimage.sh [versao]
set -euo pipefail

VERSION="${1:-0.0.0-dev}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/OpenFolioPDFSuite"
APPDIR="$ROOT_DIR/dist/AppDir"
OUT_DIR="$ROOT_DIR/dist/installer"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$OUT_DIR"

cp -r "$DIST_DIR"/* "$APPDIR/usr/bin/"
chmod +x "$APPDIR/usr/bin/OpenFolioPDFSuite"

cp "$ROOT_DIR/packaging/linux/openfolio-pdf-suite.desktop" "$APPDIR/openfolio-pdf-suite.desktop"
cp "$ROOT_DIR/packaging/icons/icon_256.png" "$APPDIR/openfolio-pdf-suite.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/OpenFolioPDFSuite" "$@"
EOF
chmod +x "$APPDIR/AppRun"

APPIMAGETOOL="$ROOT_DIR/dist/appimagetool.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
  curl -L -o "$APPIMAGETOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

# --appimage-extract-and-run evita depender de FUSE, que normalmente nao esta
# disponivel em runners de CI.
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run \
  "$APPDIR" "$OUT_DIR/OpenFolioPDFSuite-$VERSION-x86_64.AppImage"

echo "AppImage gerado em $OUT_DIR/OpenFolioPDFSuite-$VERSION-x86_64.AppImage"
