"""O catálogo das ferramentas: a aba Ferramentas, a coluna de ferramentas de cada documento, o
menu e a paleta de comandos saem daqui.

Cada ferramenta é (ícone, título, subtítulo, módulo, classe). Os textos são traduzidos ao montar
a tela; o módulo só é importado quando a ferramenta é aberta pela primeira vez, o que tira da
abertura do app o custo de bibliotecas pesadas como pyhanko (assinatura) e pytesseract (OCR).
"""

from dataclasses import dataclass

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


# -- as ferramentas que o usuário vê ------------------------------------------------------
#
# As 30 telas acima viram 23 ferramentas em 8 grupos: telas parecidas são modos de uma
# ferramenta só (Converter, Extrair texto e Extrair imagens são os modos de Converter). O id de
# cada ferramenta é a classe da tela principal dela, o que mantém valendo os atalhos e as
# configurações salvas com os nomes antigos ("tool.ConvertPage"); as outras telas ficam como
# modos ("tool.ExtractTextPage" abre Converter › Extrair texto).


@dataclass(frozen=True)
class Mode:
    label: str
    page: str  # a classe da tela que faz o trabalho
    items: tuple[int, ...] = ()  # as opções do seletor da tela que este modo mostra (vazio: todas)


@dataclass(frozen=True)
class Tool:
    id: str
    icon: str
    title: str
    description: str
    modes: tuple[Mode, ...]
    short: str = ""  # o rótulo na coluna rápida


# O seletor de cada tela que os modos filtram (as que não estão aqui usam `mode_combo`).
SELECTOR_OF = {"ConvertPage": "direction_combo", "WatermarkPage": "kind_combo", "FillSignPage": "kind_combo"}

