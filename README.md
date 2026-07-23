<p align="center">
  <img src="assets/icon.png" alt="OpenFolio PDF Suite" width="120">
</p>

<h1 align="center">OpenFolio PDF Suite</h1>

<p align="center">
  Suite completa e open source de manipulação de PDF, 100% local, sem paywall.<br>
  Interface em modo escuro, inspirada no macOS, com 15 ferramentas de PDF em um só lugar.
</p>

---

## Índice

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Demonstração](#demonstração)
  - [Mesclando arquivos](#mesclando-arquivos)
  - [Comprimindo um PDF](#comprimindo-um-pdf)
  - [Marca d'água](#marca-dágua)
  - [Campos de formulário](#campos-de-formulário)
- [Requisitos](#requisitos)
- [Como instalar](#como-instalar)
- [Como rodar](#como-rodar)
- [Tecnologias utilizadas](#tecnologias-utilizadas)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Testes](#testes)
- [Contribuição](#contribuição)
- [Licença](#licença)

## Visão geral

O OpenFolio PDF Suite é um aplicativo desktop (Windows/Linux/macOS, via PySide6) que reúne as
operações de PDF mais comuns — mesclar, dividir, comprimir, proteger, converter, preencher — sem
depender de ferramentas online, sem enviar seus arquivos para servidor nenhum e sem paywall.
Tudo roda localmente, na sua máquina.

<p align="center">
  <img src="assets/screenshots/01-visao-geral.png" alt="Janela principal do OpenFolio PDF Suite, mostrando a aba Mesclar" width="720">
</p>

A navegação é feita por uma barra lateral com ícone e descrição de cada ferramenta; cada seção
tem seus próprios campos de entrada/saída e botão de ação.

## Funcionalidades

| Seção | O que faz |
| --- | --- |
| 🆕 Criar PDF | Cria um novo PDF em branco, com uma ou mais páginas, no tamanho que você escolher |
| 📄 Mesclar | Combina vários PDFs em um único arquivo, na ordem que você definir |
| ✂️ Dividir | Separa um PDF em vários arquivos menores (uma ou N páginas por arquivo) |
| 🔃 Páginas | Rotaciona, reordena ou remove páginas de um PDF |
| 🗜️ Comprimir | Reduz o tamanho de um PDF recomprimindo conteúdo e removendo objetos duplicados |
| 🖼️ Converter | Converte páginas de PDF em imagens, ou um conjunto de imagens em um PDF |
| 💧 Marca d'água | Adiciona um texto de marca d'água (opacidade, tamanho e rotação configuráveis) |
| 🔒 Proteger | Protege um PDF com senha (AES-256), ou remove a senha de um PDF protegido |
| 🏷️ Metadados | Lê e edita título, autor, assunto e palavras-chave de um PDF |
| 🔢 Numeração | Adiciona números de página no rodapé, com página inicial configurável |
| 📝 Extrair texto | Extrai todo o texto de um PDF para um arquivo `.txt` |
| 📷 Extrair imagens | Extrai as imagens embutidas nas páginas de um PDF, em seus formatos originais |
| 📐 Cortar/Redimensionar | Corta margens ou redimensiona as páginas de um PDF para um novo tamanho |
| 🔖 Marcadores | Monta um sumário de navegação (outline) com título e página de destino |
| 🧾 Campos de formulário | Adiciona campos de formulário **interativos** (texto ou caixa de seleção) — o PDF resultante é preenchível em qualquer leitor |

## Demonstração

As capturas abaixo foram feitas rodando a aplicação de verdade: arquivos de exemplo reais são
mesclados, comprimidos e processados, e os resultados (tamanho de arquivo, mensagens de sucesso)
vêm da execução real das operações — não são mockups.

### Mesclando arquivos

Três relatórios mensais são adicionados à lista, na ordem em que devem aparecer no PDF final, e
um arquivo de saída é escolhido:

<p align="center">
  <img src="assets/screenshots/02-mesclar-arquivos.png" alt="Aba Mesclar com três PDFs carregados e arquivo de saída definido" width="720">
</p>

Ao clicar em **Mesclar**, os três arquivos são combinados em um único PDF de verdade:

<p align="center">
  <img src="assets/screenshots/03-mesclar-sucesso.png" alt="Mensagem de sucesso após mesclar os PDFs">
</p>

### Comprimindo um PDF

Um contrato de 25 páginas é escolhido como entrada:

<p align="center">
  <img src="assets/screenshots/04-comprimir-config.png" alt="Aba Comprimir com arquivo de entrada e saída definidos" width="720">
</p>

O resultado mostra o tamanho real antes e depois da compressão:

<p align="center">
  <img src="assets/screenshots/05-comprimir-sucesso.png" alt="Mensagem de sucesso mostrando reducao de 22.5 KB para 18.8 KB">
</p>

### Marca d'água

Texto, opacidade, tamanho de fonte e rotação são configuráveis antes de aplicar sobre todas as
páginas do PDF:

<p align="center">
  <img src="assets/screenshots/06-marca-dagua.png" alt="Aba Marca d'água configurada com o texto CONFIDENCIAL" width="720">
</p>

### Campos de formulário

Diferente de um texto carimbado na página, esta ferramenta cria um campo **AcroForm** de
verdade: o PDF resultante pode ser aberto em qualquer leitor (Adobe Reader, navegador, etc.) e o
campo pode ser clicado e preenchido normalmente.

<p align="center">
  <img src="assets/screenshots/07-campos-formulario.png" alt="Aba Campos de formulário configurada para adicionar um campo de texto" width="720">
</p>

## Requisitos

- Python 3.10 ou superior
- Windows, Linux ou macOS (interface gráfica via PySide6/Qt)

## Como instalar

```bash
git clone https://github.com/dcCarreto/openfolio-pdf-suite.git
cd openfolio-pdf-suite
pip install -e .
```

Isso instala o pacote em modo editável junto com todas as dependências (`pypdf`, `PySide6`,
`pypdfium2`, `Pillow`, `reportlab`, `cryptography`).

## Como rodar

```bash
python main.py
```

A janela principal abre em modo escuro, com a aba **Mesclar** selecionada por padrão. Basta
escolher a ferramenta desejada na barra lateral.

## Tecnologias utilizadas

| Biblioteca | Uso |
| --- | --- |
| [pypdf](https://pypdf.readthedocs.io/) | Leitura, escrita e manipulação de PDFs (base de quase todas as operações) |
| [PySide6](https://doc.qt.io/qtforpython/) | Interface gráfica (Qt para Python) |
| [pypdfium2](https://pypdfium2.readthedocs.io/) | Renderização de páginas PDF em imagens (conversão PDF → imagem) |
| [Pillow](https://pillow.readthedocs.io/) | Leitura/escrita de imagens (conversão imagem → PDF, extração de imagens) |
| [reportlab](https://www.reportlab.com/) | Geração de conteúdo vetorial (marca d'água, numeração de página, campos de formulário) |
| [cryptography](https://cryptography.io/) | Criptografia AES-256 usada na proteção por senha (via `pypdf[crypto]`) |

## Estrutura do projeto

```text
core/            Lógica de manipulação de PDF, sem nenhuma dependência de UI
  base.py          Classe base PDFOperation
  merge.py, split.py, pages.py, compress.py, convert.py, ...

ui/              Interface gráfica (PySide6)
  main_window.py   Janela principal: monta a sidebar e as 15 seções
  theme.py         Tema escuro único, inspirado no macOS
  icon.py          Ícone da aplicação (renderizado a partir de assets/logo.svg)
  pages/           Uma classe de página por ferramenta (MergePage, CompressPage, ...)
  widgets/         Widgets reutilizáveis (FilePicker, FileListEditor, PageContainer)

tests/           Testes pytest (um arquivo por operação de core, + teste de fumaça da UI)

assets/          Ícone/logo da aplicação e screenshots usados neste README
```

Cada operação em `core/` é independente da UI: pode ser usada diretamente em um script Python,
sem precisar abrir a interface gráfica. Por exemplo:

```python
from core.merge import MergePDF

MergePDF().run(
    ["relatorio_janeiro.pdf", "relatorio_fevereiro.pdf"],
    "relatorios_consolidados.pdf",
)
```

## Testes

```bash
pip install -e ".[test]"
pytest
```

Todos os módulos de `core/` têm testes cobrindo o comportamento esperado, e há um teste de
fumaça que garante que a janela principal monta todas as seções sem erros.

## Contribuição

Contribuições são bem-vindas. Veja [CONTRIBUTING.md](CONTRIBUTING.md) para mais detalhes.

## Licença

Distribuído sob a licença [MIT](LICENSE).
