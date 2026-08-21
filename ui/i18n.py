"""Sistema de tradução da interface: português do Brasil (idioma-fonte, padrão) e inglês.

O texto em português usado nos widgets é a própria chave de tradução: `tr(texto)`
retorna o texto sem alterações quando o idioma ativo é PT_BR, e procura a
tradução em inglês em `_EN_TRANSLATIONS` quando o idioma ativo é EN_US
(retornando o próprio texto original se não houver tradução cadastrada).
"""

from PySide6.QtCore import QObject, Signal

PT_BR = "pt_BR"
EN_US = "en_US"

_current_language = PT_BR


class _LanguageSignal(QObject):
    changed = Signal()


language_changed = _LanguageSignal()


def get_language() -> str:
    return _current_language


def set_language(language: str) -> None:
    global _current_language
    if language not in (PT_BR, EN_US):
        raise ValueError(f"Idioma inválido: {language}")
    if language == _current_language:
        return
    _current_language = language
    language_changed.changed.emit()


def tr(text: str) -> str:
    """Traduz um texto em português (idioma-fonte) para o idioma ativo."""
    if _current_language == PT_BR:
        return text
    return _EN_TRANSLATIONS.get(text, text)


_EN_TRANSLATIONS: dict[str, str] = {
    # Sidebar sections + subtitles
    "Criar PDF": "Create PDF",
    "Crie um novo PDF em branco, com uma ou mais páginas.": (
        "Create a new blank PDF, with one or more pages."
    ),
    "Mesclar": "Merge",
    "Combine vários PDFs em um único arquivo, na ordem que você escolher.": (
        "Combine multiple PDFs into a single file, in the order you choose."
    ),
    "Dividir": "Split",
    "Separe um PDF em vários arquivos menores.": "Split a PDF into several smaller files.",
    "Páginas": "Pages",
    "Rotacione, reordene ou remova páginas de um PDF.": (
        "Rotate, reorder, or remove pages from a PDF."
    ),
    "Comprimir": "Compress",
    "Reduza o tamanho de um arquivo PDF.": "Reduce the size of a PDF file.",
    "Converter": "Convert",
    "Converta entre PDF e imagens, documentos do Office (Word/Excel/PowerPoint) e XML.": (
        "Convert between PDF and images, Office documents (Word/Excel/PowerPoint), and XML."
    ),
    "Marca d'água": "Watermark",
    "Adicione um texto de marca d'água sobre as páginas de um PDF.": (
        "Add a watermark text over the pages of a PDF."
    ),
    "Proteger": "Protect",
    "Proteja um PDF com senha, ou remova a senha de um PDF protegido.": (
        "Protect a PDF with a password, or remove the password from a protected PDF."
    ),
    "Metadados": "Metadata",
    "Edite título, autor, assunto e palavras-chave de um PDF.": (
        "Edit the title, author, subject, and keywords of a PDF."
    ),
    "Numeração": "Page numbers",
    "Adicione números de página no rodapé de um PDF, ou numeração Bates.": (
        "Add page numbers to the footer of a PDF, or Bates numbering."
    ),
    "PDF/A": "PDF/A",
    "Converta um PDF para uma aproximação de PDF/A (arquivamento) ou valide um existente.": (
        "Convert a PDF to a PDF/A approximation (archiving) or validate an existing one."
    ),
    "Extrair texto": "Extract text",
    "Extraia todo o texto de um PDF para um arquivo .txt.": (
        "Extract all the text from a PDF into a .txt file."
    ),
    "Extrair imagens": "Extract images",
    "Extraia as imagens embutidas nas páginas de um PDF.": (
        "Extract the images embedded in the pages of a PDF."
    ),
    "Cortar/Redimensionar": "Crop/Resize",
    "Corte margens ou redimensione as páginas de um PDF.": (
        "Crop margins or resize the pages of a PDF."
    ),
    "Editar": "Edit",
    "Substitua imagens embutidas, cubra e reescreva texto, ou adicione/liste/"
    "remova links de um PDF.": (
        "Replace embedded images, cover and rewrite text, or add/list/remove links from a PDF."
    ),
    "Marcadores": "Bookmarks",
    "Monte um sumário de navegação (marcadores) para um PDF.": (
        "Build a navigation outline (bookmarks) for a PDF."
    ),
    "Camadas": "Layers",
    "Liste as camadas (Optional Content Groups) de um PDF e alterne a visibilidade "
    "padrão de cada uma.": (
        "List a PDF's layers (Optional Content Groups) and toggle each one's default "
        "visibility."
    ),
    "Anexos": "Attachments",
    "Liste, adicione, remova ou extraia os anexos embutidos de um PDF.": (
        "List, add, remove, or extract a PDF's embedded attachments."
    ),
    "Campos de formulário": "Form fields",
    "Adicione campos de formulário e grupos de opções, liste os existentes, "
    "exporte/importe dados preenchidos ou achate o formulário.": (
        "Add form fields and radio groups, list existing ones, export/import filled-in "
        "data, or flatten the form."
    ),
    "Acessibilidade": "Accessibility",
    "Verifique um subconjunto de PDF/UA e corrija idioma/título do documento.": (
        "Check a subset of PDF/UA and fix the document's language/title."
    ),
    "Comparar": "Compare",
    "Compare duas versões de um PDF: diff de texto por página ou diff visual.": (
        "Compare two versions of a PDF: per-page text diff or visual diff."
    ),
    # Menu bar / about dialog
    "Arquivo": "File",
    "Sair": "Quit",
    "Ajuda": "Help",
    "Sobre o OpenFolio PDF Suite": "About OpenFolio PDF Suite",
    (
        "<b>OpenFolio PDF Suite</b> — versão {version}<br><br>"
        "Suite completa e open source de manipulação de PDF, 100% local, sem paywall."
    ): (
        "<b>OpenFolio PDF Suite</b> — version {version}<br><br>"
        "Complete, open source PDF manipulation suite, 100% local, no paywall."
    ),
    # Shared widgets: FilePicker / FileListEditor
    "Nenhum arquivo selecionado": "No file selected",
    "Nenhum destino selecionado": "No destination selected",
    "Nenhuma pasta selecionada": "No folder selected",
    "Escolher arquivo": "Choose file",
    "Escolher onde salvar": "Choose where to save",
    "Escolher pasta": "Choose folder",
    "Procurar...": "Browse...",
    "Selecionar arquivo": "Select file",
    "Salvar como": "Save as",
    "Selecionar pasta": "Select folder",
    "Adicionar...": "Add...",
    "Adicionar arquivos à lista": "Add files to the list",
    "Remover selecionado": "Remove selected",
    "Remover o item selecionado da lista": "Remove the selected item from the list",
    "Subir": "Move up",
    "Mover o item selecionado para cima": "Move the selected item up",
    "Descer": "Move down",
    "Mover o item selecionado para baixo": "Move the selected item down",
    # Common strings reused across many pages
    "Arquivo PDF de entrada:": "Input PDF file:",
    "Arquivo de saída:": "Output file:",
    "Pasta de saída:": "Output folder:",
    "Escolha o arquivo de entrada.": "Choose the input file.",
    "Escolha o arquivo de saída.": "Choose the output file.",
    "Escolha a pasta de saída.": "Choose the output folder.",
    "Operação:": "Operation:",
    "Tamanho:": "Size:",
    "Largura:": "Width:",
    "Altura:": "Height:",
    "Salvar": "Save",
    "Página (0 = primeira):": "Page (0 = first):",
    "Carta (Letter)": "Letter",
    "Ofício (Legal)": "Legal",
    "Personalizado": "Custom",
    # Merge
    "Selecionar PDFs": "Select PDFs",
    "Arquivos a mesclar (na ordem desejada):": "Files to merge (in the desired order):",
    "Adicione pelo menos um arquivo.": "Add at least one file.",
    "Falha ao mesclar: {error}": "Failed to merge: {error}",
    "PDFs mesclados com sucesso.": "PDFs merged successfully.",
    # Split
    "Páginas por arquivo:": "Pages per file:",
    "Falha ao dividir: {error}": "Failed to split: {error}",
    "PDF dividido em {count} arquivo(s).": "PDF split into {count} file(s).",
    "Por número de páginas": "By page count",
    "Por marcadores": "By bookmarks",
    "Um arquivo por marcador de nível superior do sumário — cada arquivo vai da "
    "página do marcador até a página anterior ao próximo. Marcadores aninhados "
    "(subtópicos) não geram corte.": (
        "One file per top-level outline bookmark — each file runs from the bookmark's "
        "page up to the page before the next one. Nested bookmarks (sub-topics) don't "
        "cause a cut."
    ),
    "Dividir por marcadores": "Split by bookmarks",
    # Pages (rotate/reorder/remove/insert/replace)
    "Rotacionar": "Rotate",
    "Reordenar": "Reorder",
    "Remover": "Remove",
    "Inserir": "Insert",
    "Substituir": "Replace",
    "PDF com as páginas a inserir:": "PDF with the pages to insert:",
    "Inserir na posição (0 = antes da primeira página):": "Insert at position (0 = before the first page):",
    "PDF com as páginas substitutas:": "PDF with the replacement pages:",
    "Página inicial (inclusive):": "Start page (inclusive):",
    "Página final (exclusive):": "End page (exclusive):",
    "Escolha o PDF de origem das páginas.": "Choose the source PDF for the pages.",
    "Ângulo:": "Angle:",
    "Páginas a rotacionar:": "Pages to rotate:",
    "Páginas (vazio = todas), ex: 0,2": "Pages (empty = all), e.g.: 0,2",
    "Nova ordem:": "New order:",
    "Nova ordem das páginas, ex: 2,0,1": "New page order, e.g.: 2,0,1",
    "Páginas a remover:": "Pages to remove:",
    "Páginas a remover, ex: 1,3": "Pages to remove, e.g.: 1,3",
    "Aplicar": "Apply",
    "Lista de páginas inválida. Use números separados por vírgula, ex: 0,2.": (
        "Invalid page list. Use numbers separated by commas, e.g.: 0,2."
    ),
    "Informe a nova ordem das páginas.": "Enter the new page order.",
    "Informe quais páginas remover.": "Enter which pages to remove.",
    "Uma das páginas informadas não existe neste PDF.": (
        "One of the given pages doesn't exist in this PDF."
    ),
    "Falha ao processar: {error}": "Processing failed: {error}",
    "Operação concluída com sucesso.": "Operation completed successfully.",
    # Compress
    "Falha ao comprimir: {error}": "Failed to compress: {error}",
    "PDF comprimido: {original} KB -> {compressed} KB ({reduction}% menor).": (
        "PDF compressed: {original} KB -> {compressed} KB ({reduction}% smaller)."
    ),
    # Convert
    "Direção:": "Direction:",
    "PDF para imagens": "PDF to images",
    "Imagens para PDF": "Images to PDF",
    "Word/Excel/PowerPoint para PDF": "Word/Excel/PowerPoint to PDF",
    "XML para PDF": "XML to PDF",
    "Pasta de saída das imagens:": "Output folder for images:",
    "Selecionar imagens": "Select images",
    "Imagens (na ordem desejada):": "Images (in the desired order):",
    "Arquivo PDF de saída:": "Output PDF file:",
    "Arquivo Word, Excel ou PowerPoint de entrada:": "Input Word, Excel, or PowerPoint file:",
    "LibreOffice encontrado: a conversão preserva a formatação original.": (
        "LibreOffice found: the conversion preserves the original formatting."
    ),
    "LibreOffice não encontrado: usando conversão básica em Python "
    "(preserva texto, mas não a formatação visual exata).": (
        "LibreOffice not found: using basic Python conversion "
        "(preserves text, but not the exact visual formatting)."
    ),
    "Arquivo XML de entrada:": "Input XML file:",
    "Escolha o arquivo PDF de entrada.": "Choose the input PDF file.",
    "Falha ao converter: {error}": "Failed to convert: {error}",
    "{count} imagem(ns) gerada(s) com sucesso.": "{count} image(s) generated successfully.",
    "Adicione pelo menos uma imagem.": "Add at least one image.",
    "Escolha o arquivo PDF de saída.": "Choose the output PDF file.",
    "PDF gerado com sucesso.": "PDF generated successfully.",
    "Escolha o arquivo XML de entrada.": "Choose the input XML file.",
    # Watermark
    "Texto da marca d'água, ex: CONFIDENCIAL": "Watermark text, e.g.: CONFIDENTIAL",
    "Opacidade:": "Opacity:",
    "Tamanho da fonte:": "Font size:",
    "Rotação:": "Rotation:",
    "Aplicar marca d'água": "Apply watermark",
    "Texto:": "Text:",
    "Digite o texto da marca d'água.": "Enter the watermark text.",
    "Falha ao aplicar marca d'água: {error}": "Failed to apply watermark: {error}",
    "Marca d'água aplicada com sucesso.": "Watermark applied successfully.",
    # Protect
    "Proteger com senha": "Protect with password",
    "Remover senha": "Remove password",
    "Senha": "Password",
    "Senha:": "Password:",
    "Confirmar senha": "Confirm password",
    "Confirmar senha:": "Confirm password:",
    "Digite uma senha.": "Enter a password.",
    "As senhas não coincidem.": "The passwords don't match.",
    "Falha ao proteger o PDF: {error}": "Failed to protect the PDF: {error}",
    "PDF protegido com sucesso.": "PDF protected successfully.",
    "Digite a senha atual do PDF.": "Enter the PDF's current password.",
    "Falha ao remover a senha: {error}": "Failed to remove the password: {error}",
    "Senha removida com sucesso.": "Password removed successfully.",
    # Protect: advanced permissions
    "Permissões avançadas": "Advanced permissions",
    "A senha de abertura pode ficar em branco (o PDF abre sem pedir senha); a "
    "senha de permissões é obrigatória — só quem a souber tem acesso total, "
    "ignorando as restrições marcadas abaixo.": (
        "The opening password can be left blank (the PDF opens without asking for a "
        "password); the permissions password is required — only whoever knows it has full "
        "access, ignoring the restrictions checked below."
    ),
    "Senha de abertura (opcional)": "Opening password (optional)",
    "Senha de permissões": "Permissions password",
    "Permissões:": "Permissions:",
    "Permitir impressão": "Allow printing",
    "Permitir impressão em alta qualidade": "Allow high-quality printing",
    "Permitir modificação do conteúdo": "Allow content modification",
    "Permitir inserir, remover ou girar páginas": "Allow inserting, removing, or rotating pages",
    "Permitir copiar texto e imagens": "Allow copying text and images",
    "Permitir cópia para ferramentas de acessibilidade": (
        "Allow copying for accessibility tools"
    ),
    "Permitir comentários e anotações": "Allow comments and annotations",
    "Permitir preenchimento de formulários": "Allow filling out forms",
    "Aplicar permissões": "Apply permissions",
    "Digite a senha de permissões.": "Enter the permissions password.",
    "Falha ao aplicar permissões: {error}": "Failed to apply permissions: {error}",
    "Permissões aplicadas com sucesso.": "Permissions applied successfully.",
    # Metadata
    "Carregar metadados": "Load metadata",
    "Separadas por vírgula": "Comma-separated",
    "Título:": "Title:",
    "Autor:": "Author:",
    "Assunto:": "Subject:",
    "Palavras-chave:": "Keywords:",
    "Falha ao ler metadados: {error}": "Failed to read metadata: {error}",
    "Falha ao salvar metadados: {error}": "Failed to save metadata: {error}",
    "Metadados salvos com sucesso.": "Metadata saved successfully.",
    # Page numbers
    "Começar em:": "Start at:",
    "Adicionar numeração": "Add page numbers",
    "Numeração de páginas": "Page numbers",
    "Falha ao numerar páginas: {error}": "Failed to add page numbers: {error}",
    "Numeração adicionada com sucesso.": "Page numbers added successfully.",
    # Page numbers: Bates numbering
    "Numeração Bates": "Bates numbering",
    "Prefixo (ex.: CASO-)": "Prefix (e.g.: CASE-)",
    "Prefixo:": "Prefix:",
    "Dígitos (zeros à esquerda):": "Digits (leading zeros):",
    "Posição:": "Position:",
    "Adicionar numeração Bates": "Add Bates numbering",
    "Falha ao adicionar numeração Bates: {error}": "Failed to add Bates numbering: {error}",
    "Numeração Bates adicionada com sucesso.": "Bates numbering added successfully.",
    # Page numbers: header/footer
    "Cabeçalho/Rodapé": "Header/Footer",
    "Suporta os textos {page} (número da página) e {pages} (total de páginas).": (
        "Supports the placeholders {page} (page number) and {pages} (total pages)."
    ),
    "Texto, ex: Página {page} de {pages}": "Text, e.g.: Page {page} of {pages}",
    "Cabeçalho à esquerda": "Header, left",
    "Cabeçalho ao centro": "Header, center",
    "Cabeçalho à direita": "Header, right",
    "Rodapé à esquerda": "Footer, left",
    "Rodapé ao centro": "Footer, center",
    "Rodapé à direita": "Footer, right",
    "Adicionar cabeçalho/rodapé": "Add header/footer",
    "Digite o texto do cabeçalho/rodapé.": "Enter the header/footer text.",
    "Falha ao adicionar cabeçalho/rodapé: {error}": "Failed to add header/footer: {error}",
    "Cabeçalho/rodapé adicionado com sucesso.": "Header/footer added successfully.",
    # Extract text
    "Arquivo de saída (.txt):": "Output file (.txt):",
    "Falha ao extrair texto: {error}": "Failed to extract text: {error}",
    "Texto extraído com sucesso.": "Text extracted successfully.",
    # Extract images
    "Falha ao extrair imagens: {error}": "Failed to extract images: {error}",
    "Nenhuma imagem encontrada no PDF.": "No images found in the PDF.",
    "{count} imagem(ns) extraída(s) com sucesso.": "{count} image(s) extracted successfully.",
    # Crop / Resize
    "Cortar margens": "Crop margins",
    "Redimensionar": "Resize",
    "Esquerda:": "Left:",
    "Baixo:": "Bottom:",
    "Direita:": "Right:",
    "Topo:": "Top:",
    "Cortar": "Crop",
    "Margens a cortar (pontos):": "Margins to crop (points):",
    "Novo tamanho da página (pontos):": "New page size (points):",
    "Falha ao cortar páginas: {error}": "Failed to crop pages: {error}",
    "Páginas cortadas com sucesso.": "Pages cropped successfully.",
    "Falha ao redimensionar páginas: {error}": "Failed to resize pages: {error}",
    "Páginas redimensionadas com sucesso.": "Pages resized successfully.",
    # Bookmarks
    "Título do marcador": "Bookmark title",
    "Adicionar": "Add",
    "Marcadores:": "Bookmarks:",
    "Digite um título para o marcador.": "Enter a title for the bookmark.",
    "{title} — página {page}": "{title} — page {page}",
    "Adicione pelo menos um marcador.": "Add at least one bookmark.",
    "Falha ao salvar marcadores: {error}": "Failed to save bookmarks: {error}",
    "Marcadores salvos com sucesso.": "Bookmarks saved successfully.",
    # Create PDF
    "Páginas:": "Pages:",
    "Falha ao criar PDF: {error}": "Failed to create PDF: {error}",
    "PDF criado com sucesso.": "PDF created successfully.",
    # Form fields
    "Nome do campo, ex: nome_completo": "Field name, e.g.: full_name",
    "Texto": "Text",
    "Data": "Date",
    "Caixa de seleção": "Checkbox",
    "Lista suspensa": "Dropdown list",
    "Lista de seleção": "List box",
    "Marcado": "Checked",
    "Aplica-se apenas ao tipo caixa de seleção": "Applies only to the checkbox type",
    "Opções separadas por vírgula (ex: SP,RJ,MG)": "Options separated by commas (e.g.: SP,RJ,MG)",
    "Aplica-se apenas aos tipos lista suspensa e lista de seleção": (
        "Applies only to the dropdown list and list box types"
    ),
    "Opções (lista suspensa/lista de seleção):": "Options (dropdown list/list box):",
    "Nome do campo:": "Field name:",
    "Tipo:": "Type:",
    "Adicionar campo": "Add field",
    "Campo de formulário": "Form field",
    "Digite um nome para o campo.": "Enter a name for the field.",
    "Falha ao adicionar campo: {error}": "Failed to add field: {error}",
    "Campo adicionado com sucesso.": "Field added successfully.",
    # Form fields: radio group
    "Adicionar grupo de opções": "Add radio group",
    "Grupo de opções": "Radio group",
    "Nome do grupo, ex: sexo": "Group name, e.g.: gender",
    "Valor pré-selecionado (opcional)": "Pre-selected value (optional)",
    "Valor": "Value",
    "Página": "Page",
    "Adicionar opção": "Add option",
    "Remover opção": "Remove option",
    "Criar grupo": "Create group",
    "Falha ao criar grupo: {error}": "Failed to create group: {error}",
    "Grupo criado com sucesso.": "Group created successfully.",
    "Página, X e Y precisam ser números em todas as linhas preenchidas.": (
        "Page, X, and Y must be numbers in every filled-in row."
    ),
    # Form fields: list existing fields
    "Listar campos": "List fields",
    "Nenhum campo de formulário encontrado.": "No form fields found.",
    "Falha ao listar campos: {error}": "Failed to list fields: {error}",
    # Form fields: export/import data
    "Exportar dados (CSV)": "Export data (CSV)",
    "Exportar dados (FDF)": "Export data (FDF)",
    "Importar dados (CSV)": "Import data (CSV)",
    "Importar dados (FDF)": "Import data (FDF)",
    "Exportar": "Export",
    "Importar": "Import",
    "Exportar dados": "Export data",
    "Importar dados": "Import data",
    "Arquivo CSV com os dados:": "CSV file with the data:",
    "Arquivo FDF com os dados:": "FDF file with the data:",
    "Escolha o arquivo de dados.": "Choose the data file.",
    "Falha ao exportar dados: {error}": "Failed to export data: {error}",
    "{count} campo(s) exportado(s) com sucesso.": "{count} field(s) exported successfully.",
    "Falha ao importar dados: {error}": "Failed to import data: {error}",
    "{count} campo(s) preenchido(s) com sucesso.": "{count} field(s) filled in successfully.",
    # Form fields: flatten
    "Achatar formulário": "Flatten form",
    "Grava o valor atual de cada campo preenchido como conteúdo estático da "
    "página e remove os widgets interativos. Campos sem valor definido são "
    "deixados como estão.": (
        "Writes the current value of each filled-in field as static page content and "
        "removes the interactive widgets. Fields with no value set are left as they are."
    ),
    "Falha ao achatar formulário: {error}": "Failed to flatten the form: {error}",
    "{count} campo(s) achatado(s) com sucesso.": "{count} field(s) flattened successfully.",
    # Menu bar: open PDF
    "Abrir PDF...": "Open PDF...",
    # Document source bar (shared "open document" indicator on tool panels)
    "Abrir...": "Open...",
    "Abrir outro arquivo PDF": "Open another PDF file",
    "Nenhum PDF aberto": "No PDF open",
    "Abra um PDF para começar.": "Open a PDF to get started.",
    # PDF viewer toolbar
    "Página anterior": "Previous page",
    "Próxima página": "Next page",
    "Diminuir zoom": "Zoom out",
    "Aumentar zoom": "Zoom in",
    "Ajustar à largura": "Fit to width",
    "Página única": "Single page",
    "Rolagem contínua": "Continuous scroll",
    "Miniaturas": "Thumbnails",
    "Buscar": "Search",
    "Página {current} de {total}": "Page {current} of {total}",
    "Página {number}": "Page {number}",
    # PDF viewer search bar
    "Buscar no documento...": "Search the document...",
    "Ocorrência anterior": "Previous match",
    "Próxima ocorrência": "Next match",
    "Fechar": "Close",
    "Nenhuma ocorrência": "No matches",
    "{current} de {total}": "{current} of {total}",
    # Annotations: sidebar section
    "Anotações": "Annotations",
    "Realce, sublinhe, risque, adicione notas, desenhe ou carimbe sobre um PDF.": (
        "Highlight, underline, strike through, add notes, draw, or stamp over a PDF."
    ),
    # Measure: sidebar section
    "Medição": "Measurement",
    "Meça a distância entre dois pontos de um PDF, arrastando no visualizador central.": (
        "Measure the distance between two points of a PDF by dragging over the central viewer."
    ),
    # Annotations: tools
    "Selecionar/Apagar": "Select/Erase",
    "Realce": "Highlight",
    "Sublinhado": "Underline",
    "Riscado": "Strikethrough",
    "Nota adesiva": "Sticky note",
    "Caneta": "Pen",
    "Carimbo": "Stamp",
    # Annotations: colors
    "Amarelo": "Yellow",
    "Vermelho": "Red",
    "Verde": "Green",
    "Azul": "Blue",
    "Preto": "Black",
    # Annotations: stamp presets
    "APROVADO": "APPROVED",
    "CONFIDENCIAL": "CONFIDENTIAL",
    "RASCUNHO": "DRAFT",
    "REVISADO": "REVIEWED",
    "URGENTE": "URGENT",
    # Annotations: page UI
    "Ferramenta:": "Tool:",
    "Cor:": "Color:",
    "Texto do carimbo:": "Stamp text:",
    "Limpar pendentes": "Clear pending",
    "{count} anotação(ões) pendente(s)": "{count} pending annotation(s)",
    "Salvar anotações": "Save annotations",
    "Adicione pelo menos uma anotação antes de salvar.": "Add at least one annotation before saving.",
    "Falha ao salvar anotações: {error}": "Failed to save annotations: {error}",
    "Anotações salvas com sucesso.": "Annotations saved successfully.",
    # Annotations: sticky-note dialog (viewer)
    "Texto da nota:": "Note text:",
    # OCR: sidebar section
    "OCR": "OCR",
    "Reconheça texto em páginas escaneadas, tornando-as pesquisáveis.": (
        "Recognize text in scanned pages, making them searchable."
    ),
    # OCR: page UI
    "Idioma do texto:": "Text language:",
    "Pular páginas que já têm texto": "Skip pages that already have text",
    "Reconhecer texto": "Recognize text",
    "Tesseract OCR não encontrado. Instale o Tesseract "
    "(https://github.com/tesseract-ocr/tesseract) para usar esta ferramenta.": (
        "Tesseract OCR not found. Install Tesseract "
        "(https://github.com/tesseract-ocr/tesseract) to use this tool."
    ),
    "Nenhum idioma de reconhecimento instalado no Tesseract.": (
        "No recognition language installed in Tesseract."
    ),
    "Tesseract encontrado. Idiomas disponíveis: {languages}.": (
        "Tesseract found. Available languages: {languages}."
    ),
    "Nenhum idioma de reconhecimento disponível.": "No recognition language available.",
    "Falha ao reconhecer texto: {error}": "Failed to recognize text: {error}",
    "Texto reconhecido em {count} página(s).": "Text recognized in {count} page(s).",
    "Nenhuma página precisou de OCR (o PDF já tinha texto).": (
        "No page needed OCR (the PDF already had text)."
    ),
    # OCR: language names
    "Inglês": "English",
    "Português": "Portuguese",
    "Espanhol": "Spanish",
    "Francês": "French",
    "Alemão": "German",
    "Italiano": "Italian",
    # Redaction/Sanitize: sidebar section
    "Redigir/Sanitizar": "Redact/Sanitize",
    "Apague definitivamente áreas de um PDF ou remova metadados, JavaScript e anexos.": (
        "Permanently erase areas of a PDF, or remove metadata, JavaScript, and attachments."
    ),
    # Redaction/Sanitize: page UI
    "Redigir": "Redact",
    "Sanitizar": "Sanitize",
    "Modo:": "Mode:",
    "Arraste no visualizador para marcar as áreas a apagar. Cada página marcada "
    "vira uma imagem achatada (perde a camada de texto pesquisável inteira, não "
    "só a área marcada) — é assim que garantimos que nada fique recuperável.": (
        "Drag over the viewer to mark the areas to erase. Each marked page "
        "becomes a flattened image (it loses the entire searchable text layer, not "
        "just the marked area) — that's how we guarantee nothing stays recoverable."
    ),
    "Ou detecte automaticamente padrões de dado sensível no texto do PDF:": (
        "Or automatically detect sensitive data patterns in the PDF's text:"
    ),
    "CPF": "CPF",
    "CNPJ": "CNPJ",
    "Telefone": "Phone",
    "Cartão de crédito": "Credit card",
    "Expressão regular personalizada (opcional)": "Custom regular expression (optional)",
    "Detectar e marcar": "Detect and mark",
    "Marque ao menos um padrão ou digite uma expressão regular.": (
        "Check at least one pattern or enter a regular expression."
    ),
    "Falha ao detectar padrões: {error}": "Failed to detect patterns: {error}",
    "{count} ocorrência(s) encontrada(s) e marcada(s) para redação.": (
        "{count} occurrence(s) found and marked for redaction."
    ),
    "{count} área(s) marcada(s) para redação": "{count} area(s) marked for redaction",
    "Aplicar redação": "Apply redaction",
    "Marque pelo menos uma área no visualizador antes de aplicar.": (
        "Mark at least one area in the viewer before applying."
    ),
    "Falha ao redigir: {error}": "Failed to redact: {error}",
    "{count} página(s) redigida(s) com sucesso.": "{count} page(s) redacted successfully.",
    "Remover metadados": "Remove metadata",
    "Remover anotações e comentários": "Remove annotations and comments",
    "JavaScript e anexos embutidos são sempre removidos.": (
        "Embedded JavaScript and attachments are always removed."
    ),
    "Falha ao sanitizar: {error}": "Failed to sanitize: {error}",
    "PDF sanitizado com sucesso.": "PDF sanitized successfully.",
    # Digital signature: sidebar section
    "Assinatura digital": "Digital signature",
    "Assine um PDF com selo visível e assinatura criptográfica, ou verifique uma assinatura existente.": (
        "Sign a PDF with a visible stamp and a cryptographic signature, or verify an existing signature."
    ),
    # Digital signature: page UI
    "Assinar": "Sign",
    "Verificar assinatura": "Verify signature",
    "Arquivo .pfx": "Certificate file (.pfx)",
    "Gerar certificado de teste": "Generate test certificate",
    "Nome exibido na assinatura": "Name shown on the signature",
    "Certificado:": "Certificate:",
    "Nome do signatário:": "Signer name:",
    "Página:": "Page:",
    "Posição do selo:": "Stamp position:",
    "Inferior direito": "Bottom right",
    "Inferior esquerdo": "Bottom left",
    "Superior direito": "Top right",
    "Superior esquerdo": "Top left",
    "Certificado (*.pfx *.p12)": "Certificate (*.pfx *.p12)",
    "Arquivo .pfx/.p12:": "Certificate file (.pfx/.p12):",
    "Senha do certificado": "Certificate password",
    "Senha:": "Password:",
    "Certificado autoassinado gerado na hora, sem validade jurídica — use só "
    "para testar o fluxo ou assinaturas de uso pessoal/interno.": (
        "Self-signed certificate generated on the spot, with no legal validity — use it only "
        "to test the flow or for personal/internal signatures."
    ),
    "Nome completo": "Full name",
    "E-mail": "Email",
    "Nome:": "Name:",
    "E-mail:": "Email:",
    "Arquivo PDF a verificar:": "PDF file to verify:",
    "Verificar": "Verify",
    "Abra um PDF para começar.": "Open a PDF to get started.",
    "Digite o nome do signatário.": "Enter the signer's name.",
    "O PDF de entrada não tem páginas.": "The input PDF has no pages.",
    "Escolha o arquivo .pfx/.p12.": "Choose the .pfx/.p12 file.",
    "Digite o nome para o certificado de teste.": "Enter the name for the test certificate.",
    "Falha ao assinar: {error}": "Failed to sign: {error}",
    "PDF assinado com sucesso.": "PDF signed successfully.",
    "Escolha o arquivo PDF a verificar.": "Choose the PDF file to verify.",
    "Falha ao verificar: {error}": "Failed to verify: {error}",
    "Nenhuma assinatura encontrada neste PDF.": "No signature found in this PDF.",
    "íntegro (não modificado)": "intact (not modified)",
    "MODIFICADO após a assinatura": "MODIFIED after signing",
    "Campo: {field}\nSignatário: {signer}\nData: {date}\nStatus: {status}": (
        "Field: {field}\nSigner: {signer}\nDate: {date}\nStatus: {status}"
    ),
    # PDF/A
    "Converter para PDF/A": "Convert to PDF/A",
    "Validar PDF/A": "Validate PDF/A",
    "Conversão aproximada: remove JavaScript, anexos embutidos e criptografia, e "
    "declara conformidade PDF/A nos metadados — mas não embute perfil de cor "
    "(/OutputIntent) nem verifica fontes. Para arquivamento legal, valide o "
    "resultado com uma ferramenta dedicada (ex.: veraPDF) antes de considerar o "
    "documento arquivável.": (
        "Approximate conversion: removes JavaScript, embedded attachments, and encryption, "
        "and declares PDF/A conformance in the metadata — but doesn't embed a color profile "
        "(/OutputIntent) or check fonts. For legal archiving, validate the result with a "
        "dedicated tool (e.g., veraPDF) before considering the document archival-ready."
    ),
    "Parte (PDF/A-N):": "Part (PDF/A-N):",
    "Nível de conformidade:": "Conformance level:",
    "A (acessível)": "A (accessible)",
    "B (básica)": "B (basic)",
    "U (Unicode)": "U (Unicode)",
    "PDF convertido com sucesso.": "PDF converted successfully.",
    "Verifica só um subconjunto dos requisitos de PDF/A (criptografia, "
    "JavaScript, anexos e metadados XMP) — não é validação ISO 19005 completa.": (
        "Checks only a subset of PDF/A requirements (encryption, JavaScript, attachments, "
        "and XMP metadata) — this is not full ISO 19005 validation."
    ),
    "Validar": "Validate",
    "Falha ao validar: {error}": "Failed to validate: {error}",
    "Nenhum problema encontrado nas verificações realizadas.": (
        "No issues found in the checks performed."
    ),
    "Problemas encontrados:\n{issues}": "Issues found:\n{issues}",
    # Edit: modes
    "Substituir imagem": "Replace image",
    "Editar texto": "Edit text",
    "Adicionar link": "Add link",
    "Listar links": "List links",
    "Remover link": "Remove link",
    # Edit: replace image
    "Listar imagens": "List images",
    "Nenhuma imagem embutida encontrada.": "No embedded images found.",
    "Falha ao listar imagens: {error}": "Failed to list images: {error}",
    "Índice da imagem na página:": "Image index on the page:",
    "Nova imagem:": "New image:",
    "Escolha a nova imagem.": "Choose the new image.",
    "Falha ao substituir imagem: {error}": "Failed to replace image: {error}",
    "Imagem substituída com sucesso.": "Image replaced successfully.",
    # Edit: edit text
    "Cobre a área marcada e desenha o texto novo por cima, achatando a página em "
    "imagem (como na redação) — não é edição do texto original, e a página "
    "inteira perde a camada de texto pesquisável.": (
        "Covers the marked area and draws the new text on top, flattening the page into an "
        "image (like redaction) — this is not an edit of the original text, and the whole "
        "page loses its searchable text layer."
    ),
    "Texto novo": "New text",
    "Adicionar área": "Add area",
    "Remover área": "Remove area",
    "Tamanho do texto novo:": "New text size:",
    "Aplicar edição": "Apply edit",
    "Página e as coordenadas precisam ser números em todas as linhas preenchidas.": (
        "Page and the coordinates must be numbers in every filled-in row."
    ),
    "Marque pelo menos uma área com texto novo.": "Mark at least one area with new text.",
    "Falha ao editar texto: {error}": "Failed to edit text: {error}",
    "{count} página(s) editada(s) com sucesso.": "{count} page(s) edited successfully.",
    # Edit: links
    "URL externa": "External URL",
    "Página do documento": "Document page",
    "Destino:": "Target:",
    "Digite a URL de destino.": "Enter the target URL.",
    "Falha ao adicionar link: {error}": "Failed to add link: {error}",
    "Link adicionado com sucesso.": "Link added successfully.",
    "Falha ao listar links: {error}": "Failed to list links: {error}",
    "Nenhum link encontrado.": "No links found.",
    'Use "Listar links" para descobrir a página e o índice do link a remover.': (
        'Use "List links" to find the page and index of the link to remove.'
    ),
    "Índice do link na página:": "Link index on the page:",
    "Falha ao remover link: {error}": "Failed to remove link: {error}",
    "Link removido com sucesso.": "Link removed successfully.",
    # Annotations: export comments
    "Exportar comentários (CSV)": "Export comments (CSV)",
    "Exportar comentários existentes para CSV:": "Export existing comments to CSV:",
    "Falha ao exportar comentários: {error}": "Failed to export comments: {error}",
    "{count} comentário(s) exportado(s) com sucesso.": "{count} comment(s) exported successfully.",
    # Accessibility
    "Corrigir idioma/título": "Fix language/title",
    "Verifica só um subconjunto dos requisitos de PDF/UA (idioma, título, "
    "árvore de estrutura e texto alternativo em figuras já tagueadas) — não é "
    "validação PDF/UA completa.": (
        "Checks only a subset of PDF/UA requirements (language, title, structure tree, and "
        "alt text on already-tagged figures) — this is not full PDF/UA validation."
    ),
    "Não tagueia o documento automaticamente (risco real de gerar uma estrutura "
    "malformada e passar uma falsa sensação de acessibilidade) — só ajusta "
    "idioma e título, os dois únicos itens que são simples metadados.": (
        "Doesn't auto-tag the document (real risk of producing a malformed structure and "
        "giving a false sense of accessibility) — only fixes language and title, the only "
        "two items that are plain metadata."
    ),
    "Idioma, ex: pt-BR": "Language, e.g.: pt-BR",
    "Título do documento": "Document title",
    "Idioma:": "Language:",
    "Corrigir": "Fix",
    "Falha ao corrigir: {error}": "Failed to fix: {error}",
    "Informe o idioma e o título.": "Enter the language and the title.",
    "Idioma e título corrigidos com sucesso.": "Language and title fixed successfully.",
    # Compare
    "Comparar texto": "Compare text",
    "Comparar visualmente": "Compare visually",
    "PDF A:": "PDF A:",
    "PDF B:": "PDF B:",
    "Escolha os dois arquivos PDF a comparar.": "Choose both PDF files to compare.",
    "Falha ao comparar: {error}": "Failed to compare: {error}",
    "Página {page}: sem alterações": "Page {page}: no changes",
    "Página {page}: {count} linha(s) diferentes — {preview}": (
        "Page {page}: {count} different line(s) — {preview}"
    ),
    "Pasta de saída (imagens de diferença):": "Output folder (difference images):",
    "comparada": "compared",
    "só existe em A": "only exists in A",
    "só existe em B": "only exists in B",
    "tamanhos diferentes, não comparada": "different sizes, not compared",
    "Página {page}: {label} — {percent:.1f}% diferente": "Page {page}: {label} — {percent:.1f}% different",
    "Página {page}: {label}": "Page {page}: {label}",
    # Layers
    "Listar camadas": "List layers",
    "Falha ao listar camadas: {error}": "Failed to list layers: {error}",
    "Este PDF não tem camadas (Optional Content Groups).": (
        "This PDF has no layers (Optional Content Groups)."
    ),
    "visível": "visible",
    "oculta": "hidden",
    "Índice da camada:": "Layer index:",
    "Nova visibilidade:": "New visibility:",
    "Visível": "Visible",
    "Oculta": "Hidden",
    "Aplicar visibilidade": "Apply visibility",
    "Falha ao alterar visibilidade: {error}": "Failed to change visibility: {error}",
    "Visibilidade da camada alterada com sucesso.": "Layer visibility changed successfully.",
    # Attachments
    "Listar": "List",
    "Extrair todos": "Extract all",
    "Listar anexos": "List attachments",
    "Falha ao listar anexos: {error}": "Failed to list attachments: {error}",
    "Nenhum anexo embutido encontrado.": "No embedded attachments found.",
    "Arquivo a anexar:": "File to attach:",
    "Escolha o arquivo a anexar.": "Choose the file to attach.",
    "Falha ao adicionar anexo: {error}": "Failed to add attachment: {error}",
    "Anexo adicionado com sucesso.": "Attachment added successfully.",
    'Use "Listar" para descobrir o nome exato do anexo a remover.': (
        'Use "List" to find the exact name of the attachment to remove.'
    ),
    "Nome do anexo, ex: notas.txt": "Attachment name, e.g.: notes.txt",
    "Nome do anexo:": "Attachment name:",
    "Digite o nome do anexo a remover.": "Enter the name of the attachment to remove.",
    "Falha ao remover anexo: {error}": "Failed to remove attachment: {error}",
    "Anexo removido com sucesso.": "Attachment removed successfully.",
    "Extrair anexos": "Extract attachments",
    "Falha ao extrair anexos: {error}": "Failed to extract attachments: {error}",
    "{count} anexo(s) extraído(s) com sucesso.": "{count} attachment(s) extracted successfully.",
    # Measure
    "Arraste no visualizador entre dois pontos para medir a distância entre eles.": (
        "Drag over the viewer between two points to measure the distance between them."
    ),
    "Milímetros (mm)": "Millimeters (mm)",
    "Centímetros (cm)": "Centimeters (cm)",
    "Polegadas (in)": "Inches (in)",
    "Pontos PDF (pt)": "PDF points (pt)",
    "Unidade:": "Unit:",
    "Nenhuma medição feita ainda.": "No measurement taken yet.",
    "Última medição: {distance}": "Last measurement: {distance}",
    "Limpar medição": "Clear measurement",
    # Annotations: custom stamp library
    "Nome para salvar este carimbo (opcional)": "Name to save this stamp under (optional)",
    "Salvar carimbo customizado": "Save custom stamp",
    "Remover carimbo customizado selecionado": "Remove selected custom stamp",
    "Digite o texto do carimbo antes de salvar.": "Enter the stamp text before saving.",
    "Falha ao salvar carimbo: {error}": "Failed to save stamp: {error}",
    "Carimbo salvo com sucesso.": "Stamp saved successfully.",
    "Selecione um carimbo customizado para remover.": "Select a custom stamp to remove.",
}