TOOLS = {tool.id: tool for tool in [
    Tool("OrganizePage", "build_organize_icon", "Organizar páginas",
         "Reordene, gire, duplique, exclua ou extraia páginas.",
         (Mode("Visual", "OrganizePage"), Mode("Por intervalos", "PagesPage")), "Organizar"),
    Tool("MergePage", "build_merge_icon", "Mesclar", "Junte vários PDFs em um só, na ordem que você escolher.",
         (Mode("Mesclar", "MergePage"),), "Mesclar"),
    Tool("SplitPage", "build_split_icon", "Dividir", "Separe o PDF em vários arquivos menores.",
         (Mode("Por nº de páginas", "SplitPage", (0,)), Mode("Por marcador", "SplitPage", (1,)),
          Mode("Por intervalos", "SplitPage", (2,)), Mode("Por tamanho", "SplitPage", (3,)),
          Mode("Por página em branco", "SplitPage", (4,)))),
    Tool("CropPage", "build_crop_icon", "Cortar e redimensionar", "Corte as margens ou mude o tamanho das páginas.",
         (Mode("Cortar margens", "CropPage", (0,)), Mode("Mudar tamanho", "CropPage", (1,)))),
    Tool("CreatePage", "build_create_icon", "Novo PDF em branco", "Crie um PDF vazio, com uma ou mais páginas.",
         (Mode("Novo PDF", "CreatePage"),)),
    Tool("EditPage", "build_edit_icon", "Editar texto, imagem e links",
         "Reescreva um trecho, troque uma imagem ou mude os links do PDF.",
         (Mode("Texto", "EditPage", (1,)), Mode("Imagem", "EditPage", (0,)), Mode("Links", "EditPage", (2, 3, 4))),
         "Editar"),
    Tool("WatermarkPage", "build_watermark_icon", "Marca d'água", "Ponha um texto ou um logotipo sobre as páginas.",
         (Mode("Texto", "WatermarkPage", (0,)), Mode("Imagem", "WatermarkPage", (1,)))),
    Tool("PageNumbersPage", "build_page_numbers_icon", "Numeração e cabeçalho",
         "Numere as páginas ou ponha um cabeçalho e um rodapé.",
         (Mode("Números de página", "PageNumbersPage", (0,)), Mode("Bates", "PageNumbersPage", (1,)),
          Mode("Cabeçalho e rodapé", "PageNumbersPage", (2,)))),
    Tool("AnnotationsPage", "build_annotations_icon", "Anotações",
         "Realce, comente, desenhe e carimbe; depois grave as marcações no PDF.",
         (Mode("Anotações", "AnnotationsPage"),), "Anotar"),
    Tool("ComparePage", "build_compare_icon", "Comparar versões", "Veja o que mudou entre duas versões de um PDF.",
         (Mode("Lado a lado", "ComparePage", (0,)), Mode("Texto", "ComparePage", (1,)),
          Mode("Visual", "ComparePage", (2,)))),
    Tool("MeasurePage", "build_measure_icon", "Medir distâncias", "Meça a distância entre dois pontos da página.",
         (Mode("Medir", "MeasurePage"),)),
    Tool("FillSignPage", "build_fill_sign_icon", "Preencher e assinar",
         "Escreva na página, assine à mão ou com certificado digital.",
         (Mode("Preencher", "FillSignPage", (0, 1)), Mode("Assinar à mão", "FillSignPage", (2, 3)),
          Mode("Certificado digital", "SignaturePage", (0,)), Mode("Verificar", "SignaturePage", (1,))),
         "Assinar"),
    Tool("FormFieldsPage", "build_form_fields_icon", "Campos de formulário",
         "Crie e edite campos, troque os dados preenchidos ou achate o formulário.",
         (Mode("Criar", "FormFieldsPage", (0, 1)), Mode("Editar", "FormFieldsPage", (2,)),
          Mode("Dados", "FormFieldsPage", (3, 4, 5, 6)), Mode("Achatar", "FormFieldsPage", (7,)))),
    Tool("ConvertPage", "build_convert_icon", "Converter",
         "Transforme o PDF em Word, Excel, imagens ou texto, ou crie um PDF a partir deles.",
         (Mode("Do PDF para…", "ConvertPage", (4, 5, 0, 6)), Mode("Para PDF", "ConvertPage", (2, 1, 7, 3)),
          Mode("Extrair texto", "ExtractTextPage"), Mode("Extrair imagens", "ExtractImagesPage")),
         "Converter"),
    Tool("CompressPage", "build_compress_icon", "Comprimir",
         "Diminua o tamanho do arquivo para enviar por e-mail ou guardar.",
         (Mode("Comprimir", "CompressPage"),), "Comprimir"),
    Tool("OCRPage", "build_ocr_icon", "Escaneados e OCR",
         "Torne um escaneado pesquisável ou limpe as páginas dele.",
         (Mode("Reconhecer texto", "OCRPage"), Mode("Limpar páginas", "ScanCleanupPage")), "OCR"),
    Tool("ProtectPage", "build_protect_icon", "Senha e permissões",
         "Proteja o PDF com senha ou tire a senha de um PDF protegido.",
         (Mode("Proteger", "ProtectPage", (0, 1)), Mode("Remover senha", "ProtectPage", (2,))), "Proteger"),
    Tool("RedactionPage", "build_redaction_icon", "Redigir e limpar",
         "Apague de vez áreas, textos e dados ocultos que não devem sair do PDF.",
         (Mode("Áreas", "RedactionPage", (0,)), Mode("Textos e padrões", "RedactionPage", (2,)),
          Mode("Dados ocultos", "RedactionPage", (1,))), "Redigir"),
    Tool("BookmarksPage", "build_bookmarks_icon", "Sumário", "Monte o sumário de navegação do PDF.",
         (Mode("Sumário", "BookmarksPage"),)),
    Tool("AttachmentsPage", "build_attachments_icon", "Anexos", "Veja, adicione, remova ou extraia arquivos anexados.",
         (Mode("Anexos", "AttachmentsPage"),)),
    Tool("LayersPage", "build_layers_icon", "Camadas", "Escolha quais camadas do PDF aparecem ao abrir.",
         (Mode("Camadas", "LayersPage"),)),
    Tool("MetadataPage", "build_metadata_icon", "Propriedades e conformidade",
         "Edite título e autor, converta para PDF/A ou confira a acessibilidade.",
         (Mode("Informações e metadados", "MetadataPage"), Mode("PDF/A", "PDFAPage"),
          Mode("Acessibilidade", "AccessibilityPage"))),
    Tool("BatchPage", "build_batch_icon", "Processar em lote", "Aplique a mesma operação a todos os PDFs de uma pasta.",
         (Mode("Lote", "BatchPage"),)),
]}  # fmt: skip

