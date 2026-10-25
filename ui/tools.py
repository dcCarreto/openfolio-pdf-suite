"""O catálogo das ferramentas: a aba Ferramentas, a coluna de ferramentas de cada documento, o
menu e a paleta de comandos saem daqui.

Cada ferramenta é (ícone, título, subtítulo, módulo, classe). Os textos são traduzidos ao montar
a tela; o módulo só é importado quando a ferramenta é aberta pela primeira vez, o que tira da
abertura do app o custo de bibliotecas pesadas como pyhanko (assinatura) e pytesseract (OCR).
"""

SECTIONS = [
    ("build_create_icon", "Criar PDF", "Crie um novo PDF em branco, com uma ou mais páginas.",
     "ui.pages.create_page", "CreatePage"),
    ("build_merge_icon", "Mesclar", "Combine vários PDFs em um único arquivo, na ordem que você escolher.",
     "ui.pages.merge_page", "MergePage"),
    ("build_split_icon", "Dividir", "Separe um PDF em vários arquivos menores.",
     "ui.pages.split_page", "SplitPage"),
    ("build_pages_icon", "Páginas", "Rotacione, reordene ou remova páginas de um PDF.",
     "ui.pages.pages_page", "PagesPage"),
    ("build_organize_icon", "Organizar páginas",
     "Reordene arrastando, gire, duplique, exclua, insira páginas em branco ou extraia páginas.",
     "ui.pages.organize_page", "OrganizePage"),
    ("build_compress_icon", "Comprimir", "Reduza o tamanho de um arquivo PDF.",
     "ui.pages.compress_page", "CompressPage"),
    ("build_convert_icon", "Converter",
     "Converta entre PDF e imagens, Word, Excel, PowerPoint, texto, HTML, Markdown e XML.",
     "ui.pages.convert_page", "ConvertPage"),
    ("build_watermark_icon", "Marca d'água", "Adicione um texto de marca d'água sobre as páginas de um PDF.",
     "ui.pages.watermark_page", "WatermarkPage"),
    ("build_protect_icon", "Proteger", "Proteja um PDF com senha, ou remova a senha de um PDF protegido.",
     "ui.pages.protect_page", "ProtectPage"),
    ("build_metadata_icon", "Metadados", "Edite título, autor, assunto e palavras-chave de um PDF.",
     "ui.pages.metadata_page", "MetadataPage"),
    ("build_page_numbers_icon", "Numeração", "Adicione números de página no rodapé de um PDF, ou numeração Bates.",
     "ui.pages.page_numbers_page", "PageNumbersPage"),
    ("build_pdfa_icon", "PDF/A",
     "Converta um PDF para uma aproximação de PDF/A (arquivamento) ou valide um existente.",
     "ui.pages.pdfa_page", "PDFAPage"),
    ("build_extract_text_icon", "Extrair texto", "Extraia todo o texto de um PDF para um arquivo .txt.",
     "ui.pages.extract_text_page", "ExtractTextPage"),
    ("build_extract_images_icon", "Extrair imagens", "Extraia as imagens embutidas nas páginas de um PDF.",
     "ui.pages.extract_images_page", "ExtractImagesPage"),
    ("build_crop_icon", "Cortar/Redimensionar", "Corte margens ou redimensione as páginas de um PDF.",
     "ui.pages.crop_page", "CropPage"),
    ("build_edit_icon", "Editar",
     "Substitua imagens embutidas, cubra e reescreva texto, ou adicione/liste/remova links de um PDF.",
     "ui.pages.edit_page", "EditPage"),
    ("build_bookmarks_icon", "Marcadores", "Monte um sumário de navegação (marcadores) para um PDF.",
     "ui.pages.bookmarks_page", "BookmarksPage"),
    ("build_layers_icon", "Camadas",
     "Liste as camadas (Optional Content Groups) de um PDF e alterne a visibilidade padrão de cada uma.",
     "ui.pages.layers_page", "LayersPage"),
    ("build_attachments_icon", "Anexos", "Liste, adicione, remova ou extraia os anexos embutidos de um PDF.",
     "ui.pages.attachments_page", "AttachmentsPage"),
    ("build_form_fields_icon", "Campos de formulário",
     "Adicione campos de formulário e grupos de opções, liste os existentes, exporte/importe dados "
     "preenchidos ou achate o formulário.",
     "ui.pages.form_fields_page", "FormFieldsPage"),
    ("build_annotations_icon", "Anotações",
     "Realce, sublinhe, risque, adicione notas, desenhe ou carimbe sobre um PDF; edite, remova e "
     "troque comentários por XFDF.",
     "ui.pages.annotations_page", "AnnotationsPage"),
    ("build_measure_icon", "Medição",
     "Meça a distância entre dois pontos de um PDF, arrastando no visualizador central.",
     "ui.pages.measure_page", "MeasurePage"),
    ("build_ocr_icon", "OCR", "Reconheça o texto de PDFs escaneados e gere um PDF pesquisável.",
     "ui.pages.ocr_page", "OCRPage"),
    ("build_scan_cleanup_icon", "Limpar escaneados",
     "Remova páginas em branco, endireite páginas tortas e corte as margens brancas de um escaneado.",
     "ui.pages.scan_cleanup_page", "ScanCleanupPage"),
    ("build_redaction_icon", "Redigir/Sanitizar",
     "Apague definitivamente áreas de um PDF ou remova metadados, JavaScript e anexos.",
     "ui.pages.redaction_page", "RedactionPage"),
    ("build_fill_sign_icon", "Preencher e assinar",
     "Coloque texto, data, assinatura desenhada ou em imagem e iniciais na página, sem certificado.",
     "ui.pages.fill_sign_page", "FillSignPage"),
    ("build_signature_icon", "Assinatura digital",
     "Assine um PDF com selo visível e assinatura criptográfica, ou verifique uma assinatura existente.",
     "ui.pages.signature_page", "SignaturePage"),
    ("build_accessibility_icon", "Acessibilidade",
     "Verifique um subconjunto de PDF/UA e corrija idioma/título do documento.",
     "ui.pages.accessibility_page", "AccessibilityPage"),
    ("build_compare_icon", "Comparar",
     "Compare duas versões de um PDF: lado a lado com as diferenças destacadas, diff de texto por página ou diff visual.",
     "ui.pages.compare_page", "ComparePage"),
    ("build_batch_icon", "Processar em lote",
     "Aplique a mesma operação (comprimir, OCR, marca d'água, numerar, proteger, PDF/A) a todos os PDFs de uma pasta.",
     "ui.pages.batch_page", "BatchPage"),
]  # fmt: skip

