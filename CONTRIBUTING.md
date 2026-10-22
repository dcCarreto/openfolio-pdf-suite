# Contribuindo

1. Abra uma issue descrevendo o problema ou a proposta antes de enviar um PR grande.
2. Faça um fork e crie uma branch a partir de `main`.
3. Mantenha os commits pequenos e com mensagens objetivas.
4. Abra o PR descrevendo o que foi alterado e por quê.

## Padrões de código

- Python 3.10+.
- Funções e classes novas devem ter docstring curta.
- Testes ficam em `tests/`.
- Antes do PR, rode o que o CI confere:

  ```bash
  pip install -e ".[test,lint]"
  ruff check .   # bugs comuns (nomes indefinidos, imports sem uso, armadilhas do flake8-bugbear)
  mypy           # tipos de core/ e ui/ (configuração no pyproject.toml)
  pytest
  pytest --cov   # opcional: lista os arquivos com linhas sem teste, dos menos cobertos
  ```

- O app não chama nenhum programa instalado, exceto o Tesseract no OCR, e os instaladores
  levam uma cópia dele (`packaging/fetch_tessdata.py` baixa os idiomas antes do PyInstaller).
  Não acrescente dependência de programa externo: o que o app faz precisa funcionar só com
  o que vem no instalador.
- Os testes com o Tesseract de verdade rodam quando ele está instalado e são pulados quando
  não está (os mesmos caminhos também têm testes com o programa simulado). No CI ele é
  instalado e `OPENFOLIO_REQUIRE_PROGRAMS=1` faz a falta dele reprovar o teste em vez de
  pulá-lo.
