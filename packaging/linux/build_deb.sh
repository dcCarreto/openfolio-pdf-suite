#!/usr/bin/env bash
# Monta um pacote .deb a partir do build "onedir" do PyInstaller.
#
# Espera que dist/OpenFolioPDFSuite ja exista (gerado por:
#   pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
# ), rodando a partir da raiz do repositorio:
#   bash packaging/linux/build_deb.sh [versao]
set -euo pipefail

VERSION="${1:-0.0.0-dev}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/OpenFolioPDFSuite"
PKG_DIR="$ROOT_DIR/dist/deb/openfolio-pdf-suite"
OUT_DIR="$ROOT_DIR/dist/installer"

# Versoes debian nao usam "-beta.N" da mesma forma que semver; troca por "~betaN"
# pra continuar comparavel pelo dpkg (~ ordena antes da versao final correspondente).
DEB_VERSION="$(echo "$VERSION" | sed -E 's/-beta\.?([0-9]+)?/~beta\1/')"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN" \
         "$PKG_DIR/opt/openfolio-pdf-suite" \
         "$PKG_DIR/usr/bin" \
         "$PKG_DIR/usr/share/applications" \
         "$PKG_DIR/usr/share/icons/hicolor/256x256/apps" \
         "$OUT_DIR"

cp -r "$DIST_DIR"/* "$PKG_DIR/opt/openfolio-pdf-suite/"
chmod +x "$PKG_DIR/opt/openfolio-pdf-suite/OpenFolioPDFSuite"

ln -sf ../../opt/openfolio-pdf-suite/OpenFolioPDFSuite "$PKG_DIR/usr/bin/openfolio-pdf-suite"

cp "$ROOT_DIR/packaging/linux/openfolio-pdf-suite.desktop" \
   "$PKG_DIR/usr/share/applications/openfolio-pdf-suite.desktop"
cp "$ROOT_DIR/packaging/icons/icon_256.png" \
   "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/openfolio-pdf-suite.png"

INSTALLED_SIZE_KB="$(du -sk "$PKG_DIR/opt/openfolio-pdf-suite" | cut -f1)"

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: openfolio-pdf-suite
Version: $DEB_VERSION
Section: office
Priority: optional
Architecture: amd64
Installed-Size: $INSTALLED_SIZE_KB
Maintainer: dcCarreto <https://github.com/dcCarreto>
Homepage: https://github.com/dcCarreto/openfolio-pdf-suite
Description: Suite completa e open source de manipulacao de PDF
 Aplicativo desktop para mesclar, dividir, comprimir, proteger, converter,
 anotar, reconhecer texto (OCR), redigir/sanitizar e assinar PDFs, 100% local.
EOF

dpkg-deb --build --root-owner-group "$PKG_DIR" "$OUT_DIR/openfolio-pdf-suite_${DEB_VERSION}_amd64.deb"

echo "Pacote .deb gerado em $OUT_DIR/openfolio-pdf-suite_${DEB_VERSION}_amd64.deb"