# Os grupos da aba Ferramentas, na ordem da grade (4 x 2): (nome, frase de apoio, ferramentas).
GROUPS = [
    ("Montar e organizar", "Juntar, separar e reordenar páginas",
     ["OrganizePage", "MergePage", "SplitPage", "CropPage", "CreatePage"]),
    ("Editar o conteúdo", "Mudar texto, imagens e marcar páginas", ["EditPage", "WatermarkPage", "PageNumbersPage"]),
    ("Revisar e comentar", "Marcar, comparar versões e medir", ["AnnotationsPage", "ComparePage", "MeasurePage"]),
    ("Preencher e assinar", "Formulários e assinaturas", ["FillSignPage", "FormFieldsPage"]),
    ("Converter e reduzir", "Mudar formato, tamanho e ler escaneados", ["ConvertPage", "CompressPage", "OCRPage"]),
    ("Proteger e privacidade", "Senha e remoção de dados sensíveis", ["ProtectPage", "RedactionPage"]),
    ("Informações do documento", "Sumário, anexos e propriedades",
     ["BookmarksPage", "AttachmentsPage", "LayersPage", "MetadataPage"]),
    ("Automatizar", "Repetir em vários arquivos", ["BatchPage"]),
]  # fmt: skip
GROUP_OF = {tool_id: name for name, _phrase, ids in GROUPS for tool_id in ids}

# A coluna rápida de cada documento, de fábrica (o usuário fixa e tira; ver ui/preferences.py).
DEFAULT_QUICK = [
    "AnnotationsPage", "EditPage", "OrganizePage", "MergePage", "CompressPage",
    "ConvertPage", "FillSignPage", "ProtectPage", "RedactionPage", "OCRPage",
]  # fmt: skip


def tool_of_page(class_name: str) -> Tool:
    """A ferramenta de que a tela faz parte."""
    return next(tool for tool in TOOLS.values() if any(mode.page == class_name for mode in tool.modes))


def mode_for(class_name: str, selector_index: int | None) -> tuple[Tool, int]:
    """A ferramenta e o modo de uma tela, pela opção escolhida no seletor dela."""
    tool = tool_of_page(class_name)
    candidates = [i for i, mode in enumerate(tool.modes) if mode.page == class_name]
    for index in candidates:
        if selector_index is None or not tool.modes[index].items or selector_index in tool.modes[index].items:
            return tool, index
    return tool, candidates[0]


def mode_key(tool: Tool, index: int) -> str:
    """A chave estável do comando de um modo: "tool.<tela>" para o primeiro modo de uma tela que
    deixou de ser ferramenta (o nome antigo continua valendo), senão "mode.<ferramenta>.<n>"."""
    page = tool.modes[index].page
    first = next(i for i, mode in enumerate(tool.modes) if mode.page == page) == index
    return f"tool.{page}" if first and page not in TOOLS else f"mode.{tool.id}.{index}"


def command_target(key: str) -> tuple[str, int | None] | None:
    """(ferramenta, modo ou None) de uma chave de comando "tool."/"mode.", ou None."""
    if key.startswith("tool.") and key[5:] in TOOLS:
        return key[5:], None
    for tool in TOOLS.values():
        for index in range(len(tool.modes)):
            if len(tool.modes) > 1 and mode_key(tool, index) == key:
                return tool.id, index
    return None


def page_synonyms(class_name: str) -> str:
    """As palavras que levam a uma tela na busca: os sinônimos e o nome antigo dela."""
    title = SECTIONS[ROW_OF[class_name]][1]
    return f"{SYNONYMS.get(class_name, '')} {title}"

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

# Ferramentas que marcam áreas arrastando no visualizador (ver ui/area_pick_state.py).
AREA_PICK_PAGES = {"EditPage", "FormFieldsPage", "CropPage", "SignaturePage", "FillSignPage"}
