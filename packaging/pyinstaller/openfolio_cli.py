"""O comando `openfolio` no app empacotado: o mesmo de `pip install` (core/cli.py), num
executável de console ao lado do app, que é de janela e não escreve no terminal."""

import sys

from core.cli import main

sys.exit(main())
