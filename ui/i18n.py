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


def literal(text: str) -> str:
    """O texto para um botão ou uma aba sem que o "&" vire atalho ("Fill & sign", "A&B.pdf")."""
    return text.replace("&", "&&")


def plural(count: int, one: str, many: str, **params) -> str:
    """"1 página" / "25 páginas": `one` sem {count} no singular, `many` com {count}; os outros
    valores do texto ("{folder}") vêm em `params`."""
    return tr(one if count == 1 else many).format(count=count, **params)


def tr_message(text) -> str:
    """Traduz um texto vindo do `core`: uma `core.messages.Message` (modelo + valores) ou um
    texto fixo, procurado no dicionário como qualquer outro."""
    template = getattr(text, "template", None)
    if template is not None:
        params = {
            key: tr_message(value) if getattr(value, "template", None) is not None else value
            for key, value in text.params.items()
        }
        return tr(template).format(**params)
    return tr(str(text))


def error_text(exc: BaseException) -> str:
    """A mensagem de um erro no idioma ativo (ver `tr_message`)."""
    if len(exc.args) == 1 and isinstance(exc.args[0], str):
        return tr_message(exc.args[0])
    return str(exc)


_qt_translator = None


def install_qt_translator(app) -> None:
    """Traduz os textos do próprio Qt (botões "Yes"/"No"/"Cancel" das caixas de diálogo,
    menus de contexto dos campos de texto) para o idioma ativo."""
    global _qt_translator
    from PySide6.QtCore import QLibraryInfo, QTranslator

    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if _current_language != PT_BR:
        return  # o Qt já vem em inglês
    translator = QTranslator(app)
    if translator.load("qtbase_pt_BR", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
        _qt_translator = translator


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
    "Converta entre PDF e imagens, Word, Excel, PowerPoint, texto, HTML, Markdown e XML.": (
        "Convert between PDF and images, Word, Excel, PowerPoint, text, HTML, Markdown and XML."
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
    "Compare duas versões de um PDF: lado a lado com as diferenças destacadas, diff de texto por página ou diff visual.": (
        "Compare two versions of a PDF: side by side with the differences highlighted, per-page text diff or visual diff."
    ),
    # Menu bar / about dialog
    "Arquivo": "File",
    "Sair": "Quit",
    "Ajuda": "Help",
    "Sobre o OpenFolio PDF Suite": "About OpenFolio PDF Suite",
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
    "Carta (Letter)": "Letter",
    "Ofício (Legal)": "Legal",
    "Personalizado": "Custom",
    # Merge
    "Selecionar PDFs": "Select PDFs",
    "todas (ex.: 1-3, 5)": "all (e.g. 1-3, 5)",
    "Páginas do arquivo selecionado:": "Pages of the selected file:",
    "Um marcador por arquivo (com os marcadores dele dentro)": "One bookmark per file (with its bookmarks inside)",
    "Junta dois arquivos página a página: a 1ª do primeiro, a 1ª do segundo, a 2ª do primeiro...": (
        "Joins two files page by page: the 1st of the first, the 1st of the second, the 2nd of the first..."
    ),
    "Versos em ordem inversa (o maço virado no scanner)": "Backs in reverse order (the stack flipped in the scanner)",
    "Para intercalar, deixe na lista só dois arquivos: o das frentes e o dos versos.": "To interleave, keep only two files in the list: the fronts and the backs.",
    "Adicione pelo menos um arquivo.": "Add at least one file.",
    "Falha ao mesclar: {error}": "Failed to merge: {error}",
    # Split
    "Páginas por arquivo:": "Pages per file:",
    "Falha ao dividir: {error}": "Failed to split: {error}",
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
    # M16 — mais modos de dividir
    "Por intervalos": "By ranges",
    "Por tamanho máximo": "By maximum size",
    "A cada página em branco": "At each blank page",
    "ex.: 1-3; 4-10; 11-": "e.g. 1-3; 4-10; 11-",
    "As páginas selecionadas nas miniaturas, num arquivo só (Ctrl ou Shift + clique).": "The pages selected in the thumbnails, in a single file (Ctrl or Shift + click).",
    "Um arquivo por grupo, separados por ponto e vírgula; dentro de um grupo, vírgulas juntam páginas soltas (1-3, 5; 6-10). Um grupo só extrai aquelas páginas.": "One file per group, separated by semicolons; within a group, commas join single pages (1-3, 5; 6-10). A single group extracts those pages.",
    "Dividir por intervalos": "Split by ranges",
    "Partes de até esse tamanho, com as páginas na ordem (para anexar em e-mail ou enviar a um sistema com limite). Uma página que sozinha passa do limite fica num arquivo próprio.": "Parts up to this size, with the pages in order (to attach to an email or upload to a system with a limit). A page that alone exceeds the limit goes in a file of its own.",
    "Dividir por tamanho": "Split by size",
    "Tamanho máximo:": "Maximum size:",
    "Para lotes escaneados com uma folha em branco entre os documentos: cada página em branco separa um arquivo do próximo e não vai para nenhum.": "For scanned batches with a blank sheet between documents: each blank page separates one file from the next and goes in none.",
    "Dividir nas páginas em branco": "Split at blank pages",
    "Informe as páginas de cada arquivo.": "Provide the pages of each file.",
    "Passaram do limite, por terem uma página maior que ele: {files}.": "Over the limit, because they have a page larger than it: {files}.",
    "Nenhuma página em branco encontrada: não há onde dividir.": "No blank page found: there is nowhere to split.",
    "Medindo as partes": "Measuring the parts",
    "Procurando páginas em branco": "Looking for blank pages",
    # PDF para imagens (M18)
    "Formato:": "Format:",
    "PNG (uma imagem por página)": "PNG (one image per page)",
    "JPEG (uma imagem por página, menor)": "JPEG (one image per page, smaller)",
    "TIFF (um arquivo com todas as páginas)": "TIFF (one file with every page)",
    "Informe as páginas a converter.": "Enter the pages to convert.",
    # Marca d'água (M19)
    "Imagem ou logotipo": "Image or logo",
    "Imagem:": "Image:",
    "Largura da imagem em relação à largura da página.": "Width of the image relative to the width of the page.",
    "Centro": "Center",
    "Canto superior esquerdo": "Top left corner",
    "Canto superior direito": "Top right corner",
    "Canto inferior esquerdo": "Bottom left corner",
    "Canto inferior direito": "Bottom right corner",
    "Mosaico (repetida pela página)": "Tiled (repeated across the page)",
    "Atrás do conteúdo": "Behind the content",
    "Como um papel timbrado: o texto da página fica por cima. Some em páginas escaneadas, que cobrem a página inteira.": (
        "Like letterhead: the text of the page stays on top. It disappears on scanned pages, which cover the whole page."
    ),
    "Pré-visualizar": "Preview",
    "Mostra a página atual do visualizador com a marca d'água, sem gravar nada.": (
        "Shows the viewer's current page with the watermark, without saving anything."
    ),
    "Marca d'água:": "Watermark:",
    "Escolha a imagem da marca d'água.": "Choose the watermark image.",
    "Informe as páginas a marcar.": "Enter the pages to mark.",
    "Informe o texto ou a imagem da marca d'água.": "Enter the text or the image of the watermark.",
    # Numeração (M20)
    "Arábicos (1, 2, 3)": "Arabic (1, 2, 3)",
    "Romanos minúsculos (i, ii, iii)": "Lowercase Roman (i, ii, iii)",
    "Romanos maiúsculos (I, II, III)": "Uppercase Roman (I, II, III)",
    "Algarismos:": "Numerals:",
    "Usar os rótulos de página do documento": "Use the document's page labels",
    "Escreve o número que o visualizador mostra para cada página (como iii ou A-1), em vez de contar.": (
        "Writes the number the viewer shows for each page (such as iii or A-1), instead of counting."
    ),
    "Pular as primeiras:": "Skip the first:",
    "A capa e as páginas de abertura ficam sem número; a contagem começa depois delas.": (
        "The cover and the opening pages get no number; the count starts after them."
    ),
    "Algarismos romanos vão de 1 a 3999.": "Roman numerals go from 1 to 3999.",
    "Informe as páginas a numerar.": "Enter the pages to number.",
    "Nenhuma página sobrou para numerar.": "No page is left to number.",
    # Assinatura (M24)
    "Motivo: {value}": "Reason: {value}",
    "Local: {value}": "Location: {value}",
    "Contato: {value}": "Contact: {value}",
    "confere": "checks out",
    "NÃO CONFERE": "DOES NOT CHECK OUT",
    "Carimbo de tempo: {date} ({status})": "Timestamp: {date} ({status})",
    "Formato: PAdES": "Format: PAdES",
    "Opcional, ex: Aprovo este documento": "Optional, e.g.: I approve this document",
    "Opcional, ex: Curitiba, PR": "Optional, e.g.: Curitiba, PR",
    "Opcional, ex: telefone ou e-mail": "Optional, e.g.: phone or e-mail",
    "Opcional: a imagem da sua assinatura (PNG com fundo transparente fica melhor) na metade esquerda do selo.": (
        "Optional: the image of your signature (a PNG with a transparent background looks best) on the left half of the stamp."
    ),
    "Formato PAdES": "PAdES format",
    "O padrão europeu de assinatura de PDF (ETSI). Desmarque só se um sistema antigo exigir o formato da Adobe.": (
        "The European PDF signature standard (ETSI). Uncheck it only if an old system requires the Adobe format."
    ),
    "Opcional: endereço do servidor de carimbo de tempo (TSA)": "Optional: address of the timestamp server (TSA)",
    "Um servidor de carimbo de tempo atesta a data da assinatura, em vez do relógio deste "
    "computador. O app envia a ele só o resumo criptográfico do documento, não o documento.": (
        "A timestamp server attests the date of the signature, instead of this computer's clock. "
        "The app sends it only the cryptographic digest of the document, not the document."
    ),
    "Motivo:": "Reason:",
    "Local:": "Location:",
    "Contato:": "Contact:",
    "Imagem no selo:": "Image in the stamp:",
    "Carimbo de tempo:": "Timestamp:",
    "Ver o certificado": "View the certificate",
    "Mostra de quem é o certificado, quem o emitiu e até quando vale.": (
        "Shows whose certificate it is, who issued it and until when it is valid."
    ),
    "O selo leva o nome que está no certificado.": "The stamp carries the name on the certificate.",
    "Falha ao abrir o certificado: {error}": "Failed to open the certificate: {error}",
    "VENCIDO: não dá para assinar com ele.": "EXPIRED: it cannot be used to sign.",
    "Não foi possível ler a imagem do selo: {error}": "Could not read the stamp image: {error}",
    "O certificado venceu em {date}: a assinatura não seria válida. Use um certificado em dia.": (
        "The certificate expired on {date}: the signature would not be valid. Use a current certificate."
    ),
    "Não foi possível obter o carimbo de tempo de {url}: {error}": "Could not get the timestamp from {url}: {error}",
    "O servidor de carimbo de tempo {url} não respondeu.": "The timestamp server {url} did not respond.",
    # OCR (M22)
    "Refazer o OCR (tira o texto reconhecido antes)": "Redo the OCR (removes the text recognized before)",
    "Endireitar as páginas no documento": "Straighten the pages in the document",
    "Gira as páginas tortas (até 5°) e põe de pé as digitalizadas de lado, como a aba "
    "Limpar escaneados. Sem isso, o OCR lê na orientação certa, mas a página fica como está.": (
        "Rotates crooked pages (up to 5°) and turns pages scanned sideways upright, like the "
        "Clean up scans tab. Without it, the OCR reads in the right orientation, but the page stays as it is."
    ),
    # Pages (rotate/reorder/remove/insert/replace)
    "Rotacionar": "Rotate",
    "Reordenar": "Reorder",
    "Remover": "Remove",
    "Inserir": "Insert",
    "Substituir": "Replace",
    "PDF com as páginas a inserir:": "PDF with the pages to insert:",
    "Inserir antes da página (total + 1 = no fim):": "Insert before page (total + 1 = at the end):",
    "PDF com as páginas substitutas:": "PDF with the replacement pages:",
    "Substituir da página:": "Replace from page:",
    "Até a página (inclusive):": "To page (inclusive):",
    "Escolha o PDF de origem das páginas.": "Choose the source PDF for the pages.",
    "Ângulo:": "Angle:",
    "Páginas a rotacionar:": "Pages to rotate:",
    "90° no sentido horário": "90° clockwise",
    "180°": "180°",
    "90° no sentido anti-horário": "90° counterclockwise",
    "Nova ordem:": "New order:",
    "Todas as páginas na nova ordem, ex: 3, 1, 2 ou 4-1": (
        "Every page in the new order, e.g.: 3, 1, 2 or 4-1"
    ),
    "Páginas a remover:": "Pages to remove:",
    "Páginas a remover, ex: 2, 5-7": "Pages to remove, e.g.: 2, 5-7",
    "Aplicar": "Apply",
    "Informe a nova ordem das páginas.": "Enter the new page order.",
    "Informe quais páginas remover.": "Enter which pages to remove.",
    "Falha ao processar: {error}": "Processing failed: {error}",
    # Compress
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
    "Arquivo XML de entrada:": "Input XML file:",
    "Falha ao converter: {error}": "Failed to convert: {error}",
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
    # Marcadores (M25)
    "Título": "Title",
    "Arraste para reordenar ou solte sobre outro marcador para aninhar. Duplo clique edita o título ou a página.": (
        "Drag to reorder, or drop onto another bookmark to nest it. Double-click edits the title or the page."
    ),
    "Move o marcador para cima, entre os do mesmo nível.": "Moves the bookmark up, among those at the same level.",
    "Move o marcador para baixo, entre os do mesmo nível.": "Moves the bookmark down, among those at the same level.",
    "Para dentro": "Indent",
    "Põe o marcador dentro do que está acima dele.": "Puts the bookmark inside the one above it.",
    "Para fora": "Outdent",
    "Tira o marcador de dentro do marcador pai.": "Takes the bookmark out of its parent bookmark.",
    "Remove o marcador e os que estão dentro dele.": "Removes the bookmark and the ones inside it.",
    "Recarregar do documento": "Reload from the document",
    "Descarta as mudanças e volta aos marcadores do documento aberto.": (
        "Discards the changes and goes back to the bookmarks of the open document."
    ),
    "Gerar a partir dos títulos": "Generate from the headings",
    "Sugere um sumário com as linhas em fonte maior que a do texto; cada tamanho vira um nível.": (
        "Suggests an outline from the lines in a font larger than the text's; each size becomes a level."
    ),
    "Falha ao procurar os títulos: {error}": "Failed to look for the headings: {error}",
    "Há um marcador sem título.": "There is a bookmark without a title.",
    "Nenhum título encontrado: o texto todo tem o mesmo tamanho.": "No heading found: all the text has the same size.",
    "Trocar os marcadores da lista pelos {count} títulos encontrados?": (
        "Replace the bookmarks in the list with the {count} headings found?"
    ),
    'A página "{page}" do marcador "{title}" não existe: o documento tem 1 página.': (
        'Page "{page}" of bookmark "{title}" does not exist: the document has 1 page.'
    ),
    'A página "{page}" do marcador "{title}" não existe: o documento tem {count} páginas.': (
        'Page "{page}" of bookmark "{title}" does not exist: the document has {count} pages.'
    ),
    "Procurando os títulos": "Looking for the headings",
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
    # Entrada não confiável (M30)
    "{name} descompacta para mais de {limit} MB: parece malformado e não foi aberto.": (
        "{name} unpacks to more than {limit} MB: it looks malformed and was not opened."
    ),
    "{name} não é um documento do Office válido (.docx, .xlsx ou .pptx).": (
        "{name} is not a valid Office document (.docx, .xlsx or .pptx)."
    ),
    # Propriedades (M29)
    "Descrição": "Description",
    "XMP": "XMP",
    "Salvar a descrição": "Save the description",
    "O pacote XMP completo, como está no arquivo. Se ele existe, salvar a Descrição "
    "grava os mesmos campos nele; uma mudança feita só aqui não muda a Descrição. "
    "Vazio tira o XMP.": (
        "The whole XMP packet, as it is in the file. If there is one, saving the Description "
        "writes the same fields into it; a change made only here does not change the Description. "
        "Empty removes the XMP."
    ),
    "Salvar o XMP": "Save the XMP",
    "Os requisitos de PDF/A que o app verifica foram atendidos. Para converter, use a ferramenta PDF/A.": (
        "The PDF/A requirements the app checks are met. To convert, use the PDF/A tool."
    ),
    "Nenhum problema nos itens de acessibilidade que o app verifica.": (
        "No problem in the accessibility items the app checks."
    ),
    "Propriedades salvas.": "Properties saved.",
    "Falha ao salvar as propriedades: {error}": "Failed to save the properties: {error}",
    "Declara: {pdfa}": "Declares: {pdfa}",
    "O XMP precisa ter x:xmpmeta ou rdf:RDF na raiz.": "The XMP must have x:xmpmeta or rdf:RDF at its root.",
    "O XMP não é um XML válido: {error}": "The XMP is not valid XML: {error}",
    # Anotações (M27)
    "Seta": "Arrow",
    "Trocar a cor": "Change the color",
    "Mover comentário": "Move comment",
    "A anotação ficaria pequena demais.": "The annotation would be too small.",
    # Formulários (M26)
    "Editar campos existentes": "Edit existing fields",
    "A ordem da lista (arraste para mudar)": "The order of the list (drag to change it)",
    "Por linhas": "By rows",
    "Por colunas": "By columns",
    "Aceitar só datas (usa JavaScript)": "Accept only dates (uses JavaScript)",
    "Os leitores com JavaScript (como o Acrobat) recusam o que não for uma data DD/MM/AAAA. "
    "Fica desligado porque põe JavaScript no PDF; sem ele, o campo tem só a dica do formato.": (
        "Readers with JavaScript (such as Acrobat) refuse anything that is not a DD/MM/YYYY date. "
        "It is off because it puts JavaScript in the PDF; without it, the field has only the format hint."
    ),
    "Na ordem de tabulação: arraste para mudar a ordem.": "In tab order: drag to change the order.",
    "Texto que aparece ao passar o mouse (opcional)": "Text shown when hovering (optional)",
    "Somente leitura": "Read only",
    "Obrigatório": "Required",
    "Dica:": "Tooltip:",
    "Aplicar ao campo": "Apply to the field",
    "Remover campo": "Remove field",
    "Gravar ordem": "Save order",
    "Campo alterado com sucesso.": "Field changed successfully.",
    "Ordem de tabulação gravada.": "Tab order saved.",
    "Campo selecionado:": "Selected field:",
    "Ordem de tabulação:": "Tab order:",
    "Falha ao alterar o formulário: {error}": "Failed to change the form: {error}",
    "Escolha um campo da lista.": "Choose a field from the list.",
    'Clique em "Listar campos" primeiro.': 'Click "List fields" first.',
    'Campo "{name}" removido.': 'Field "{name}" removed.',
    'Não há campo chamado "{name}" neste PDF.': 'There is no field named "{name}" in this PDF.',
    "O nome do campo não pode ficar vazio nem ter ponto.": "The field name cannot be empty or contain a dot.",
    "Nenhum campo de formulário encontrado.": "No form fields found.",
    "Falha ao listar campos: {error}": "Failed to list fields: {error}",
    # Form fields: export/import data
    "Exportar dados (FDF)": "Export data (FDF)",
    "Importar dados (FDF)": "Import data (FDF)",
    "Exportar": "Export",
    "Importar": "Import",
    "Exportar dados": "Export data",
    "Importar dados": "Import data",
    "Arquivo FDF com os dados:": "FDF file with the data:",
    "Escolha o arquivo de dados.": "Choose the data file.",
    "Falha ao exportar dados: {error}": "Failed to export data: {error}",
    "Falha ao importar dados: {error}": "Failed to import data: {error}",
    # Form fields: flatten
    "Achatar formulário": "Flatten form",
    "Grava o valor atual de cada campo preenchido como conteúdo estático da "
    "página e remove os widgets interativos. Campos sem valor definido são "
    "deixados como estão.": (
        "Writes the current value of each filled-in field as static page content and "
        "removes the interactive widgets. Fields with no value set are left as they are."
    ),
    "Falha ao achatar formulário: {error}": "Failed to flatten the form: {error}",
    # Menu bar: open PDF
    "Abrir PDF...": "Open PDF...",
    # Document source bar (shared "open document" indicator on tool panels)
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
    "Buscar (Ctrl+F)": "Search (Ctrl+F)",
    "Ajustar à página": "Fit page",
    "Zoom": "Zoom",
    "de {total}": "of {total}",
    "Mais opções de exibição": "More view options",
    # Top bar and document tabs
    "Buscar ferramentas e comandos": "Search tools and commands",
    "Idioma da interface": "Interface language",
    "alterações não salvas": "unsaved changes",
    "Executar a ação da ferramenta": "Run the tool's action",
    # Tool panel (ui/tool_panel.py) and its input/output widgets
    "Opções": "Options",
    "Onde fica o resultado": "Where the result goes",
    "Fechar ferramenta (Esc)": "Close tool (Esc)",
    # Ferramentas, grupos, modos, coluna rápida, busca e Início
    "Achatar": "Flatten",
    "Anotar": "Annotate",
    "Apague de vez áreas, textos e dados ocultos que não devem sair do PDF.": "Permanently remove areas, text and hidden data that must not leave the PDF.",
    "Aplique a mesma operação a todos os PDFs de uma pasta.": "Apply the same operation to every PDF in a folder.",
    "Assinar à mão": "Sign by hand",
    "Bates": "Bates",
    "Busca também por sinônimos: cpf, word, rubrica…": "Also searches synonyms: password, word, initials…",
    "Cabeçalho e rodapé": "Header and footer",
    "Certificado digital": "Digital certificate",
    "Comandos": "Commands",
    "Comparar versões": "Compare versions",
    "Converter e reduzir": "Convert and shrink",
    "Cortar e redimensionar": "Crop and resize",
    "Corte as margens ou mude o tamanho das páginas.": "Crop the margins or change the page size.",
    "Criar": "Create",
    "Crie e edite campos, troque os dados preenchidos ou achate o formulário.": "Create and edit fields, exchange filled-in data or flatten the form.",
    "Crie um PDF vazio, com uma ou mais páginas.": "Create an empty PDF with one or more pages.",
    "Dados": "Data",
    "Dados ocultos": "Hidden data",
    "Diminua o tamanho do arquivo para enviar por e-mail ou guardar.": "Make the file smaller to email or store it.",
    "Diminuir o tamanho": "Make it smaller",
    "Do PDF para…": "From PDF to…",
    "Editar o conteúdo": "Edit the content",
    "Editar texto, imagem e links": "Edit text, images and links",
    "Edite título e autor, converta para PDF/A ou confira a acessibilidade.": "Edit title and author, convert to PDF/A or check accessibility.",
    "Escaneados e OCR": "Scans and OCR",
    "Escolha pelo que você quer fazer. Cada grupo diz para que serve.": "Choose by what you want to do. Each group says what it is for.",
    "Escolha quais camadas do PDF aparecem ao abrir.": "Choose which PDF layers show when it opens.",
    "Escolha uma pasta e uma operação; no fim, um relatório CSV mostra o que deu certo.": (
        "Pick a folder and an operation; at the end, a CSV report shows what worked."
    ),
    "Esconder dados pessoais": "Hide personal data",
    "Escreva na página, assine à mão ou com certificado digital.": "Write on the page, sign by hand or with a digital certificate.",
    "Fixar na coluna rápida": "Pin to the quick column",
    "Formulários e assinaturas": "Forms and signatures",
    "Imagem": "Image",
    "Informações do documento": "Document information",
    "Informações e metadados": "Information and metadata",
    "Juntar PDFs": "Combine PDFs",
    "Juntar, separar e reordenar páginas": "Combine, split and reorder pages",
    "Junte vários PDFs em um só, na ordem que você escolher.": "Combine several PDFs into one, in the order you choose.",
    "Lado a lado": "Side by side",
    "Links": "Links",
    "Lote": "Batch",
    "Mais usadas": "Most used",
    "Marcar, comparar versões e medir": "Mark up, compare versions and measure",
    "Medir": "Measure",
    "Medir distâncias": "Measure distances",
    "Meça a distância entre dois pontos da página.": "Measure the distance between two points on the page.",
    "Modo": "Mode",
    "Modos: {modes}": "Modes: {modes}",
    "Montar e organizar": "Assemble and organize",
    "Monte o sumário de navegação do PDF.": "Build the PDF's navigation outline.",
    "Mudar formato, tamanho e ler escaneados": "Change format and size, read scans",
    "Mudar tamanho": "Change size",
    "Mudar texto, imagens e marcar páginas": "Change text and images, mark pages",
    "Na coluna rápida": "In the quick column",
    "Novo PDF": "New PDF",
    "Novo PDF em branco": "New blank PDF",
    "Numeração e cabeçalho": "Numbering and header",
    "Numere as páginas ou ponha um cabeçalho e um rodapé.": "Number the pages or add a header and footer.",
    "Números de página": "Page numbers",
    "O que você quer fazer? Ex.: assinar, cpf, word": "What do you want to do? E.g.: sign, password, word",
    "Organizar": "Organize",
    "Os PDFs que você abrir aparecem aqui, para voltar a eles com um clique.": "The PDFs you open show up here, so you can get back to them in one click.",
    "Ou comece pelo que você quer fazer": "Or start with what you want to do",
    "Para PDF": "To PDF",
    "Ponha um texto ou um logotipo sobre as páginas.": "Put a text or a logo over the pages.",
    "Por marcador": "By bookmark",
    "Por nº de páginas": "By page count",
    "Por página em branco": "At blank pages",
    "Por tamanho": "By size",
    "Preencher": "Fill in",
    "Propriedades e conformidade": "Properties and compliance",
    "Proteger e privacidade": "Protection and privacy",
    "Proteja o PDF com senha ou tire a senha de um PDF protegido.": "Protect the PDF with a password or remove the password of a protected PDF.",
    "Realce, comente, desenhe e carimbe; depois grave as marcações no PDF.": "Highlight, comment, draw and stamp; then save the markup to the PDF.",
    "Redigir e limpar": "Redact and clean",
    "Reescreva um trecho, troque uma imagem ou mude os links do PDF.": "Rewrite a passage, replace an image or change the PDF's links.",
    "Remover da coluna": "Remove from the column",
    "Reordene, gire, duplique, exclua ou extraia páginas.": "Reorder, rotate, duplicate, delete or extract pages.",
    "Repetir em vários arquivos": "Repeat across many files",
    "Senha e permissões": "Password and permissions",
    "Senha e remoção de dados sensíveis": "Passwords and removal of sensitive data",
    "Separe o PDF em vários arquivos menores.": "Split the PDF into several smaller files.",
    "Sumário": "Outline",
    "Sumário, anexos e propriedades": "Outline, attachments and properties",
    "Tornar pesquisável": "Make searchable",
    "Torne um escaneado pesquisável ou limpe as páginas dele.": "Make a scan searchable or clean up its pages.",
    "Transformar em Word": "Turn into Word",
    "Transforme o PDF em Word, Excel, imagens ou texto, ou crie um PDF a partir deles.": "Turn the PDF into Word, Excel, images or text, or create a PDF from them.",
    "Veja o que mudou entre duas versões de um PDF.": "See what changed between two versions of a PDF.",
    "Veja, adicione, remova ou extraia arquivos anexados.": "View, add, remove or extract attached files.",
    "Visual": "Visual",
    "por “{word}”": "by “{word}”",
    "Áreas": "Areas",
    "Textos e padrões": "Text and patterns",
    "↑↓ navegar · Enter abrir · Tab ver modos": "↑↓ navigate · Enter open · Tab see modes",
    # Painel da ferramenta e Comprimir
    "Quanto comprimir": "How much to compress",
    "Leve": "Light",
    "Equilibrada": "Balanced",
    "Forte": "Strong",
    "recomendada": "recommended",
    "Quase sem diferença visível. As imagens não perdem qualidade.": "Almost no visible difference. Images keep their quality.",
    "Boa para enviar por e-mail. Fotos a 150 DPI.": "Good for sending by email. Photos at 150 DPI.",
    "Menor arquivo; fotos podem perder nitidez. 100 DPI.": "Smallest file; photos may lose sharpness. 100 DPI.",
    "Leve · sem perda": "Light · lossless",
    "Equilibrada · boa para e-mail": "Balanced · good for email",
    "Forte · menor arquivo": "Strong · smallest file",
    "Comprimir PDF": "Compress PDF",
    "Tons de cinza · menor, mas perde a cor": "Grayscale · smaller, but loses color",
    "Pronto: {original} → {compressed}": "Done: {original} → {compressed}",
    "{reduction}% menor.": "{reduction}% smaller.",
    "1 imagem recomprimida.": "1 image recompressed.",
    "{count} imagens recomprimidas.": "{count} images recompressed.",
    "Aplicado neste documento; salve para gravar no arquivo.": "Applied to this document; save to write it to the file.",
    "Gravado em {name}.": "Saved to {name}.",
    "O arquivo não ficaria menor ({original} → {compressed}).": "The file would not get smaller ({original} → {compressed}).",
    "Nada foi gravado. Tente um nível mais forte.": "Nothing was saved. Try a stronger level.",
    "Não foi possível comprimir.": "Could not compress.",
    "Abra ou arraste o PDF que quer diminuir.": "Open or drop the PDF you want to shrink.",
    "Abra ou arraste o PDF que quer usar.": "Open or drop the PDF you want to use.",
    "Neste documento": "In this document",
    "Em um arquivo novo": "In a new file",
    "O arquivo no disco só muda ao salvar. Ctrl+Z desfaz.": "The file on disk only changes when you save. Ctrl+Z undoes.",
    "Abra um PDF para continuar.": "Open a PDF to continue.",
    "Ver detalhes": "See details",
    "{step}… {current} de {total}": "{step}… {current} of {total}",
    "1 página": "1 page",
    # Faixa do topo, barra de status e selo de estado do documento
    "Ajuste e rotação": "Fit and rotation",
    "Modo de exibição": "View mode",
    "Local · nenhum arquivo sai deste computador": "Local · no file leaves this computer",
    "Salvo às {time}": "Saved at {time}",
    "Sem alterações": "No changes",
    "Salvo": "Saved",
    "Não salvo": "Unsaved",
    "1 alteração aplicada, não salva": "1 change applied, not saved",
    "{count} alterações aplicadas, não salvas": "{count} changes applied, not saved",
    "1 em andamento": "1 running",
    "{count} em andamento": "{count} running",
    "1 tarefa em andamento": "1 task running",
    "{count} tarefas em andamento": "{count} tasks running",
    "1 concluída": "1 done",
    "{count} concluídas": "{count} done",
    "1 falhou": "1 failed",
    "{count} falharam": "{count} failed",
    "Operação cancelada.": "Operation cancelled.",
    "Nada foi gravado.": "Nothing was saved.",
    "Tentar de novo": "Try again",
    "Concluir": "Done",
    # Barra de marcação e comentários (Anotações)
    "Barra de marcação": "Markup bar",
    "Marcação": "Markup",
    "Cor: {name}": "Color: {name}",
    "Mais cores...": "More colors...",
    "Cor da marcação": "Markup color",
    "Estilo": "Style",
    "Estilo: cor e espessura": "Style: color and thickness",
    "A cor e a espessura das próximas marcações.": "The color and thickness of the next markups.",
    "Cor": "Color",
    "Sublinhado e riscado": "Underline and strikethrough",
    "Círculo e seta": "Circle and arrow",
    "Espessura": "Thickness",
    "Espessura: {width}": "Thickness: {width}",
    "Diminuir a espessura": "Decrease thickness",
    "Aumentar a espessura": "Increase thickness",
    "Realce, sublinhado e riscado seguem a linha do texto: a espessura vale para caneta, formas e seta.": (
        "Highlight, underline and strikeout follow the text line: thickness applies to the pen, shapes and arrow."
    ),
    "1 pendente": "1 pending",
    "{count} pendentes": "{count} pending",
    "Gravar": "Save",
    "Gravar marcações": "Save markups",
    "Gravar {count} marcações": "Save {count} markups",
    "Gravar as marcações pendentes como uma versão do documento (Ctrl+Z desfaz)": (
        "Save the pending markups as a version of the document (Ctrl+Z undoes)"
    ),
    "Descartar": "Discard",
    "Descarta as marcações ainda não gravadas (Ctrl+Z traz de volta)": (
        "Discards the markups not saved yet (Ctrl+Z brings them back)"
    ),
    "Pendente": "Pending",
    "Gravado": "Saved",
    "Comentários · {count}": "Comments · {count}",
    "Todas as páginas": "All pages",
    "Mostrar os comentários de": "Show the comments of",
    # Tarefas, regiões (F6) e aviso de atualização
    "Tarefas": "Tasks",
    "Miniaturas": "Thumbnails",
    "Buscar": "Search",
    "1 tarefa": "1 task",
    "{count} tarefas": "{count} tasks",
    "Limpar concluídas": "Clear finished",
    "Em andamento": "Running",
    "Concluída": "Finished",
    "Falhou": "Failed",
    "Cancelada": "Cancelled",
    "Próxima região": "Next region",
    "Região anterior": "Previous region",
    "Novidades": "What's new",
    "Edição de {data}.": "Edition of {data}.",
    "Você usa a de {data}.": "You're on {data}.",
    "Ver notas completas": "Full release notes",
    "Avisar quando houver uma nova edição": "Notify me about new editions",
    "Nada é baixado nem instalado sem a sua confirmação. Seus documentos abertos são preservados.": (
        "Nothing is downloaded or installed without your confirmation. Your open documents are kept."
    ),
    # Início, Ferramentas, paleta e Organizar páginas
    "Olá! Abra um PDF para começar.": "Hi! Open a PDF to get started.",
    "Tudo acontece neste computador. Nenhum arquivo sai daqui.": (
        "Everything happens on this computer. No file ever leaves it."
    ),
    "Arraste um PDF para cá": "Drop a PDF here",
    "ou escolha um arquivo no computador": "or choose a file on your computer",
    "Abrir": "Open",
    "Mostrar na pasta": "Show in folder",
    "Remover da lista": "Remove from list",
    "hoje, {hora}": "today, {hora}",
    "ontem": "yesterday",
    "há {n} dias": "{n} days ago",
    "Buscar ferramenta": "Search tools",
    "Todas": "All",
    "Documentos abertos": "Open documents",
    "{count} selecionadas": "{count} selected",
    "Em branco": "Blank",
    "Tamanho das miniaturas": "Thumbnail size",
    "Alterações pendentes · {count}": "Pending changes · {count}",
    "Aplicar {count} alterações": "Apply {count} changes",
    "Volta a grade para o documento como está": "Puts the grid back the way the document is",
    "Desfazer só esta alteração": "Undo just this change",
    "Desfazer: {change}": "Undo: {change}",
    "a página {number}": "page {number}",
    "a página em branco": "the blank page",
    "{count} páginas": "{count} pages",
    "Trocar...": "Change...",
    "Gravar o resultado num arquivo novo": "Save the result to a new file",
    "Nenhum documento aberto": "No document open",
    "Arraste um PDF para cá ou escolha um arquivo no computador.": "Drop a PDF here or choose a file on your computer.",
    "Abrir arquivo...": "Open file...",
    "Página {current} de {total}": "Page {current} of {total}",
    "Página {number}": "Page {number}",
    # PDF viewer: opening documents
    "Abrir PDF": "Open PDF",
    "PDF protegido por senha": "Password-protected PDF",
    "Este PDF está protegido por senha. Digite a senha para abri-lo:": (
        "This PDF is password-protected. Enter the password to open it:"
    ),
    "Senha incorreta. Tente novamente:": "Wrong password. Try again:",
    "Não foi possível abrir o PDF: {error}": "Could not open the PDF: {error}",
    # PDF viewer search bar
    "Buscar no documento...": "Search the document...",
    "Ocorrência anterior": "Previous match",
    "Próxima ocorrência": "Next match",
    "Fechar": "Close",
    "Nenhuma ocorrência": "No matches",
    "{current} de {total}": "{current} of {total}",
    # Annotations: sidebar section
    "Anotações": "Annotations",
    "Realce, sublinhe, risque, adicione notas, desenhe ou carimbe sobre um PDF; edite, remova e troque comentários por XFDF.": (
        "Highlight, underline, strike through, add notes, draw, or stamp over a PDF; edit, remove "
        "and exchange comments via XFDF."
    ),
    # Measure: sidebar section
    "Medição": "Measurement",
    "Meça a distância entre dois pontos de um PDF, arrastando no visualizador central.": (
        "Measure the distance between two points of a PDF by dragging over the central viewer."
    ),
    "1 comentário excluído, com as respostas.": "1 comment deleted, with its replies.",
    "{count} comentários excluídos, com as respostas.": "{count} comments deleted, with their replies.",
    "1 comentário exportado.": "1 comment exported.",
    "{count} comentários exportados.": "{count} comments exported.",
    "1 comentário importado.": "1 comment imported.",
    "{count} comentários importados.": "{count} comments imported.",
    "1 de tipo que o XFDF não leva (anexo, som...) ficou de fora.": "1 of a type XFDF does not carry (attachment, sound...) was left out.",
    "{count} de tipo que o XFDF não leva (anexo, som...) ficaram de fora.": "{count} of a type XFDF does not carry (attachment, sound...) were left out.",
    "1 ficou como estava: carimbos, textos livres e polígonos têm o desenho fixo.": "1 stayed as it was: stamps, free text and polygons have a fixed drawing.",
    "{count} ficaram como estavam: carimbos, textos livres e polígonos têm o desenho fixo.": "{count} stayed as they were: stamps, free text and polygons have a fixed drawing.",
    "1 ficou de fora: tipo não suportado, página que não existe ou dados inválidos.": "1 was left out: unsupported type, a page that does not exist or invalid data.",
    "{count} ficaram de fora: tipo não suportado, página que não existe ou dados inválidos.": "{count} were left out: unsupported type, a page that does not exist or invalid data.",
    "1 marcação gravada.": "1 markup saved.",
    "{count} marcações gravadas.": "{count} markups saved.",
    "1 pág.": "1 p.",
    "{count} págs.": "{count} pp.",
    "pág. {number}": "p. {number}",
    "1 selecionado": "1 selected",
    "{count} selecionados": "{count} selected",
    "Arraste uma marcação na página para movê-la. Selecione várias com Ctrl para mudar a cor ou excluir de uma vez.": "Drag a markup on the page to move it. Select several with Ctrl to change the color or delete them at once.",
    "Autor do comentário": "Comment author",
    "Autor dos comentários novos": "Author of new comments",
    "Cor trocada em 1 comentário.": "Color changed on 1 comment.",
    "Cor trocada em {count} comentários.": "Color changed on {count} comments.",
    "Descartar {count}": "Discard {count}",
    "Excluir": "Delete",
    "Excluir comentários": "Delete comments",
    "Excluir {count}": "Delete {count}",
    "Exportar e importar comentários": "Export and import comments",
    "Gravados {count}": "Saved {count}",
    "Pendentes {count}": "Pending {count}",
    "Todos": "All",
    "Gravar 1 marcação": "Save 1 markup",
    "Mudar o autor": "Change the author",
    "Mudar o autor...": "Change the author...",
    "Nada para gravar": "Nothing to save",
    "Nenhum comentário ainda. As marcações que você fizer na página aparecem aqui.": "No comments yet. The markups you make on the page show up here.",
    "Não foi possível exportar os comentários.": "Could not export the comments.",
    "O nome que os leitores de PDF mostram em cada comentário. Fica guardado.": "The name PDF readers show on each comment. It is remembered.",
    "O texto deste comentário faz parte do desenho: exclua-o e crie outro.": "This comment's text is part of its drawing: delete it and make another.",
    "Opções avançadas": "Advanced options",
    "autor dos comentários": "comment author",
    "Novas marcações": "New markups",
    "Remove o carimbo salvo que está escolhido": "Removes the saved stamp that is picked",
    "Salvar carimbo": "Save stamp",
    "Salvar texto": "Save text",
    "Texto da nota": "Note text",
    "Texto do carimbo": "Stamp text",
    "comentários": "comments",
    "Nota adesiva": "Sticky note",
    "{more}: no ▾ (ou seta para baixo).": "{more}: in the ▾ (or the down arrow).",
    "Arraste sobre o texto para realçá-lo.": "Drag over the text to highlight it.",
    "Arraste para desenhar um retângulo.": "Drag to draw a rectangle.",
    "Arquivo só com os comentários, para levá-los a outro leitor de PDF sem enviar o documento.": "A file with just the comments, to take them to another PDF reader without sending the document.",
    "Planilha CSV...": "CSV spreadsheet...",
    "Planilha do Excel...": "Excel spreadsheet...",
    "XFDF (só os comentários)...": "XFDF (comments only)...",
    "1 página salva em {name}.": "1 page saved to {name}.",
    "{count} páginas salvas em {name}.": "{count} pages saved to {name}.",
    "1 selecionada": "1 selected",
    "Aplicar 1 alteração": "Apply 1 change",
    "Desfazer tudo": "Undo all",
    "Duplicar {pages}": "Duplicate {pages}",
    "Excluir {pages}": "Delete {pages}",
    "Gira as selecionadas 90° à direita. À esquerda fica no ▾.": "Rotates the selected pages 90° right. Left is in the ▾.",
    "Girar": "Rotate",
    "Girar {pages} em 90°": "Rotate {pages} by 90°",
    "Girar {pages} em 90° à esquerda": "Rotate {pages} by 90° left",
    "Inserir em branco": "Insert blank",
    "Inserir página em branco após a {number}": "Insert a blank page after page {number}",
    "Inserir página em branco no fim": "Insert a blank page at the end",
    "Marca as selecionadas para excluir ao aplicar (Delete)": "Marks the selected pages to delete when you apply (Delete)",
    "Mover {pages} para antes da {number}": "Move {pages} before page {number}",
    "Mover {pages} para o fim": "Move {pages} to the end",
    "Nada muda no documento até você aplicar. Para mover, arraste a miniatura; a linha azul mostra onde ela vai entrar.": "Nothing changes in the document until you apply. To move, drag the thumbnail; the blue line shows where it goes.",
    "Nenhuma alteração ainda. Gire, duplique, exclua ou arraste as páginas na grade.": "No changes yet. Rotate, duplicate, delete or drag the pages in the grid.",
    "Selecione páginas para girar, duplicar, extrair ou excluir.": "Select pages to rotate, duplicate, extract or delete.",
    "as páginas {pages} e {last}": "pages {pages} and {last}",
    "{number} · excluir": "{number} · delete",
    "{page}, a excluir": "{page}, to delete",
    "As operações que você rodar aparecem aqui, com o andamento de cada uma.": "The operations you run show up here, with the progress of each one.",
    "Ver motivo": "See why",
    "agora": "just now",
    "cancelada por você": "canceled by you",
    "há {n} min": "{n} min ago",
    "{done} de {total}": "{done} of {total}",
    "1 página enviada para a impressora.": "1 page sent to the printer.",
    "{count} páginas enviadas para a impressora.": "{count} pages sent to the printer.",
    "1 anexo extraído.": "1 attachment extracted.",
    "{count} anexos extraídos.": "{count} attachments extracted.",
    "1 PDF na pasta.": "1 PDF in the folder.",
    "{count} PDFs na pasta.": "{count} PDFs in the folder.",
    "{done} de 1 arquivo processado em {folder}.": "{done} of 1 file processed in {folder}.",
    "{done} de {count} arquivos processados em {folder}.": "{done} of {count} files processed in {folder}.",
    "Página {page}: 1 linha diferente — {preview}": "Page {page}: 1 different line — {preview}",
    "Página {page}: {count} linhas diferentes — {preview}": "Page {page}: {count} different lines — {preview}",
    "1 imagem gerada.": "1 image created.",
    "{count} imagens geradas.": "{count} images created.",
    "1 página editada.": "1 page edited.",
    "{count} páginas editadas.": "{count} pages edited.",
    "1 imagem extraída.": "1 image extracted.",
    "{count} imagens extraídas.": "{count} images extracted.",
    "1 campo exportado.": "1 field exported.",
    "{count} campos exportados.": "{count} fields exported.",
    "1 campo preenchido.": "1 field filled.",
    "{count} campos preenchidos.": "{count} fields filled.",
    "1 campo achatado.": "1 field flattened.",
    "{count} campos achatados.": "{count} fields flattened.",
    "Texto reconhecido em 1 página.": "Text recognized on 1 page.",
    "Texto reconhecido em {count} páginas.": "Text recognized on {count} pages.",
    "1 script ou ação de JavaScript": "1 JavaScript script or action",
    "{count} scripts ou ações de JavaScript": "{count} JavaScript scripts or actions",
    "1 arquivo embutido": "1 embedded file",
    "{count} arquivos embutidos": "{count} embedded files",
    "1 anotação": "1 annotation",
    "{count} anotações": "{count} annotations",
    "1 área marcada para redação": "1 area marked for redaction",
    "{count} áreas marcadas para redação": "{count} areas marked for redaction",
    "1 página redigida.": "1 page redacted.",
    "{count} páginas redigidas.": "{count} pages redacted.",
    "1 revisão gravada depois desta assinatura": "1 revision saved after this signature",
    "{count} revisões gravadas depois desta assinatura": "{count} revisions saved after this signature",
    "PDF dividido em 1 arquivo.": "PDF split into 1 file.",
    "PDF dividido em {count} arquivos.": "PDF split into {count} files.",
    "1 campo": "1 field",
    "{count} campos": "{count} fields",
    "1 fonte.": "1 font.",
    "{count} fontes.": "{count} fonts.",
    "1 diferença no texto.": "1 difference in the text.",
    "{count} diferenças no texto.": "{count} differences in the text.",
    "Intercalar frente e verso": "Interleave front and back",
    "Use quando frentes e versos foram escaneados em arquivos separados.": "Use it when fronts and backs were scanned into separate files.",
    "Arquivos, na ordem em que vão aparecer": "Files, in the order they will appear",
    "Mesclar 1 PDF": "Merge 1 PDF",
    "Mesclar {count} PDFs": "Merge {count} PDFs",
    "Mesclar PDFs": "Merge PDFs",
    "1 PDF juntado num só.": "1 PDF combined into one.",
    "{count} PDFs juntados num só.": "{count} PDFs combined into one.",
    "O reconhecimento de texto não está instalado neste computador.": "Text recognition is not installed on this computer.",
    "Nenhum idioma de reconhecimento instalado.": "No recognition language installed.",
    "Idiomas disponíveis: {languages}.": "Available languages: {languages}.",
    "Para reconhecer português, instale o idioma português do reconhecimento de texto.": "To recognize Portuguese, install the Portuguese language for text recognition.",
    "{task}: pronto.": "{task}: done.",
    "Páginas organizadas. Aplicado neste documento; salve para gravar no arquivo.": "Pages organized. Applied to this document; save to write it to the file.",
    "Todas · ex.: 1-3, 5, 8-": "All · e.g. 1-3, 5, 8-",
    "O reconhecimento de texto não está instalado. Instale-o para usar esta ferramenta.": "Text recognition is not installed. Install it to use this tool.",
    "O reconhecimento de texto não está instalado: veja a ferramenta Escaneados e OCR.": "Text recognition is not installed: see the Scans and OCR tool.",
    "Requer a detecção de orientação do reconhecimento de texto.": "Needs the orientation detection of text recognition.",
    "{items} e {last}": "{items} and {last}",
    "Padrão de assinatura em PDF que mantém a assinatura verificável por muitos anos.": "A PDF signature standard that keeps the signature verifiable for many years.",
    "Comprova quando o documento foi assinado. Usa a internet: só um resumo do arquivo é enviado, nunca o PDF.": "Proves when the document was signed. Uses the internet: only a digest of the file is sent, never the PDF.",
    "Numeração sequencial usada em processos (ex.: DOC000123) que continua de um arquivo para o outro.": "Sequential numbering used in legal cases (e.g. DOC000123) that carries on from one file to the next.",
    "Resolução das imagens. Mais DPI, mais nitidez e arquivo maior. 150 é bom para tela; 300, para impressão.": "Image resolution. More DPI, sharper images and a bigger file. 150 is good for screens; 300 for print.",
    "1 figura tagueada sem texto alternativo (/Alt).": "1 tagged figure without alternative text (/Alt).",
    "{count} figuras tagueadas sem texto alternativo (/Alt).": "{count} tagged figures without alternative text (/Alt).",
    "1 página com links ou campos sem ordem de tabulação pela estrutura (/Tabs /S).": "1 page with links or fields without a tab order by structure (/Tabs /S).",
    "{count} páginas com links ou campos sem ordem de tabulação pela estrutura (/Tabs /S).": "{count} pages with links or fields without a tab order by structure (/Tabs /S).",
    "1 campo de formulário sem descrição para leitores de tela (/TU): {names}.": "1 form field without a description for screen readers (/TU): {names}.",
    "{count} campos de formulário sem descrição para leitores de tela (/TU): {names}.": "{count} form fields without a description for screen readers (/TU): {names}.",
    "{label} {page} não existe: o documento tem 1 página.": "{label} {page} does not exist: the document has 1 page.",
    "{label} {page} não existe: o documento tem {count} páginas.": "{label} {page} does not exist: the document has {count} pages.",
    "O documento tem 1 página: confira as páginas informadas.": "The document has 1 page: check the pages you entered.",
    "O documento tem {count} páginas: confira as páginas informadas.": "The document has {count} pages: check the pages you entered.",
    "{name} tem 1 página: confira as páginas escolhidas.": "{name} has 1 page: check the pages you picked.",
    "{name} tem {count} páginas: confira as páginas escolhidas.": "{name} has {count} pages: check the pages you picked.",
    "A imagem {number} não existe: a página tem 1 imagem.": "Image {number} does not exist: the page has 1 image.",
    "A imagem {number} não existe: a página tem {count} imagens.": "Image {number} does not exist: the page has {count} images.",
    "A camada {number} não existe: o documento tem 1 camada.": "Layer {number} does not exist: the document has 1 layer.",
    "A camada {number} não existe: o documento tem {count} camadas.": "Layer {number} does not exist: the document has {count} layers.",
    "O link {number} não existe: a página tem 1 link.": "Link {number} does not exist: the page has 1 link.",
    "O link {number} não existe: a página tem {count} links.": "Link {number} does not exist: the page has {count} links.",
    "1 slide com texto demais para uma página continuou na página seguinte.": "1 slide with too much text for one page carried on to the next page.",
    "{count} slides com texto demais para uma página continuaram na página seguinte.": "{count} slides with too much text for one page carried on to the next page.",
    "Página repetida na nova ordem: {pages}.": "Page repeated in the new order: {pages}.",
    "Páginas repetidas na nova ordem: {pages}.": "Pages repeated in the new order: {pages}.",
    "Posição de inserção inválida: o documento tem 1 página; dá para inserir antes ou depois dela.": "Invalid insert position: the document has 1 page; you can insert before or after it.",
    "Posição de inserção inválida: o documento tem {count} páginas; dá para inserir antes da página 1 até depois da página {count}.": "Invalid insert position: the document has {count} pages; you can insert from before page 1 to after page {count}.",
    "Intervalo inválido: a página final precisa vir depois da inicial ({start}) e o documento tem 1 página.": "Invalid range: the last page has to come after the first ({start}) and the document has 1 page.",
    "Intervalo inválido: a página final precisa vir depois da inicial ({start}) e o documento tem {count} páginas.": "Invalid range: the last page has to come after the first ({start}) and the document has {count} pages.",
    "1 ação proibida removida (JavaScript, abrir programas, ações automáticas).": "1 forbidden action removed (JavaScript, launching programs, automatic actions).",
    "{count} ações proibidas removidas (JavaScript, abrir programas, ações automáticas).": "{count} forbidden actions removed (JavaScript, launching programs, automatic actions).",
    "1 anexo removido: o PDF/A-{part} não permite esse anexo.": "1 attachment removed: PDF/A-{part} does not allow it.",
    "{count} anexos removidos: o PDF/A-{part} não permite esses anexos.": "{count} attachments removed: PDF/A-{part} does not allow them.",
    "1 anotação removida (multimídia, escondida ou com anexo não permitido).": "1 annotation removed (multimedia, hidden or with an attachment that is not allowed).",
    "{count} anotações removidas (multimídia, escondidas ou com anexo não permitido).": "{count} annotations removed (multimedia, hidden or with an attachment that is not allowed).",
    "1 anotação marcada para impressão, como o PDF/A exige.": "1 annotation marked for printing, as PDF/A requires.",
    "{count} anotações marcadas para impressão, como o PDF/A exige.": "{count} annotations marked for printing, as PDF/A requires.",
    "1 stream com compressão LZW recodificado.": "1 LZW-compressed stream re-encoded.",
    "{count} streams com compressão LZW recodificados.": "{count} LZW-compressed streams re-encoded.",
    "1 anotação sem aparência definida (/AP).": "1 annotation without a defined appearance (/AP).",
    "{count} anotações sem aparência definida (/AP).": "{count} annotations without a defined appearance (/AP).",
    "Assinatura com validade criptográfica: quem receber o PDF consegue conferir quem assinou e se ele mudou depois.": "A signature with cryptographic validity: whoever gets the PDF can check who signed it and whether it changed afterwards.",
    "Revise a lista antes de aplicar.": "Review the list before applying.",
    # Annotations: tools
    "Selecionar": "Select",
    "Realce": "Highlight",
    "Sublinhado": "Underline",
    "Riscado": "Strikethrough",
    "Clique numa marcação para escolhê-la; arraste para movê-la.": "Click a markup to pick it; drag to move it.",
    "Arraste sobre o texto para sublinhá-lo.": "Drag over the text to underline it.",
    "Arraste sobre o texto para riscá-lo.": "Drag over the text to strike it through.",
    "Clique na página para deixar um comentário.": "Click the page to leave a comment.",
    "Desenhe à mão livre sobre a página.": "Draw freehand on the page.",
    "Arraste para desenhar um círculo.": "Drag to draw a circle.",
    "Arraste para desenhar uma seta.": "Drag to draw an arrow.",
    "Clique na página para pôr o carimbo escolhido no painel.": "Click the page to place the stamp picked in the panel.",
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
    "Cor:": "Color:",
    "Adicione pelo menos uma anotação antes de salvar.": "Add at least one annotation before saving.",
    "Falha ao salvar anotações: {error}": "Failed to save annotations: {error}",
    # Annotations: sticky-note dialog (viewer)
    "Texto da nota:": "Note text:",
    # OCR: sidebar section
    "OCR": "OCR",
    # OCR: page UI
    "Reconhecer texto": "Recognize text",
    "Falha ao reconhecer texto: {error}": "Failed to recognize text: {error}",
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
    "Arraste no visualizador para marcar as áreas a apagar.": "Drag over the viewer to mark the areas to erase.",
    "Cada página marcada vira uma imagem, com as áreas pintadas de preto na própria "
    "imagem — e perde a camada de texto pesquisável inteira, não só a área marcada. "
    "O resultado é conferido antes de ser salvo.": (
        "Each marked page becomes an image, with the areas painted black in the image itself "
        "— and it loses the entire searchable text layer, not just the marked area. The result "
        "is checked before it is saved."
    ),
    "Textos a procurar": "Text to search for",
    "Todas as ocorrências são marcadas. Maiúsculas e acentos não importam; separe vários com ;": (
        "Every occurrence is marked. Case and accents don't matter; separate several with ;"
    ),
    "Ex.: Maria da Silva; Rua das Flores": "E.g.: John Smith; Main Street",
    "Padrões de dado sensível": "Sensitive data patterns",
    "Texto buscado": "Searched text",
    "CPF": "CPF",
    "CNPJ": "CNPJ",
    "Telefone": "Phone",
    "Cartão de crédito": "Credit card",
    "Expressão regular personalizada (opcional)": "Custom regular expression (optional)",
    "Procurar e marcar": "Search and mark",
    "Digite um texto a procurar, marque um padrão ou digite uma expressão regular.": (
        "Type a text to search for, check a pattern or enter a regular expression."
    ),
    "Falha ao detectar padrões: {error}": "Failed to detect patterns: {error}",
    "1 ocorrência encontrada": "1 occurrence found",
    "{count} ocorrências encontradas": "{count} occurrences found",
    "1 nova marcada para redação.": "1 new one marked for redaction.",
    "{count} novas marcadas para redação.": "{count} new ones marked for redaction.",
    "Expressão personalizada": "Custom expression",
    "área marcada à mão": "area marked by hand",
    "Selecione uma área para vê-la destacada no visualizador.": (
        "Select an area to see it highlighted in the viewer."
    ),
    "Remover selecionadas": "Remove selected",
    "Limpar todas": "Clear all",
    "Selecione na lista as áreas a remover.": "Select the areas to remove in the list.",
    "Também sanitizar o documento": "Also sanitize the document",
    "O texto apagado pode aparecer também no título, nos metadados ou em anexos. "
    "Com esta opção, o arquivo redigido também passa pela sanitização.": (
        "The erased text may also appear in the title, the metadata, or attachments. "
        "With this option, the redacted file also goes through sanitization."
    ),
    "A redação é irreversível: cada página marcada vira uma imagem achatada e "
    "perde toda a camada de texto pesquisável, não só a área marcada. Continuar?": (
        "Redaction is irreversible: each marked page becomes a flattened image and "
        "loses its entire searchable text layer, not just the marked area. Continue?"
    ),
    "Aplicar redação": "Apply redaction",
    "Marque pelo menos uma área no visualizador antes de aplicar.": (
        "Mark at least one area in the viewer before applying."
    ),
    "Falha ao redigir: {error}": "Failed to redact: {error}",
    "Remover metadados": "Remove metadata",
    "Remover anotações e comentários": "Remove annotations and comments",
    "JavaScript, ações que abrem arquivos ou programas ou enviam dados, e arquivos "
    "embutidos são sempre removidos. O resultado é conferido antes de ser salvo.": (
        "JavaScript, actions that open files or programs or send data, and embedded "
        "files are always removed. The result is checked before it is saved."
    ),
    "Falha ao sanitizar: {error}": "Failed to sanitize: {error}",
    "PDF sanitizado com sucesso.": "PDF sanitized successfully.",
    "Removido:": "Removed:",
    "Nada perigoso foi encontrado no documento.": "Nothing dangerous was found in the document.",
    "1 ação que abre arquivos ou programas, envia dados ou acessa conteúdo externo": (
        "1 action that opens files or programs, sends data, or accesses external content"
    ),
    "{count} ações que abrem arquivos ou programas, enviam dados ou acessam conteúdo externo": (
        "{count} actions that open files or programs, send data, or access external content"
    ),
    "1 item de dados privados de aplicativos, miniaturas ou metadados de páginas e imagens": (
        "1 item of private application data, thumbnails, or page and image metadata"
    ),
    "{count} itens de dados privados de aplicativos, miniaturas ou metadados de páginas e imagens": (
        "{count} items of private application data, thumbnails, or page and image metadata"
    ),
    "metadados do documento (título, autor e outros)": "document metadata (title, author, and others)",
    "formulário XFA (pode conter scripts)": "XFA form (may contain scripts)",
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
    "Certificado:": "Certificate:",
    "Página:": "Page:",
    "Posição do selo:": "Stamp position:",
    "Inferior direito": "Bottom right",
    "Inferior esquerdo": "Bottom left",
    "Superior direito": "Top right",
    "Superior esquerdo": "Top left",
    "Certificado (*.pfx *.p12)": "Certificate (*.pfx *.p12)",
    "Arquivo .pfx/.p12:": "Certificate file (.pfx/.p12):",
    "Senha do certificado": "Certificate password",
    "Certificado autoassinado gerado na hora, sem validade jurídica — use só "
    "para testar o fluxo ou assinaturas de uso pessoal/interno.": (
        "Self-signed certificate generated on the spot, with no legal validity — use it only "
        "to test the flow or for personal/internal signatures."
    ),
    "Nome completo": "Full name",
    "E-mail": "Email",
    "Nome:": "Name:",
    "E-mail:": "Email:",
    "Arquivo PDF a verificar (vazio = o documento aberto):": (
        "PDF file to verify (empty = the open document):"
    ),
    "Verificar": "Verify",
    "O PDF de entrada não tem páginas.": "The input PDF has no pages.",
    "Escolha o arquivo .pfx/.p12.": "Choose the .pfx/.p12 file.",
    "Digite o nome para o certificado de teste.": "Enter the name for the test certificate.",
    "Falha ao assinar: {error}": "Failed to sign: {error}",
    "PDF assinado com sucesso.": "PDF signed successfully.",
    "Escolha o arquivo PDF a verificar.": "Choose the PDF file to verify.",
    "Falha ao verificar: {error}": "Failed to verify: {error}",
    "Nenhuma assinatura encontrada neste PDF.": "No signature found in this PDF.",
    'Assinatura {number} de {total} — campo "{field}"': 'Signature {number} of {total} — field "{field}"',
    "Resultado: {verdict}": "Result: {verdict}",
    "VÁLIDA": "VALID",
    "VÁLIDA, COM RESSALVAS": "VALID, WITH CAVEATS",
    "INVÁLIDA": "INVALID",
    "Não foi possível verificar esta assinatura: {error}": "This signature could not be verified: {error}",
    "{name} (certificado autoassinado)": "{name} (self-signed certificate)",
    "Signatário (segundo o certificado): {name}": "Signer (according to the certificate): {name}",
    "Emitido por: {issuer}": "Issued by: {issuer}",
    "Validade do certificado: {start} a {end}": "Certificate validity: {start} to {end}",
    "Data declarada pelo signatário: {date}": "Date declared by the signer: {date}",
    "Conteúdo assinado: {status}": "Signed content: {status}",
    "íntegro": "intact",
    "ALTERADO depois da assinatura": "CHANGED after signing",
    "Assinatura criptográfica: {status}": "Cryptographic signature: {status}",
    "válida": "valid",
    "Alterações depois da assinatura: {status}": "Changes after signing: {status}",
    "nenhuma — a assinatura cobre o documento inteiro": "none — the signature covers the whole document",
    "a assinatura não cobre o documento de forma padrão — trate como suspeito": (
        "the signature does not cover the document in the standard way — treat it as suspicious"
    ),
    "sem mudança de conteúdo": "no content change",
    "só manutenção de assinaturas (carimbos de tempo e dados de validação)": (
        "signature maintenance only (timestamps and validation data)"
    ),
    "só preenchimento de formulário e novas assinaturas": "form filling and new signatures only",
    "comentários e anotações": "comments and annotations",
    "ALTERAÇÕES NO CONTEÚDO — o documento pode ter sido adulterado depois de assinado": (
        "CONTENT CHANGES — the document may have been tampered with after signing"
    ),
    "não foi possível analisar o que mudou": "it was not possible to analyze what changed",
    "Confiança no certificado: {status}": "Certificate trust: {status}",
    "validado até uma autoridade certificadora confiável do sistema": (
        "validated up to a certificate authority trusted by the system"
    ),
    "não confiável — certificado autoassinado (sem validade jurídica)": (
        "not trusted — self-signed certificate (no legal validity)"
    ),
    "não confiável — não foi possível validar a cadeia até uma autoridade confiável do "
    "sistema (para certificados ICP-Brasil, a cadeia da ICP-Brasil precisa estar instalada)": (
        "not trusted — the chain could not be validated up to an authority trusted by the "
        "system (for ICP-Brasil certificates, the ICP-Brasil chain must be installed)"
    ),
    # PDF/A
    "Converter para PDF/A": "Convert to PDF/A",
    "Validar PDF/A": "Validate PDF/A",
    "Parte (PDF/A-N):": "Part (PDF/A-N):",
    "Nível de conformidade:": "Conformance level:",
    "A (acessível)": "A (accessible)",
    "B (básica)": "B (basic)",
    "U (Unicode)": "U (Unicode)",
    "PDF convertido com sucesso.": "PDF converted successfully.",
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
    "Número da imagem na página:": "Image number on the page:",
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
    # Edit: links
    "URL externa": "External URL",
    "Página do documento": "Document page",
    "Destino:": "Target:",
    "Digite a URL de destino.": "Enter the target URL.",
    "Falha ao adicionar link: {error}": "Failed to add link: {error}",
    "Link adicionado com sucesso.": "Link added successfully.",
    "Falha ao listar links: {error}": "Failed to list links: {error}",
    "Nenhum link encontrado.": "No links found.",
    "Número do link na página:": "Link number on the page:",
    "Falha ao remover link: {error}": "Failed to remove link: {error}",
    "Link removido com sucesso.": "Link removed successfully.",
    # Annotations: export comments
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
    "Número da camada:": "Layer number:",
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
    'Anexo "{name}" adicionado com sucesso.': 'Attachment "{name}" added successfully.',
    "Use a senha de abertura ou, num PDF com restrições (que abre sem senha), "
    "a senha de permissões.": (
        "Use the open password or, for a restricted PDF (which opens without a "
        "password), the permissions password."
    ),
    "Sem campo correspondente no PDF (ignorados): {names}": (
        "No matching field in the PDF (ignored): {names}"
    ),
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
    "Digite o texto do carimbo antes de salvar.": "Enter the stamp text before saving.",
    "Falha ao salvar carimbo: {error}": "Failed to save stamp: {error}",
    "Carimbo salvo com sucesso.": "Stamp saved successfully.",
    "Selecione um carimbo customizado para remover.": "Select a custom stamp to remove.",
    # Etapa 3: operações em segundo plano, log e busca incremental
    'Aguarde "{task}" terminar, ou cancele essa operação.': 'Wait for "{task}" to finish, or cancel it.',
    'Cancelar': 'Cancel',
    'Cancelando...': 'Cancelling...',
    'Operação cancelada: nada foi gravado.': 'Operation cancelled: nothing was saved.',
    'Operação em andamento': 'Operation in progress',
    '"{task}" ainda está em andamento. Cancelar e sair?': '"{task}" is still running. Cancel it and quit?',
    'Reconhecendo o texto': 'Recognizing text',
    'Gravando': 'Saving',
    'Procurando dados sensíveis': 'Looking for sensitive data',
    'Redigindo páginas': 'Redacting pages',
    'Verificando o resultado': 'Verifying the result',
    'Comparando páginas': 'Comparing pages',
    'Convertendo páginas': 'Converting pages',
    'Lendo as imagens': 'Reading the images',
    'Editando páginas': 'Editing pages',
    'Comprimindo páginas': 'Compressing pages',
    'Removendo objetos repetidos': 'Removing duplicate objects',
    'Convertendo o documento': 'Converting the document',
    'Lendo os arquivos': 'Reading the files',
    'Erro inesperado': 'Unexpected error',
    'Ocorreu um erro inesperado: {error}': 'An unexpected error occurred: {error}',
    'Os detalhes foram gravados em:\n{path}': 'The details were saved to:\n{path}',
    'Buscando...': 'Searching...',
    # Etapa 4: qualidade das ferramentas
    'Nível de compressão:': 'Compression level:',
    'Comprimindo imagens': 'Compressing images',
    'Tamanho da página:': 'Page size:',
    'Margem:': 'Margin:',
    'DPI da imagem:': 'Image DPI:',
    'A4': 'A4',
    'Ajustar ao tamanho da imagem': 'Fit to the image size',
    'Resolução usada para calcular o tamanho da página a partir da imagem.': (
        'Resolution used to compute the page size from the image.'
    ),
    'Documentos do Office': 'Office documents',
    'A conversão básica deixou de fora:': 'The basic conversion left out:',
    'Páginas em paisagem (linhas mais longas)': 'Landscape pages (longer lines)',
    'Informe ao menos uma imagem para converter.': 'Provide at least one image to convert.',
    'A margem não pode ser negativa.': 'The margin cannot be negative.',
    'O DPI precisa ser maior que zero.': 'DPI must be greater than zero.',
    'A margem é maior que a página.': 'The margin is larger than the page.',
    'As imagens do documento não foram incluídas.': "The document's images were not included.",
    'Cabeçalhos e rodapés não foram incluídos.': 'Headers and footers were not included.',
    'As imagens e gráficos dos slides não foram incluídos.': (
        "The slides' images and charts were not included."
    ),
    'Formato não suportado: {suffix}': 'Unsupported format: {suffix}',
    'Gráficos e imagens da planilha "{sheet}" não foram incluídos.': (
        'Charts and images of the "{sheet}" sheet were not included.'
    ),
    'A planilha "{sheet}" tem {columns} colunas; só as {limit} primeiras foram incluídas.': (
        'The "{sheet}" sheet has {columns} columns; only the first {limit} were included.'
    ),
    'Ajustar sem distorcer (sobra transparente)': 'Fit without distortion (transparent margins)',
    'Esticar para ocupar a área toda': 'Stretch to fill the whole area',
    'Se a proporção for diferente:': 'If the proportions differ:',
    'A mesma imagem também aparecia na página {pages}, que mudou junto.': (
        'The same image also appeared on page {pages}, which changed too.'
    ),
    'A mesma imagem também aparecia nas páginas {pages}, que mudaram junto.': (
        'The same image also appeared on pages {pages}, which changed too.'
    ),
    'Arraste no visualizador para marcar cada área. As coordenadas (em pontos PDF) podem ser ajustadas na tabela.': (
        'Drag over the viewer to mark each area. The coordinates (in PDF points) can be adjusted in the table.'
    ),
    'Texto novo da área selecionada (Enter quebra a linha)': (
        'New text for the selected area (Enter starts a new line)'
    ),
    'Fonte:': 'Font:',
    'Sem serifa': 'Sans serif',
    'Sem serifa, negrito': 'Sans serif, bold',
    'Monoespaçada': 'Monospaced',
    'Cor do texto:': 'Text color:',
    'Cor de fundo da área:': 'Area background color:',
    'Esquerda': 'Left',
    'Base': 'Bottom',
    'Direita': 'Right',
    'Topo': 'Top',
    'Esquerda / Base / Direita / Topo (pontos PDF):': 'Left / Bottom / Right / Top (PDF points):',
    'O texto não coube inteiro na área {areas}: o que não coube ficou de fora. Aumente a área ou diminua a fonte.': (
        'The text did not fit entirely in area {areas}: what did not fit was left out. Enlarge the area or reduce the font.'
    ),
    'O texto não coube inteiro nas áreas {areas}: o que não coube ficou de fora. Aumente as áreas ou diminua a fonte.': (
        'The text did not fit entirely in areas {areas}: what did not fit was left out. Enlarge the areas or reduce the font.'
    ),
    'https://exemplo.com': 'https://example.com',
    'Esta imagem está gravada dentro do conteúdo da página (imagem inline) e não pode ser substituída sem reescrever a página. Use Editar texto ou a redação para cobri-la.': (
        'This image is stored inside the page content (inline image) and cannot be replaced without rewriting the page. Use Edit text or redaction to cover it.'
    ),
    'Informe uma URL ou uma página de destino — exatamente uma das duas.': (
        'Provide a URL or a target page — exactly one of them.'
    ),
    'Esta página não tem nenhum link.': 'This page has no links.',
    'página {page}': 'page {page}',
    'destino interno': 'internal destination',
    'ação: {action}': 'action: {action}',
    'sem destino': 'no destination',
    'Página de destino': 'Target page',
    'Branco': 'White',
    'Cinza': 'Gray',
    'Outra cor...': 'Other color...',
    'Escolher cor': 'Choose color',
    'Exportar dados (CSV ou Excel)': 'Export data (CSV or Excel)',
    'Importar dados (CSV ou Excel)': 'Import data (CSV or Excel)',
    'Arquivo CSV ou Excel com os dados:': 'CSV or Excel file with the data:',
    'Já existe um campo chamado "{name}" neste PDF. Escolha outro nome.': (
        'This PDF already has a field named "{name}". Choose another name.'
    ),
    'Nenhum dos campos do arquivo de dados existe neste PDF: {names}': (
        'None of the fields in the data file exist in this PDF: {names}'
    ),
    'O arquivo FDF está malformado: {error}': 'The FDF file is malformed: {error}',
    'Um grupo de opções precisa de pelo menos duas opções.': 'An option group needs at least two options.',
    'Os valores das opções devem ser únicos.': 'Option values must be unique.',
    'selected_value deve ser um dos valores das opções.': (
        'The selected value must be one of the option values.'
    ),
    'Nenhum campo com nome válido encontrado no CSV.': 'No field with a valid name found in the CSV.',
    'Nenhum campo encontrado no arquivo FDF.': 'No field found in the FDF file.',
    'Adicionar anexo': 'Add attachment',
    'Remover anexo': 'Remove attachment',
    'Nenhum anexo chamado "{name}" foi encontrado neste PDF.': (
        'No attachment named "{name}" was found in this PDF.'
    ),
    'O anexo "{name}" continuaria no arquivo; nada foi salvo.': (
        'The attachment "{name}" would remain in the file; nothing was saved.'
    ),
    'O anexo "{name}" tentou gravar fora da pasta escolhida.': (
        'The attachment "{name}" tried to write outside the chosen folder.'
    ),
    'Criado com:': 'Created with:',
    'Aplicativo em que o documento foi criado': 'Application the document was created in',
    'Produtor do PDF:': 'PDF producer:',
    'Aplicativo que gerou o PDF': 'Application that produced the PDF',
    'não informada': 'not set',
    'Criado em: {created}. Modificado em: {modified}.': 'Created: {created}. Modified: {modified}.',
    'Idiomas do texto (marque todos os que aparecem no documento):': (
        'Text languages (check all that appear in the document):'
    ),
    'Só as escaneadas': 'Scanned pages only',
    'Todas (forçar OCR)': 'All (force OCR)',
    'DPI:': 'DPI:',
    'Resolução usada para ler a página. Texto pequeno pede mais DPI; 300 serve para a maioria.': (
        'Resolution used to read the page. Small text needs more DPI; 300 suits most documents.'
    ),
    'Corrigir páginas digitalizadas de lado': 'Fix pages scanned sideways',
    'Detecta páginas digitalizadas de lado ou de cabeça para baixo.': 'Detects pages scanned sideways or upside down.',
    'Marque pelo menos um idioma do texto.': 'Check at least one text language.',
    'Os instaladores do app já trazem o reconhecimento de texto. Rodando do código-fonte, ele precisa ser instalado à parte: os passos estão no README, em "Requisitos". Depois, reabra o app.': (
        'The app installers already include text recognition. When running from source, it has to be installed separately: the steps are in the README, under "Requisitos" (Requirements). Then reopen the app.'
    ),
    'O DPI do OCR precisa estar entre 72 e 1200.': 'OCR DPI must be between 72 and 1200.',
    'Escolha pelo menos um idioma de reconhecimento.': 'Choose at least one recognition language.',
    'Numeração de página': 'Page numbering',
    'Marcador desconhecido no texto: {names}. Use {{page}} (número da página) e {{pages}} (total de páginas).': (
        'Unknown placeholder in the text: {names}. Use {{page}} (page number) and {{pages}} (total pages).'
    ),
    'Remove o que o PDF/A proíbe (JavaScript, ações automáticas, anexos não permitidos), embute o perfil de cor sRGB e sincroniza os metadados. Depois verifica fontes, transparência e estrutura: se algo impedir a conformidade, nada é gravado e a lista do que falta é mostrada. PDFs protegidos por senha precisam passar antes por "Remover senha".': (
        'Removes what PDF/A forbids (JavaScript, automatic actions, attachments that are not allowed), embeds the sRGB color profile and syncs the metadata. Then checks fonts, transparency and structure: if anything prevents conformance, nothing is saved and the list of what is missing is shown. Password-protected PDFs must go through "Remove password" first.'
    ),
    'Nenhum problema encontrado nas verificações do app. Elas não cobrem a norma inteira: para arquivamento legal, confirme com o veraPDF.': (
        "No problems found by the app's checks. They do not cover the whole standard: for legal archiving, confirm with veraPDF."
    ),
    'O documento não pôde ser convertido, e nada foi gravado:': (
        'The document could not be converted, and nothing was saved:'
    ),
    'Ajustes feitos:': 'Changes made:',
    'Parte PDF/A inválida: {part} (use 1, 2 ou 3).': 'Invalid PDF/A part: {part} (use 1, 2 or 3).',
    'O nível {conformance} não existe no PDF/A-{part} (use {options}).': (
        'Level {conformance} does not exist in PDF/A-{part} (use {options}).'
    ),
    'Formulário XFA removido (proibido em PDF/A).': 'XFA form removed (forbidden in PDF/A).',
    'Falta o perfil de cor (/OutputIntent).': 'The color profile (/OutputIntent) is missing.',
    'Fontes não embutidas: {fonts}.': 'Fonts not embedded: {fonts}.',
    'O PDF/A-1 não permite transparência, e o documento usa (escolha a parte 2 ou 3).': (
        'PDF/A-1 does not allow transparency, and the document uses it (choose part 2 or 3).'
    ),
    'O PDF/A-1 não permite camadas, e o documento tem (escolha a parte 2 ou 3).': (
        'PDF/A-1 does not allow layers, and the document has them (choose part 2 or 3).'
    ),
    'O nível {conformance} exige que o texto tenha mapeamento Unicode, e estas fontes não têm: {fonts}.': (
        'Level {conformance} requires text with a Unicode mapping, and these fonts lack it: {fonts}.'
    ),
    'O nível A exige um documento tagueado (com estrutura de acessibilidade); use o nível B.': (
        'Level A requires a tagged document (with accessibility structure); use level B.'
    ),
    'O nível A exige o idioma do documento (/Lang); defina-o em Acessibilidade.': (
        'Level A requires the document language (/Lang); set it in Accessibility.'
    ),
    'O título no dicionário Info e no XMP não são iguais.': (
        'The title in the Info dictionary and in the XMP differ.'
    ),
    'O autor no dicionário Info e no XMP não são iguais.': (
        'The author in the Info dictionary and in the XMP differ.'
    ),
    'Os metadados XMP não declaram conformidade PDF/A.': (
        'The XMP metadata does not declare PDF/A conformance.'
    ),
    'O arquivo declara PDF/A-{declared}, não PDF/A-{part}.': (
        'The file declares PDF/A-{declared}, not PDF/A-{part}.'
    ),
    'O arquivo declara o nível {declared}, não o nível {conformance}.': (
        'The file declares level {declared}, not level {conformance}.'
    ),
    'Os metadados XMP estão malformados.': 'The XMP metadata is malformed.',
    'O PDF está protegido por senha — PDF/A não permite criptografia.': (
        'The PDF is password-protected — PDF/A does not allow encryption.'
    ),
    'O documento contém JavaScript.': 'The document contains JavaScript.',
    'O documento contém anexos, proibidos em PDF/A-1.': (
        'The document contains attachments, forbidden in PDF/A-1.'
    ),
    'O documento contém anexos que não são PDF/A, proibidos em PDF/A-2.': (
        'The document contains non-PDF/A attachments, forbidden in PDF/A-2.'
    ),
    'O documento tem ações automáticas (/AA).': 'The document has automatic actions (/AA).',
    'O documento contém um formulário XFA.': 'The document contains an XFA form.',
    'O formulário pede ao leitor que gere as aparências dos campos (/NeedAppearances).': (
        'The form asks the reader to generate the field appearances (/NeedAppearances).'
    ),
    'O documento contém ações proibidas em PDF/A (JavaScript, abrir programas, multimídia...).': (
        'The document contains actions forbidden in PDF/A (JavaScript, launching programs, multimedia...).'
    ),
    'Uma página tem ações automáticas (/AA).': 'A page has automatic actions (/AA).',
    'O documento usa compressão LZW.': 'The document uses LZW compression.',
    'O documento contém anotações multimídia ou 3D.': 'The document contains multimedia or 3D annotations.',
    'Há anotações escondidas ou que não saem na impressão.': (
        'There are hidden annotations or annotations that do not print.'
    ),
    'Preparando o documento': 'Preparing the document',
    'Verificando o documento': 'Checking the document',
    'O leitor mostra o nome do arquivo em vez do título (falta /DisplayDocTitle).': (
        'Readers show the file name instead of the title (/DisplayDocTitle is missing).'
    ),
    'Informe um idioma (ex.: pt-BR).': 'Provide a language (e.g.: en-US).',
    'Informe um título para o documento.': 'Provide a title for the document.',
    'A nova ordem precisa incluir todas as {total} páginas; faltam: {pages}. Para tirar páginas, use Remover.': (
        'The new order must include all {total} pages; missing: {pages}. To drop pages, use Remove.'
    ),
    'O ângulo de rotação precisa ser múltiplo de 90 graus.': (
        'The rotation angle must be a multiple of 90 degrees.'
    ),
    'A remoção resultaria em um PDF sem nenhuma página.': 'Removing them would leave a PDF with no pages.',
    'As margens de corte excedem o tamanho da página {page}.': (
        'The crop margins exceed the size of page {page}.'
    ),
    'A largura e a altura precisam ser maiores que zero.': 'Width and height must be greater than zero.',
    'Informe ao menos um arquivo PDF para mesclar.': 'Provide at least one PDF file to merge.',
    "Para intercalar, informe exatamente dois arquivos: o das frentes e o dos versos.": "To interleave, provide exactly two files: the fronts and the backs.",
    "Informe as páginas de cada arquivo (ou nenhuma).": "Provide the pages of each file (or none).",
    "Nenhuma página escolhida.": "No page chosen.",
    'O PDF não tem marcadores de nível superior para dividir.': (
        'The PDF has no top-level bookmarks to split by.'
    ),
    'Não foi possível localizar a página de nenhum marcador.': 'Could not find the page of any bookmark.',
    'Senha incorreta.': 'Wrong password.',
    'Este PDF está protegido por senha. Abra-o no visualizador (que pede a senha) para usá-lo nas ferramentas de leitura, ou use "Remover senha" em Proteger para trabalhar sobre uma cópia sem proteção.': (
        'This PDF is password-protected. Open it in the viewer (which asks for the password) to use it in the reading tools, or use "Remove password" in Protect to work on an unprotected copy.'
    ),
    'Este PDF abre sem senha, mas o autor restringiu alterações com uma senha de permissões. Para alterá-lo, use "Remover senha" em Proteger informando a senha de permissões — o resultado sai sem proteção, e você pode protegê-lo de novo depois.': (
        'This PDF opens without a password, but the author restricted changes with a permissions password. To change it, use "Remove password" in Protect with the permissions password — the result has no protection, and you can protect it again afterwards.'
    ),
    'Este PDF está protegido por senha. Alterá-lo aqui geraria uma cópia sem a proteção; use "Remover senha" em Proteger e, se quiser, proteja o resultado de novo depois.': (
        'This PDF is password-protected. Changing it here would produce an unprotected copy; use "Remove password" in Protect and, if you want, protect the result again afterwards.'
    ),
    'O autor deste PDF não permite copiar o conteúdo dele (texto e imagens). Para extrair, use "Remover senha" em Proteger informando a senha de permissões.': (
        'The author of this PDF does not allow copying its content (text and images). To extract, use "Remove password" in Protect with the permissions password.'
    ),
    'Não foi possível carregar o certificado .pfx (senha incorreta ou arquivo inválido).': (
        'Could not load the .pfx certificate (wrong password or invalid file).'
    ),
    'Informe um certificado .pfx ou os dados para gerar um certificado de teste.': (
        'Provide a .pfx certificate or the details to generate a test certificate.'
    ),
    'Expressão regular inválida: {error}': 'Invalid regular expression: {error}',
    'A página {page} ainda tem texto depois da redação. O arquivo não foi salvo.': (
        'Page {page} still has text after redaction. The file was not saved.'
    ),
    'A página {page} tem conteúdo inesperado depois da redação. O arquivo não foi salvo.': (
        'Page {page} has unexpected content after redaction. The file was not saved.'
    ),
    'Na página {page}, uma área marcada ainda mostra conteúdo depois da redação. O arquivo não foi salvo.': (
        'On page {page}, a marked area still shows content after redaction. The file was not saved.'
    ),
    'A sanitização não conseguiu remover: {problems}. O arquivo não foi salvo.': (
        'Sanitization could not remove: {problems}. The file was not saved.'
    ),
    # Etapa 5: experiência de uso
    'Salvar como...': 'Save as...',
    'Abrir recente': 'Open recent',
    'Limpar lista': 'Clear list',
    'Nenhum arquivo recente': 'No recent files',
    'Desfazer': 'Undo',
    'Refazer': 'Redo',
    'Desfazer {operation}': 'Undo {operation}',
    'Refazer {operation}': 'Redo {operation}',
    'Documento salvo.': 'Document saved.',
    'Alterações não salvas': 'Unsaved changes',
    '"{name}" tem alterações que não foram salvas. Salvar antes?': (
        '"{name}" has unsaved changes. Save first?'
    ),
    'Não foi possível salvar o arquivo: {error}': 'Could not save the file: {error}',
    'Aplicar o resultado ao documento aberto (Ctrl+Z desfaz)': (
        'Apply the result to the open document (Ctrl+Z undoes)'
    ),
    'No documento aberto (Ctrl+Z desfaz)': 'In the open document (Ctrl+Z undoes)',
    'O resultado é aplicado ao documento aberto. Use Arquivo > Salvar para gravar.': (
        'The result is applied to the open document. Use File > Save to write it.'
    ),
    'Arraste no visualizador a área que deve ficar; as margens são calculadas a partir dela.': (
        'Drag over the viewer the area to keep; the margins are computed from it.'
    ),
    'Clique numa imagem para escolhê-la.': 'Click an image to choose it.',
    'Arraste no visualizador para marcar a área do link, ou ajuste os valores abaixo.': (
        'Drag over the viewer to mark the link area, or adjust the values below.'
    ),
    'Clique num link da lista, ou arraste sobre ele no visualizador, para escolher o link a remover.': (
        'Click a link in the list, or drag over it in the viewer, to choose the link to remove.'
    ),
    'Arraste no visualizador para marcar onde o campo fica, ou ajuste os valores (pontos PDF).': (
        'Drag over the viewer to mark where the field goes, or adjust the values (PDF points).'
    ),
    'Selecione uma opção na tabela e arraste no visualizador para marcar onde ela fica.': (
        'Select an option in the table and drag over the viewer to mark where it goes.'
    ),
    'Usar seleção': 'Use selection',
    'Preenche com as páginas selecionadas nas miniaturas (Ctrl ou Shift + clique).': (
        'Fills in the pages selected in the thumbnails (Ctrl or Shift + click).'
    ),
    'Área marcada no visualizador': 'Area marked in the viewer',
    'Para escolher o lugar exato do selo, arraste no visualizador.': (
        'To choose the exact place of the stamp, drag over the viewer.'
    ),
    'Arraste no visualizador para marcar a área do selo.': 'Drag over the viewer to mark the stamp area.',
    'A área do selo é pequena demais: marque pelo menos 20 x 10 pontos.': (
        'The stamp area is too small: mark at least 20 x 10 points.'
    ),
    'Ir para a página... (Ctrl+G)': 'Go to page... (Ctrl+G)',
    'Ir para a página': 'Go to page',
    'Ir para a página {page}': 'Go to page {page}',
    'Escrever para {address}': 'Write to {address}',
    'Página (1 a {total}):': 'Page (1 to {total}):',
    'Ajustar à página (Ctrl+0)': 'Fit page (Ctrl+0)',
    'Girar a visualização (o arquivo não muda)': 'Rotate the view (the file does not change)',
    'Painel lateral (miniaturas, marcadores, anexos)': 'Side panel (thumbnails, bookmarks, attachments)',
    'Miniaturas (Ctrl ou Shift + clique seleciona várias)': (
        'Thumbnails (Ctrl or Shift + click selects several)'
    ),
    'Duplo clique para salvar o anexo': 'Double-click to save the attachment',
    'Salvar anexo': 'Save attachment',
    'Não foi possível salvar o anexo: {error}': 'Could not save the attachment: {error}',
    '(sem título)': '(untitled)',
    'Página {page}': 'Page {page}',
    'Verificar as assinaturas': 'Verify the signatures',
    '1 assinatura digital. Alterar o PDF a invalida.': '1 digital signature. Changing the PDF invalidates it.',
    '{count} assinaturas digitais. Alterar o PDF as invalida.': '{count} digital signatures. Changing the PDF invalidates them.',
    'Este PDF tem campos de formulário. Clique em um campo para preencher.': 'This PDF has form fields. Click a field to fill it in.',
    'Este PDF tem camadas: partes que podem ser mostradas ou ocultadas.': 'This PDF has layers: parts that can be shown or hidden.',
    'Protegido por senha.': 'Password-protected.',
    'Protegido: o autor bloqueou alterações ou cópia.': 'Protected: the author blocked changes or copying.',
    'Ver': 'View',
    'Fechar aviso': 'Dismiss notice',
    'Ocorreu um erro inesperado.': 'An unexpected error occurred.',
    'Não há espaço livre no disco para gravar o arquivo.': 'There is no free disk space to write the file.',
    'Memória insuficiente para concluir a operação. Feche outros programas ou use um arquivo menor.': (
        'Not enough memory to finish the operation. Close other programs or use a smaller file.'
    ),
    'O PDF parece estar corrompido ou não é um PDF válido.': (
        'The PDF seems to be corrupted or is not a valid PDF.'
    ),
    'O arquivo não foi encontrado: {name}': 'The file was not found: {name}',
    'Sem permissão para usar o arquivo {name}. Se ele estiver aberto em outro programa, feche-o e tente de novo.': (
        'No permission to use the file {name}. If it is open in another program, close it and try again.'
    ),
    'Clique numa camada para escolhê-la.': 'Click a layer to choose it.',
    'Da primeira à última página selecionada nas miniaturas.': 'From the first to the last page selected in the thumbnails.',
    'Página atual': 'Current page',
    'Usar a página que está no visualizador': 'Use the page shown in the viewer',
    # Etapa 6: novas funcionalidades
    'Imprimir...': 'Print...',
    'Imprimir': 'Print',
    'Imprimindo páginas': 'Printing pages',
    'Não foi possível imprimir: {error}': 'Could not print: {error}',
    'Não foi possível iniciar a impressão.': 'Could not start printing.',
    'Nenhuma página escolhida para imprimir.': 'No pages chosen to print.',
    'O autor deste PDF não permite imprimi-lo. Para imprimir, use "Remover senha" em Proteger informando a senha de permissões.': (
        'The author of this PDF does not allow printing it. To print, use "Remove password" in Protect with the permissions password.'
    ),
    'Organizar páginas': 'Organize pages',
    'Reordene arrastando, gire, duplique, exclua, insira páginas em branco ou extraia páginas.': (
        'Reorder by dragging, rotate, duplicate, delete, insert blank pages or extract pages.'
    ),
    'Girar à esquerda': 'Rotate left',
    'Girar à direita': 'Rotate right',
    'Mover para trás': 'Move back',
    'Mover para a frente': 'Move forward',
    'Duplicar': 'Duplicate',
    'Insere uma página em branco depois da última selecionada, ou no fim.': (
        'Inserts a blank page after the last selected one, or at the end.'
    ),
    'Extrair...': 'Extract...',
    'Salva as páginas selecionadas em outro arquivo.': 'Saves the selected pages to another file.',
    'Página em branco': 'Blank page',
    'edição na grade': 'grid edit',
    'anotação': 'annotation',
    'área de redação': 'redaction area',
    'Extrair páginas': 'Extract pages',
    'Preencher formulário': 'Fill form',
    'Preencher e assinar': 'Fill & sign',
    'Coloque texto, data, assinatura desenhada ou em imagem e iniciais na página, sem certificado.': 'Place text, a date, a drawn or image signature and initials on the page, without a certificate.',
    'Assinatura': 'Signature',
    'Iniciais': 'Initials',
    'Limpar': 'Clear',
    'Desenhe com o mouse ou a caneta:': 'Draw with the mouse or pen:',
    'Texto a colocar na página': 'Text to place on the page',
    'Desenhar...': 'Draw...',
    'Imagem...': 'Image...',
    'Usa uma imagem PNG ou JPEG (de preferência com fundo transparente).': 'Uses a PNG or JPEG image (preferably with a transparent background).',
    'Arraste no visualizador para marcar onde colocar; cada área recebe o item escolhido acima.': 'Drag on the viewer to mark where to place it; each area gets the item chosen above.',
    'O que é colocado aqui entra no conteúdo da página. Não é assinatura digital: para isso, use a aba Assinatura digital.': 'What you place here becomes part of the page content. It is not a digital signature: for that, use the Digital signature tab.',
    'O que colocar:': 'What to place:',
    'Nada guardado ainda: desenhe ou escolha uma imagem.': 'Nothing saved yet: draw or choose an image.',
    'Não foi possível ler a imagem.': 'Could not read the image.',
    'Imagens': 'Images',
    'Digite o texto antes de marcar a área.': 'Type the text before marking the area.',
    'Desenhe ou escolha a imagem antes de marcar a área.': 'Draw or choose the image before marking the area.',
    'Marque pelo menos uma área com texto, data, assinatura ou iniciais.': 'Mark at least one area with text, a date, a signature or initials.',
    'Processar em lote': 'Batch processing',
    "Aplique a mesma operação (comprimir, OCR, marca d'água, numerar, proteger, PDF/A) a todos os PDFs de uma pasta.": 'Apply the same operation (compress, OCR, watermark, number, protect, PDF/A) to every PDF in a folder.',
    'Começar a numeração em:': 'Start numbering at:',
    'Converter para PDF/A-2b': 'Convert to PDF/A-2b',
    'Digite a senha.': 'Type the password.',
    'Escolha a pasta com os PDFs.': 'Choose the folder with the PDFs.',
    'Falhou: {error}': 'Failed: {error}',
    'Idioma do texto:': 'Text language:',
    'Nenhum PDF na pasta escolhida.': 'No PDF in the chosen folder.',
    'Nenhum PDF para processar.': 'No PDF to process.',
    'Numerar páginas': 'Number pages',
    'O relatório não foi salvo: {error}': 'The report was not saved: {error}',
    'Pasta com os PDFs:': 'Folder with the PDFs:',
    "Texto da marca d'água:": 'Watermark text:',
    'Processando os arquivos': 'Processing the files',
    'Processar': 'Process',
    'Relatório: {path}': 'Report: {path}',
    'Resultado': 'Result',
    'Salvo como {name}': 'Saved as {name}',
    'Sem opções: cada arquivo vira PDF/A-2b.': 'No options: each file becomes PDF/A-2b.',
    'Sem pasta de saída, os arquivos vão para "processados", dentro da pasta de entrada.': 'Without an output folder, the files go to "processados", inside the input folder.',
    'Senha para abrir:': 'Password to open:',
    'Falharam: {count}.': 'Failed: {count}.',
    'Limpar escaneados': 'Clean up scans',
    'Remova páginas em branco, endireite páginas tortas e corte as margens brancas de um escaneado.': 'Remove blank pages, straighten skewed pages and crop the white margins of a scan.',
    'Remover páginas em branco': 'Remove blank pages',
    'Endireitar páginas tortas (até 5°)': 'Straighten skewed pages (up to 5°)',
    'Cortar as margens brancas': 'Crop the white margins',
    'Limpar páginas': 'Clean up pages',
    'Feito para páginas escaneadas: a análise olha a imagem da página, não o texto. Confira o resultado; Ctrl+Z desfaz.': 'Made for scanned pages: the analysis looks at the page image, not the text. Check the result; Ctrl+Z undoes it.',
    'Escolha pelo menos uma limpeza.': 'Choose at least one cleanup.',
    'Páginas em branco removidas: {pages}.': 'Blank pages removed: {pages}.',
    'Páginas endireitadas: {pages}.': 'Pages straightened: {pages}.',
    'Margens cortadas nas páginas: {pages}.': 'Margins cropped on pages: {pages}.',
    'Nenhuma página precisou de limpeza.': 'No page needed cleaning up.',
    'Os números são os das páginas antes da limpeza.': 'The numbers are those of the pages before the cleanup.',
    'Analisando as páginas': 'Analyzing the pages',
    'Todas as páginas parecem em branco; nada foi alterado.': 'Every page looks blank; nothing was changed.',
    'PDF para Word (.docx)': 'PDF to Word (.docx)',
    'PDF para Excel (.xlsx)': 'PDF to Excel (.xlsx)',
    'PDF para texto com layout (.txt)': 'PDF to text with layout (.txt)',
    'HTML, Markdown ou texto para PDF': 'HTML, Markdown or text to PDF',
    'HTML, Markdown ou texto': 'HTML, Markdown or text',
    'Arquivo HTML, Markdown ou texto de entrada:': 'Input HTML, Markdown or text file:',
    'Vai só o texto das páginas: imagens e formatação ficam de fora, e página escaneada precisa de OCR antes.': 'Only the text of the pages goes: images and formatting are left out, and a scanned page needs OCR first.',
    'Títulos, listas, tabelas, links e imagens locais são mantidos; estilos CSS avançados, scripts e imagens da internet, não.': 'Headings, lists, tables, links and local images are kept; advanced CSS styles, scripts and images from the internet are not.',
    'Arquivo gerado: {path}': 'File created: {path}',
    'Páginas sem texto (escaneadas? faça o OCR antes): {pages}': 'Pages without text (scanned? run OCR first): {pages}',
    'Comparar lado a lado': 'Compare side by side',
    'Mostra as duas versões lado a lado, com as diferenças de texto destacadas e a rolagem sincronizada. O texto comparado é o do documento inteiro: o que só passou para outra página não conta como diferença.': 'Shows both versions side by side, with the text differences highlighted and synchronized scrolling. The text of the whole document is compared: text that only moved to another page does not count as a difference.',
    'A: documento aberto': 'A: open document',
    'B: comparar com': 'B: compare with',
    'Abra o documento A e escolha o PDF B a comparar.': 'Open document A and choose the PDF B to compare.',
    'Lendo o texto': 'Reading the text',
    'Comparando o texto': 'Comparing the text',
    'removido “{a}”': 'removed “{a}”',
    'incluído “{b}”': 'added “{b}”',
    '“{a}” → “{b}”': '“{a}” → “{b}”',
    'Pág. {pages}: {change}': 'P. {pages}: {change}',
    'Comparação lado a lado — {a} × {b}': 'Side-by-side comparison — {a} × {b}',
    'Diferença anterior (Shift+F3)': 'Previous difference (Shift+F3)',
    'Próxima diferença (F3)': 'Next difference (F3)',
    'Removido de A': 'Removed from A',
    'Incluído em B': 'Added in B',
    'Alterado': 'Changed',
    'Nenhuma diferença no texto.': 'No differences in the text.',
    'Páginas de {side} sem texto (escaneadas? faça o OCR antes): {pages}': 'Pages of {side} without text (scanned? run OCR first): {pages}',
    'Imagens, formatação e cabeçalhos/rodapés repetidos em todas as páginas não entram na comparação; para eles, use "Comparar visualmente".': 'Images, formatting and headers/footers repeated on every page are not compared; for them, use "Compare visually".',
    # A11 — comentários existentes e XFDF
    "Autor": "Author",
    "Importar comentários (XFDF)...": "Import comments (XFDF)...",
    "Importar comentários (XFDF)": "Import comments (XFDF)",
    "Exportar comentários": "Export comments",
    "Editar comentário": "Edit comment",
    "Nota": "Note",
    "Ondulado": "Squiggly",
    "Texto livre": "Free text",
    "Retângulo": "Rectangle",
    "Círculo": "Circle",
    "Linha": "Line",
    "Polígono": "Polygon",
    "Polilinha": "Polyline",
    "Inserção": "Caret",
    "Anexo": "Attachment",
    "A anotação escolhida não existe mais no documento.": "The chosen annotation no longer exists in the document.",
    "O arquivo XFDF tem uma declaração DOCTYPE, que não é aceita.": "The XFDF file has a DOCTYPE declaration, which is not accepted.",
    "O arquivo escolhido não é um XFDF válido.": "The chosen file is not a valid XFDF.",
    # A12 — propriedades do documento
    "Propriedades do documento...": "Document properties...",
    "Propriedades do documento": "Document properties",
    "Não foi possível ler as propriedades: {error}": "Could not read the properties: {error}",
    "Imprimir:": "Print:",
    "Imprimir em alta qualidade:": "Print in high quality:",
    "Alterar o documento:": "Change the document:",
    "Copiar texto e imagens:": "Copy text and images:",
    "Extrair texto para acessibilidade:": "Extract text for accessibility:",
    "Comentar:": "Comment:",
    "Preencher formulários:": "Fill in forms:",
    "Montar o documento (inserir, girar, excluir páginas):": "Assemble the document (insert, rotate, delete pages):",
    "A3": "A3",
    "A5": "A5",
    "{count} bytes": "{count} bytes",
    "retrato": "portrait",
    "paisagem": "landscape",
    "Sim": "Yes",
    "Não": "No",
    "Geral": "General",
    "Segurança": "Security",
    "Fontes": "Fonts",
    "(com as alterações ainda não salvas)": "(with the changes not saved yet)",
    "XFA (formulário dinâmico, que o app não preenche)": "XFA (dynamic form, which the app does not fill in)",
    "Arquivo:": "File:",
    "Versão do PDF:": "PDF version:",
    "Criado em:": "Created on:",
    "Modificado em:": "Modified on:",
    "Visualização rápida na web:": "Fast web view:",
    "Marcado para acessibilidade:": "Tagged for accessibility:",
    "PDF/A:": "PDF/A:",
    "Não declara": "Not declared",
    "Formulário:": "Form:",
    "Não tem": "None",
    "Proteção:": "Protection:",
    "Sem proteção: qualquer pessoa abre, imprime, copia e altera.": "No protection: anyone can open, print, copy and change it.",
    "Criptografia {method}": "{method} encryption",
    "Permitido": "Allowed",
    "Não permitido": "Not allowed",
    "Fonte": "Font",
    "Tipo": "Type",
    "Embutida": "Embedded",
    "Codificação": "Encoding",
    "Sim (subconjunto)": "Yes (subset)",
    "Não (fonte padrão)": "No (standard font)",
    "(sem nome)": "(no name)",
    "Nenhuma fonte: o documento não tem texto (escaneado ou só imagens).": "No fonts: the document has no text (scanned or images only).",
    "1 não embutida: em outro computador, o texto pode aparecer com outra fonte.": "1 not embedded: on another computer, the text may show in a different font.",
    "{count} não embutidas: em outro computador, o texto pode aparecer com outra fonte.": "{count} not embedded: on another computer, the text may show in a different font.",
    "Tamanho": "Size",
    "Personalizada": "Custom",
    # A14 — tema
    "Exibir": "View",
    "Tema": "Theme",
    "Escuro": "Dark",
    "Claro": "Light",
    "Seguir o sistema": "Follow the system",
    "Animações da interface": "Interface animations",
    # A15 — apresentação e página dupla
    "Apresentação": "Presentation",
    "Página dupla": "Two pages",
    "Livro (capa sozinha)": "Book (cover on its own)",
    # A17 — verificação de atualização
    "Verificar atualizações...": "Check for updates...",
    "Verificar atualizações ao iniciar": "Check for updates at startup",
    "Mostrar no menu de aplicativos": "Show in the applications menu",
    "Menu de aplicativos": "Applications menu",
    "Mostrar o OpenFolio no menu de aplicativos e na lista de programas para abrir PDF?\n\n"
    "Dá para mudar depois em Ajuda > Mostrar no menu de aplicativos.":
        "Show OpenFolio in the applications menu and in the list of programs to open PDFs?\n\n"
        "You can change this later in Help > Show in the applications menu.",
    "Não foi possível mudar o menu de aplicativos: {error}": "Could not change the applications menu: {error}",
    "Verificar atualizações": "Check for updates",
    "Não foi possível verificar atualizações. Confira a conexão e tente de novo.": "Could not check for updates. Check your connection and try again.",
    "Atualização disponível": "Update available",
    # A18 — paleta de comandos e atalhos
    "Atalhos de teclado...": "Keyboard shortcuts...",
    "Paleta de comandos...": "Command palette...",
    "Ferramentas": "Tools",
    "Paleta de comandos": "Command palette",
    "Atalhos de teclado": "Keyboard shortcuts",
    "Comando": "Command",
    "Atalho": "Shortcut",
    "Restaurar padrões": "Restore defaults",
    "O atalho {keys} já é usado pelo visualizador.": "The shortcut {keys} is already used by the viewer.",
    "O atalho {keys} já é usado por \"{command}\".": "The shortcut {keys} is already used by \"{command}\".",
    # M48 — Sobre
    "Suite completa e open source de manipulação de PDF, 100% local, sem paywall.": (
        "Complete open source PDF suite, 100% local, no paywall."
    ),
    "O que mudou em cada atualização": "What changed in each update",
    # Atualizações sem número de versão, com consentimento
    "O OpenFolio PDF Suite já está atualizado.": "OpenFolio PDF Suite is up to date.",
    "(A atualização não traz descrição.)": "(The update has no description.)",
    "Se você aceitar, o app baixa a atualização, confere o arquivo e fecha para instalá-la; ao terminar, ele abre de novo. Seus documentos não são tocados.": (
        "If you accept, the app downloads the update, checks the file and closes to install it; when it is done, "
        "it opens again. Your documents are not touched."
    ),
    "Baixar e instalar": "Download and install",
    "Se você aceitar, a página da atualização abre no navegador para você baixá-la.": (
        "If you accept, the update page opens in your browser for you to download it."
    ),
    "Abrir a página": "Open the page",
    "Agora não": "Not now",
    "Baixando a atualização...": "Downloading the update...",
    "Atualização": "Update",
    "Não foi possível baixar a atualização: o arquivo não chegou inteiro ou não confere com o publicado. Nada foi instalado; tente de novo mais tarde.": (
        "Could not download the update: the file did not arrive complete or does not match the published one. "
        "Nothing was installed; try again later."
    ),
    "A atualização foi baixada e conferida. O app vai fechar para instalá-la e abre de novo quando terminar.": (
        "The update was downloaded and checked. The app will close to install it and open again when it is done."
    ),
    "(sem arquivo de log)": "(no log file)",
    "Abrir pasta": "Open folder",
    "Componente": "Component",
    "Versão": "Version",
    "Licença": "License",
    "Arquivo de log (anexe-o ao relatar um problema):": "Log file (attach it when reporting a problem):",
    "Componentes de terceiros:": "Third-party components:",
    "Os textos das licenças dos pacotes Python vão junto com o app, nos metadados de cada um.": (
        "The license texts of the Python packages ship with the app, in each package's metadata."
    ),
    "O código-fonte das bibliotecas GPL e LGPL está em cada atualização, na página de releases.": (
        "The source code of the GPL and LGPL libraries is in each update, on the releases page."
    ),
    "Licenças das bibliotecas": "Library licenses",
    # Sem programas externos (LibreOffice, Ghostscript, veraPDF)
    "A conversão leva o texto, os títulos, as listas e as tabelas de arquivos .docx, .xlsx e .pptx, mas não a "
    "formatação visual exata, as imagens nem os cabeçalhos e rodapés.": (
        "The conversion keeps the text, headings, lists and tables of .docx, .xlsx and .pptx files, but not the "
        "exact visual formatting, images, headers or footers."
    ),
    "Verifica os requisitos de PDF/A que o app cobre (declaração, perfil de cor, fontes embutidas, transparência, "
    "ações e anexos proibidos, metadados) — não é a validação ISO 19005 completa.": (
        "Checks the PDF/A requirements the app covers (declaration, color profile, embedded fonts, transparency, "
        "forbidden actions and attachments, metadata) — not the full ISO 19005 validation."
    ),
    # -- janela com abas de documento ----------------------------------------------------
    "Início": "Home",
    "Todas as ferramentas": "All tools",
    "Sem documento": "No document",
    "Fechar documento": "Close document",
    "Miniaturas das páginas": "Page thumbnails",
    "Revisar e comentar": "Review and comment",
    "Automatizar": "Automate",
    "Recentes": "Recent",
    "Salvar (Ctrl+S)": "Save (Ctrl+S)",
    "Imprimir... (Ctrl+P)": "Print... (Ctrl+P)",
}
