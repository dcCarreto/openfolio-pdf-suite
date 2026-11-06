import os
import sys

# O reportlab grava imagens e streams codificados em ASCII85 por padrão, o que soma 25% ao
# tamanho de cada imagem sem nenhum ganho num arquivo binário (páginas achatadas da redação,
# imagens convertidas em PDF, conversão do Office).
#
# Pela variável de ambiente que o reportlab lê ao carregar: importá-lo aqui só para mudar a
# opção custava ~40 ms na abertura do app, antes de qualquer PDF precisar dele.
if "reportlab.rl_config" in sys.modules:
    sys.modules["reportlab.rl_config"].useA85 = 0  # type: ignore[attr-defined]
else:
    os.environ.setdefault("RL_useA85", "0")
