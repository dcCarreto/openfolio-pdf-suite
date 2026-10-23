#!/usr/bin/env bash
# Baixa o codigo-fonte das bibliotecas GPL e LGPL que vao no app e junta num .tar, que o
# workflow anexa a release: a GPL pede oferecer o fonte, e oferece-lo no mesmo lugar do
# binario cumpre isso.
#
# A lista (build/third-party/sources.txt) sai do build do PyInstaller
# (packaging/pyinstaller/third_party.py): URLs no Windows (MSYS2) e no macOS (Homebrew),
# pacote=versao no Linux (apt-get source). Rodar a partir da raiz do repositorio:
#   bash packaging/fetch_sources.sh windows|linux|macos
set -euo pipefail

PLATFORM="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST="$ROOT_DIR/build/third-party/sources.txt"
OUT_DIR="$ROOT_DIR/dist/installer"
STAGING="$ROOT_DIR/dist/sources-staging"

if [ ! -s "$LIST" ]; then
  echo "Nenhuma biblioteca GPL ou LGPL no app."
  exit 0
fi

mkdir -p "$OUT_DIR"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cd "$STAGING"

if [ "$PLATFORM" = linux ]; then
  # As VMs do GitHub vem sem os repositorios de fonte (deb-src) ligados.
  sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
  sudo apt-get update -qq
fi
while read -r source; do
  if [ "$PLATFORM" = linux ]; then
    apt-get source --download-only "$source"
  else
    curl -fsSLO "$source"
  fi
done < "$LIST"

tar -cf "$OUT_DIR/OpenFolioPDFSuite-codigo-fonte-$PLATFORM.tar" ./*
echo "codigo-fonte em $OUT_DIR/OpenFolioPDFSuite-codigo-fonte-$PLATFORM.tar"
