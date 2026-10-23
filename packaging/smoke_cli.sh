#!/usr/bin/env bash
# Teste de fumaca do comando openfolio empacotado (packaging/pyinstaller/openfolio_cli.py):
# numera as paginas de um PDF (usa as fontes que vao dentro do app) e le as propriedades.
#
#   bash packaging/smoke_cli.sh dist/OpenFolioPDFSuite/openfolio
set -euo pipefail

CLI="$1"
WORK=dist/smoke-cli  # relativo: no Windows, o Python nao entende os caminhos /tmp do bash
rm -rf "$WORK"
mkdir -p "$WORK"
python -c "from pypdf import PdfWriter; w = PdfWriter(); w.add_blank_page(width=200, height=200); w.write('$WORK/entrada.pdf')"

"$CLI" number "$WORK/entrada.pdf" -o "$WORK/numerado.pdf"
"$CLI" info "$WORK/numerado.pdf" --json | python -c "import json, sys; assert json.load(sys.stdin)['page_count'] == 1"
echo "openfolio empacotado ok"
