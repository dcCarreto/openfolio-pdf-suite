#!/usr/bin/env bash
# Baixa o codigo-fonte das bibliotecas GPL e LGPL que vao no app e junta num .tar, que o
# workflow anexa a release: a GPL pede oferecer o fonte, e oferece-lo no mesmo lugar do
# binario cumpre isso.
#
# A lista (build/third-party/sources.txt) sai do build do PyInstaller
# (packaging/pyinstaller/third_party.py): URLs no Windows (MSYS2) e no macOS (Homebrew),
# pacote=versao no Linux (do Launchpad). Rodar a partir da raiz do repositorio:
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

# Linux: pacote=versao vem do Launchpad, que guarda todas as versoes publicadas no Ubuntu
# (tambem as do pocket de seguranca). O apt-get source dependia do espelho da VM, que as vezes
# ainda nao tem o indice de fontes da versao instalada ("Can not find version").
launchpad_source() {
  local name="${1%%=*}" version="${1#*=}"
  local base="https://launchpad.net/ubuntu/+archive/primary/+files"
  local dsc="${name}_${version#*:}.dsc"  # os nomes de arquivo nao levam a epoca ("1:")
  curl -fsSLO --retry 3 "$base/$dsc"
  # O .dsc lista os outros arquivos com o SHA-256 de cada um: baixa e confere.
  awk '/^Checksums-Sha256:/{f=1;next} /^[^ ]/{f=0} f{print $1 "  " $3}' "$dsc" > "$dsc.sha256"
  while read -r _sum file; do
    curl -fsSLO --retry 3 "$base/$file"
  done < "$dsc.sha256"
  sha256sum -c --quiet "$dsc.sha256"
  rm "$dsc.sha256"
}

while read -r source; do
  if [ "$PLATFORM" = linux ]; then
    launchpad_source "$source"
  else
    curl -fsSLO "$source"
  fi
done < "$LIST"

tar -cf "$OUT_DIR/OpenFolioPDFSuite-codigo-fonte-$PLATFORM.tar" ./*
echo "codigo-fonte em $OUT_DIR/OpenFolioPDFSuite-codigo-fonte-$PLATFORM.tar"
