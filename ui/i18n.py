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
    "Adicione números de página no rodapé de um PDF.": (
        "Add page numbers to the footer of a PDF."
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
    "Marcadores": "Bookmarks",
    "Monte um sumário de navegação (marcadores) para um PDF.": (
        "Build a navigation outline (bookmarks) for a PDF."
    ),
    "Campos de formulário": "Form fields",
    "Adicione campos de formulário interativos (texto ou caixa de seleção) a um PDF.": (
        "Add interactive form fields (text or checkbox) to a PDF."
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
    # Pages (rotate/reorder/remove)
    "Rotacionar": "Rotate",
    "Reordenar": "Reorder",
    "Remover": "Remove",
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
    "Caixa de seleção": "Checkbox",
    "Marcado (apenas para caixa de seleção)": "Checked (checkbox only)",
    "Nome do campo:": "Field name:",
    "Tipo:": "Type:",
    "Adicionar campo": "Add field",
    "Campo de formulário": "Form field",
    "Digite um nome para o campo.": "Enter a name for the field.",
    "Falha ao adicionar campo: {error}": "Failed to add field: {error}",
    "Campo adicionado com sucesso.": "Field added successfully.",
}
