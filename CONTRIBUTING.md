# Contribuindo

1. Abra uma issue descrevendo o problema ou a proposta antes de enviar um PR grande.
2. Faça um fork e crie uma branch a partir de `desenvolvimento`, onde o trabalho é integrado;
   `main` só recebe o que vai ser publicado como atualização (ver [RELEASING.md](RELEASING.md)).
3. Mantenha os commits pequenos e com mensagens objetivas.
4. Abra o PR para `desenvolvimento`, descrevendo o que foi alterado e por quê. Se a mudança
   for visível para quem usa o app, acrescente-a em "Próxima atualização" no
   [CHANGELOG.md](CHANGELOG.md).

## Padrões de código

- Python 3.10+.
- Funções e classes novas devem ter docstring curta.
- Testes ficam em `tests/`.
- Antes do PR, rode o que o CI confere:

  ```bash
  pip install -c requirements-lock.txt -e ".[test,lint]"
  ruff check .   # bugs comuns (nomes indefinidos, imports sem uso, armadilhas do flake8-bugbear)
  mypy           # tipos de core/ e ui/ (configuração no pyproject.toml)
  pytest
  pytest --cov   # opcional: lista os arquivos com linhas sem teste, dos menos cobertos
  ```

- As versões exatas das dependências ficam no `requirements-lock.txt`, que o CI e os builds
  de release usam (`-c`: ele só fixa versões, quem diz o que instalar é o `pyproject.toml`).
  Ao mudar as dependências do `pyproject.toml`, ou para trazer versões novas, gere o lock de
  novo com o [uv](https://docs.astral.sh/uv/) e rode os testes antes do commit:

  ```bash
  uv pip compile pyproject.toml --universal --python-version 3.10 --extra test --extra build --extra lint -o requirements-lock.txt --upgrade
  ```

  Sem `--upgrade`, o uv mantém as versões que já estão no lock e só resolve o que mudou.

- O app não chama nenhum programa instalado, exceto o Tesseract no OCR, e os instaladores
  levam uma cópia dele (`packaging/fetch_tessdata.py` baixa os idiomas antes do PyInstaller).
  Não acrescente dependência de programa externo: o que o app faz precisa funcionar só com
  o que vem no instalador.
- Os testes com o Tesseract de verdade rodam quando ele está instalado e são pulados quando
  não está (os mesmos caminhos também têm testes com o programa simulado). No CI ele é
  instalado e `OPENFOLIO_REQUIRE_PROGRAMS=1` faz a falta dele reprovar o teste em vez de
  pulá-lo.