ROW_OF = {class_name: row for row, (*_rest, class_name) in enumerate(SECTIONS)}

# A aba Ferramentas agrupa as ferramentas pelo que o usuário quer fazer.
CATEGORIES = [
    ("Criar e editar", ["CreatePage", "EditPage", "OrganizePage", "PagesPage", "MergePage", "SplitPage", "CropPage"]),
    ("Revisar e comentar", ["AnnotationsPage", "MeasurePage", "ComparePage", "FillSignPage"]),
    ("Formulários e assinatura", ["FormFieldsPage", "SignaturePage"]),
    ("Proteger", ["ProtectPage", "RedactionPage", "AccessibilityPage"]),
    ("Converter e otimizar",
     ["ConvertPage", "CompressPage", "OCRPage", "ScanCleanupPage", "PDFAPage", "ExtractTextPage", "ExtractImagesPage"]),
    ("Documento",
     ["BookmarksPage", "AttachmentsPage", "LayersPage", "MetadataPage", "PageNumbersPage", "WatermarkPage"]),
    ("Automatizar", ["BatchPage"]),
]  # fmt: skip

# Outras palavras que levam à ferramenta na busca da aba Ferramentas (em português e em inglês,
# sem acento: a busca ignora acentos e maiúsculas).
SYNONYMS = {
    "CreatePage": "novo em branco new blank",
    "MergePage": "juntar unir combinar join combine",
    "SplitPage": "separar quebrar dividir split separate",
    "PagesPage": "girar rotacionar reordenar excluir rotate reorder delete",
    "OrganizePage": "reordenar girar duplicar excluir extrair rotate reorder duplicate extract",
    "CompressPage": "reduzir diminuir tamanho otimizar shrink reduce size optimize",
    "ConvertPage": "word docx excel xlsx powerpoint pptx imagem jpg png html markdown texto image",
    "WatermarkPage": "carimbo rascunho confidencial stamp draft",
    "ProtectPage": "senha criptografar bloquear desbloquear password encrypt lock unlock",
    "MetadataPage": "propriedades titulo autor xmp properties title author",
    "PageNumbersPage": "numerar paginas bates rodape numbers footer",
    "PDFAPage": "arquivamento pdfa archive",
    "ExtractTextPage": "copiar texto txt copy text",
    "ExtractImagesPage": "fotos imagens salvar photos images",
    "CropPage": "margens recortar redimensionar margins trim resize",
    "EditPage": "texto imagem link editar edit text image",
    "BookmarksPage": "sumario indice outline toc",
    "LayersPage": "ocg camadas layers",
    "AttachmentsPage": "arquivos embutidos anexar attachments embedded",
    "FormFieldsPage": "formulario campos form fields acroform",
    "AnnotationsPage": "comentar realcar sublinhar nota caneta comment highlight note pen markup",
    "MeasurePage": "distancia regua medir distance ruler measure",
    "OCRPage": "reconhecer texto escaneado pesquisavel recognize scanned searchable tesseract",
    "ScanCleanupPage": "escaneado paginas em branco endireitar scanned blank deskew",
    "RedactionPage": "cpf cnpj tarjar ocultar censurar lgpd apagar sanitizar redact hide censor sanitize",
    "FillSignPage": "assinar assinatura rubrica iniciais preencher sign signature initials fill",
    "SignaturePage": "assinar assinatura certificado icp digital verificar sign signature certificate verify",
    "AccessibilityPage": "pdfua leitor de tela acessivel screen reader accessible",
    "ComparePage": "diferencas versoes diff differences versions",
    "BatchPage": "lote pasta automatizar varios batch folder automate many",
}

# A coluna de ícones à direita de cada documento: as ferramentas mais usadas, um clique.
QUICK_TOOLS = [
    "EditPage", "AnnotationsPage", "OrganizePage", "MergePage", "CompressPage", "ConvertPage",
    "FillSignPage", "SignaturePage", "ProtectPage", "RedactionPage", "OCRPage", "FormFieldsPage",
]  # fmt: skip

# Ferramentas que marcam áreas arrastando no visualizador (ver ui/area_pick_state.py).
AREA_PICK_PAGES = {"EditPage", "FormFieldsPage", "CropPage", "SignaturePage", "FillSignPage"}
