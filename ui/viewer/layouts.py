"""Layouts das páginas (A15). Página dupla e livro são a rolagem contínua com duas páginas
por linha; no livro a capa fica sozinha, e as páginas pares à esquerda, como impressas.

Num módulo à parte para o menu Exibir da janela não precisar carregar o visualizador (e o que
ele importa) antes de abrir um documento."""

SINGLE = "single"
CONTINUOUS = "continuous"
DOUBLE = "double"
BOOK = "book"
LAYOUTS = (SINGLE, CONTINUOUS, DOUBLE, BOOK)
