from reportlab import rl_config

# O reportlab grava imagens e streams codificados em ASCII85 por padrão, o que soma 25% ao
# tamanho de cada imagem sem nenhum ganho num arquivo binário (páginas achatadas da redação,
# imagens convertidas em PDF, conversão do Office).
rl_config.useA85 = 0
