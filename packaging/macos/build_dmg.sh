#!/usr/bin/env bash
# Monta um .dmg a partir do bundle .app gerado pelo PyInstaller.
#
# Espera que dist/OpenFolioPDFSuite.app ja exista (gerado por:
#   pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
# ), rodando a partir da raiz do repositorio:
#   bash packaging/macos/build_dmg.sh [versao]
#
# O app nao e assinado nem notarizado (exigiria uma conta paga de
# desenvolvedor Apple) - o macOS vai bloquear a primeira execucao via
# Gatekeeper. Isso e esperado numa build beta; instrucoes de como abrir
# mesmo assim ficam no README/release notes.
set -euo pipefail

VERSION="${1:-0.0.0-dev}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="$ROOT_DIR/dist/OpenFolioPDFSuite.app"
OUT_DIR="$ROOT_DIR/dist/installer"
STAGING="$ROOT_DIR/dist/dmg-staging"

mkdir -p "$OUT_DIR"
rm -rf "$STAGING"
mkdir -p "$STAGING"

cp -R "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create -volname "OpenFolio PDF Suite" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  "$OUT_DIR/OpenFolioPDFSuite-$VERSION.dmg"

echo "dmg gerado em $OUT_DIR/OpenFolioPDFSuite-$VERSION.dmg"
