"""Linha de comando do OpenFolio (A13): as operações do `core`, sem a interface.

    openfolio merge a.pdf b.pdf -o junto.pdf
    openfolio rotate contrato.pdf -o girado.pdf --paginas "1-3, 5" --angulo 90
    openfolio info contrato.pdf --json

Como na interface, nada é sobrescrito sem pedir (`--force`), páginas contam a partir de 1 e
toda gravação é atômica: um erro ou Ctrl+C nunca deixa um arquivo pela metade. Códigos de
saída: 0 ok, 1 erro na operação, 2 uso errado, 130 interrompido.
"""

import argparse
import dataclasses
import datetime
import getpass
import json
import sys
from pathlib import Path

from pypdf.errors import PyPdfError

from .base import READ, EncryptedPDFError, RestrictedPDFError, open_reader, remember_password
from .progress import OperationCancelled, Progress

_LOCKED = "o PDF {path} está protegido por senha: informe-a com --senha."
_RESTRICTED = (
    "a proteção de {path} não permite esta operação: tire a senha antes com "
    '"openfolio unlock" (o resultado sai sem proteção).'
)


class _Failure(Exception):
    """Erro que a CLI explica com a própria mensagem (sem traceback)."""


def _shows_progress(args) -> bool:
    return not args.quiet and sys.stderr.isatty()


def _progress(args) -> Progress | None:
    """Andamento numa linha só do stderr, quando ele é um terminal."""
    if not _shows_progress(args):
        return None

    def report(done: int, total: int, message: str) -> None:
        counter = f" {done}/{total}" if total else ""
        sys.stderr.write(f"\r{message}{counter}\033[K")
        sys.stderr.flush()

    return Progress(report)


def _output(args, path: str | None = None) -> str:
    output = path or args.output
    if Path(output).exists() and not args.force:
        raise _Failure(f"{output} já existe: escolha outro nome ou use --force para sobrescrever.")
    return output


def _output_dir(args) -> str:
    """A pasta das partes ou imagens: os nomes saem fixos (doc_part1.pdf), então uma pasta
    com arquivos só vale com --force."""
    folder = Path(args.output)
    if folder.is_dir() and any(folder.iterdir()) and not args.force:
        raise _Failure(f"a pasta {args.output} não está vazia: escolha outra ou use --force.")
    folder.mkdir(parents=True, exist_ok=True)
    return args.output


def _pages(args, path: str, text: str | None) -> list[int] | None:
    if text is None:
        return None
    from ui.page_ranges import parse_page_ranges  # sem Qt: só lê "1-3, 5, 8-"

    return parse_page_ranges(text, len(open_reader(path, purpose=READ).pages))


def _ask_password(prompt: str, confirm: bool = False) -> str:
    password = getpass.getpass(prompt)
    if confirm and getpass.getpass("Repita a senha: ") != password:
        raise _Failure("as senhas não conferem.")
    return password


# -- comandos -------------------------------------------------------------------------


def _merge(args):
    from .merge import MergePDF

    pages = None
    if args.paginas is not None:
        if len(args.paginas) != len(args.inputs):
            raise _Failure("use --paginas uma vez para cada arquivo, na mesma ordem (\"todas\" para o arquivo inteiro).")
        pages = [
            None if text.strip().lower() == "todas" else _pages(args, path, text)
            for path, text in zip(args.inputs, args.paginas)
        ]
    if args.versos_invertidos and not args.intercalar:
        raise _Failure("--versos-invertidos só vale com --intercalar.")
    MergePDF().run(
        args.inputs,
        _output(args),
        progress=_progress(args),
        pages=pages,
        bookmark_per_file=args.marcador_por_arquivo,
        interleave=args.intercalar,
        reverse_second=args.versos_invertidos,
    )
    return f"{len(args.inputs)} arquivo(s) juntado(s) em {args.output}."


def _split(args):
    from .split import SplitAtBlankPages, SplitByBookmarks, SplitByRanges, SplitBySize, SplitPDF

    folder = _output_dir(args)
    note = ""
    if args.marcadores:
        paths = SplitByBookmarks().run(args.input, folder)
    elif args.intervalos is not None:
        groups = [_pages(args, args.input, group) for group in args.intervalos.split(";") if group.strip(", ")]
        if not groups:
            raise _Failure('informe as páginas de cada arquivo, separadas por ";": --intervalos "1-3; 4-".')
        paths = SplitByRanges().run(args.input, folder, groups)
    elif args.tamanho_max is not None:
        if args.tamanho_max <= 0:
            raise _Failure("--tamanho-max precisa ser maior que zero.")
        max_bytes = round(args.tamanho_max * 1024 * 1024)
        paths = SplitBySize().run(args.input, folder, max_bytes, _progress(args))
        big = [Path(p).name for p in paths if Path(p).stat().st_size > max_bytes]
        if big:
            note = f" Passaram do limite, por terem uma página maior que ele: {', '.join(big)}."
    elif args.paginas_em_branco:
        paths = SplitAtBlankPages().run(args.input, folder, _progress(args))
    else:
        if args.paginas_por_arquivo < 1:
            raise _Failure("--paginas-por-arquivo precisa ser pelo menos 1.")
        paths = SplitPDF().run(args.input, folder, pages_per_file=args.paginas_por_arquivo)
    return f"{len(paths)} arquivo(s) em {args.output}.{note}"


def _rotate(args):
    from .pages import RotatePages

    pages = _pages(args, args.input, args.paginas)
    RotatePages().run(args.input, _output(args), angle=args.angulo, pages=pages)
    return f"Páginas giradas em {args.angulo}°: {args.output}."


def _remove(args):
    from .pages import RemovePages

    RemovePages().run(args.input, _output(args), _pages(args, args.input, args.paginas))
    return f"Páginas removidas: {args.output}."


def _extract(args):
    from .pages import ArrangePages

    pages = _pages(args, args.input, args.paginas)
    ArrangePages().run(args.input, _output(args), [(page, 0) for page in pages])
    return f"{len(pages)} página(s) extraída(s) para {args.output}."


def _compress(args):
    from .compress import CompressPDF

    result = CompressPDF().run(
        args.input,
        _output(args),
        level=args.nivel,
        grayscale=args.cinza,
        progress=_progress(args),
    )
    if not result.written:
        return "O arquivo já estava compacto: comprimir não o deixaria menor, e nada foi gravado."
    return f"{args.output}: {result.reduction_percent:.0f}% menor (de {result.original_size} para {result.compressed_size} bytes)."


def _protect(args):
    from .protect import ProtectPDF

    password = args.senha_nova if args.senha_nova is not None else _ask_password("Senha para abrir: ", confirm=True)
    if not password:
        raise _Failure("a senha não pode ser vazia.")
    ProtectPDF().run(args.input, _output(args), password, owner_password=args.senha_dono)
    return f"Protegido com senha: {args.output}."


def _unlock(args):
    from .protect import UnlockPDF

    password = args.senha if args.senha is not None else _ask_password("Senha do PDF: ")
    UnlockPDF().run(args.input, _output(args), password)
    return f"Sem senha: {args.output}."


def _watermark(args):
    from .watermark import AddWatermark

    if not (args.texto or args.imagem):
        raise _Failure("informe --texto ou --imagem.")
    pages = _pages(args, args.input, args.paginas)
    AddWatermark().run(
        args.input,
        _output(args),
        args.texto or "",
        opacity=args.opacidade,
        font_size=args.tamanho,
        rotation=args.rotacao,
        color=args.cor,
        image_path=args.imagem,
        image_width=args.largura / 100,
        position=args.posicao,
        behind=args.atras,
        pages=sorted(set(pages)) if pages is not None else None,
    )
    return f"Marca d'água aplicada: {args.output}."


def _number(args):
    from .fonts import MONO, SANS, SANS_BOLD
    from .page_numbers import AddPageNumbers

    pages = _pages(args, args.input, args.paginas)
    AddPageNumbers().run(
        args.input,
        _output(args),
        start_at=args.inicio,
        font_size=args.tamanho,
        position=args.posicao,
        style={"arabicos": "arabic", "romanos": "roman", "ROMANOS": "ROMAN"}[args.algarismos],
        skip_first=args.pular,
        pages=sorted(set(pages)) if pages is not None else None,
        use_page_labels=args.rotulos,
        font={"normal": SANS, "negrito": SANS_BOLD, "mono": MONO}[args.fonte],
    )
    return f"Páginas numeradas: {args.output}."


def _ocr(args):
    from .ocr import OCRDocument

    count = OCRDocument().run(
        args.input,
        _output(args),
        language=args.idioma,
        mode={"escaneadas": "auto", "todas": "force", "refazer": "redo"}[args.paginas],
        detect_orientation=args.orientacao or args.endireitar,
        straighten=args.endireitar,
        progress=_progress(args),
    )
    return f"Texto reconhecido em {count} página(s): {args.output}."


def _pdfa(args):
    from .pdfa import ConvertToPDFA

    result = ConvertToPDFA().run(
        args.input, _output(args), part=args.parte, conformance=args.conformidade, progress=_progress(args)
    )
    if not result.written:
        raise _Failure("não deu para converter, nada foi gravado:\n  " + "\n  ".join(map(str, result.issues)))
    return f"PDF/A-{args.parte}{args.conformidade.upper()} gravado: {args.output}."


def _text(args):
    from .extract_text import ExtractText

    ExtractText().run(args.input, _output(args), layout=args.layout)
    return f"Texto extraído para {args.output}."


def _images(args):
    from .convert import ConvertToImages

    if not 0 < args.escala <= 10:
        raise _Failure("--escala precisa estar entre 0 e 10.")
    pages = _pages(args, args.input, args.paginas)
    paths = ConvertToImages().run(
        args.input,
        _output_dir(args),
        scale=args.escala,
        progress=_progress(args),
        image_format=args.formato,
        pages=sorted(set(pages)) if pages is not None else None,
    )
    return f"{len(paths)} imagem(ns) em {args.output}."


def _json_default(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return str(value)


def _info(args):
    from .properties import ReadDocumentProperties
    from ui.page_ranges import format_page_ranges

    properties = ReadDocumentProperties().run(args.input)
    if args.json:
        return json.dumps(dataclasses.asdict(properties), default=_json_default, ensure_ascii=False, indent=2)

    meta = properties.metadata
    lines = [
        f"Arquivo: {args.input}",
        f"Versão do PDF: {properties.version}",
        f"Páginas: {properties.page_count}",
        f"Tamanho: {properties.file_size} bytes",
    ]
    labels = [("title", "Título"), ("author", "Autor"), ("subject", "Assunto"), ("keywords", "Palavras-chave"),
              ("creator", "Criado com"), ("producer", "Produtor do PDF")]
    lines += [f"{label}: {meta[key]}" for key, label in labels if meta[key]]
    for key, label in (("created", "Criado em"), ("modified", "Modificado em")):
        if meta[key] is not None:
            lines.append(f"{label}: {meta[key]:%d/%m/%Y %H:%M}")
    lines.append(f"Marcado para acessibilidade: {'sim' if properties.tagged else 'não'}")
    if properties.pdfa:
        lines.append(f"PDF/A declarado: {properties.pdfa}")
    if properties.form_fields:
        lines.append(f"Campos de formulário: {properties.form_fields}")
    if properties.permissions is None:
        lines.append("Proteção: nenhuma")
    else:
        denied = [key for key, allowed in properties.permissions.items() if not allowed]
        lines.append(
            f"Proteção: {properties.encryption}, senha para abrir: {'sim' if properties.needs_password else 'não'}, "
            f"não permite: {', '.join(denied) or 'nada'}"
        )
    lines.append(f"Fontes ({len(properties.fonts)}):")
    for font in properties.fonts:
        embedded = "embutida" + (" (subconjunto)" if font.subset else "") if font.embedded else (
            "não embutida (padrão)" if font.standard else "NÃO EMBUTIDA"
        )
        lines.append(f"  {font.name or '(sem nome)'} — {font.kind}, {embedded}, páginas {format_page_ranges(font.pages)}")
    lines.append("Tamanhos de página:")
    for group in properties.page_sizes:
        mm = f"{group.width * 25.4 / 72:.0f} × {group.height * 25.4 / 72:.0f} mm"
        lines.append(f"  {mm} ({group.width:g} × {group.height:g} pt): páginas {format_page_ranges(group.pages)}")
    return "\n".join(lines)


# -- argumentos -----------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    from .compress import LEVELS as COMPRESSION_LEVELS

    parser = argparse.ArgumentParser(
        prog="openfolio",
        description="Operações do OpenFolio PDF Suite pela linha de comando. 100% local.",
        epilog='Páginas contam a partir de 1: "1-3, 5, 8-" (8- vai até o fim). Ajuda de um comando: openfolio COMANDO -h',
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-f", "--force", action="store_true", help="sobrescreve a saída se ela já existir")
    common.add_argument("-q", "--quiet", action="store_true", help="não mostra andamento nem a mensagem final")
    common.add_argument("--senha", help="senha dos PDFs de entrada protegidos (fica no histórico do shell)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")

    def command(name, handler, help_text, output="arquivo"):
        sub = commands.add_parser(name, parents=[common], help=help_text, description=help_text)
        sub.set_defaults(handler=handler)
        if name != "merge":
            sub.add_argument("input", metavar="ENTRADA.pdf")
        if output:
            sub.add_argument("-o", "--output", required=True, metavar="SAIDA" if output == "arquivo" else "PASTA")
        return sub

    sub = commands.add_parser("merge", parents=[common], help="junta PDFs na ordem dada", description="Junta PDFs na ordem dada.")
    sub.set_defaults(handler=_merge)
    sub.add_argument("inputs", nargs="+", metavar="ENTRADA.pdf")
    sub.add_argument("-o", "--output", required=True, metavar="SAIDA")
    sub.add_argument(
        "--paginas",
        action="append",
        metavar="PAGINAS",
        help='páginas de cada arquivo: repita uma vez por arquivo, na ordem ("todas" para o arquivo inteiro)',
    )
    sub.add_argument("--marcador-por-arquivo", action="store_true", help="um marcador no começo de cada arquivo")
    sub.add_argument("--intercalar", action="store_true", help="dois arquivos, frentes e versos: 1ª do primeiro, 1ª do segundo...")
    sub.add_argument("--versos-invertidos", action="store_true", help="com --intercalar: o segundo arquivo está na ordem inversa")

    sub = command("split", _split, "divide em vários PDFs (numa pasta)", output="pasta")
    mode = sub.add_mutually_exclusive_group()
    mode.add_argument("--paginas-por-arquivo", type=int, default=1, metavar="N")
    mode.add_argument("--marcadores", action="store_true", help="um arquivo por marcador de primeiro nível")
    mode.add_argument("--intervalos", metavar="PAGINAS", help='as páginas de cada arquivo, separadas por ";": "1-3; 4-10; 11-"')
    mode.add_argument("--tamanho-max", type=float, metavar="MB", help="arquivos de até MB megabytes")
    mode.add_argument("--paginas-em-branco", action="store_true", help="divide nas páginas em branco (que saem)")

    sub = command("rotate", _rotate, "gira páginas")
    sub.add_argument("--angulo", type=int, choices=(90, 180, 270), default=90, help="sentido horário (padrão 90)")
    sub.add_argument("--paginas", help="padrão: todas")

    sub = command("remove", _remove, "remove páginas")
    sub.add_argument("--paginas", required=True)

    sub = command("extract", _extract, "copia páginas para um PDF novo, na ordem dada")
    sub.add_argument("--paginas", required=True)

    sub = command("compress", _compress, "reduz o tamanho do arquivo")
    sub.add_argument("--nivel", choices=COMPRESSION_LEVELS, default="medium")
    sub.add_argument("--cinza", action="store_true", help="converte as imagens para tons de cinza")

    sub = command("protect", _protect, "protege com senha (pergunta a senha se --senha-nova faltar)")
    sub.add_argument("--senha-nova", help="senha para abrir (fica no histórico do shell)")
    sub.add_argument("--senha-dono", help="senha de permissões (padrão: a mesma)")

    command("unlock", _unlock, "tira a senha (pergunta a senha se --senha faltar)")

    sub = command("watermark", _watermark, "aplica uma marca d'água de texto ou imagem")
    sub.add_argument("--texto")
    sub.add_argument("--imagem", help="um logotipo (PNG, JPEG...) no lugar do texto")
    sub.add_argument("--largura", type=float, default=30, help="da imagem, em %% da largura da página (padrão: 30)")
    sub.add_argument("--opacidade", type=float, default=0.3)
    sub.add_argument("--tamanho", type=int, default=40)
    sub.add_argument("--rotacao", type=float, default=45)
    sub.add_argument("--cor", default="000000", help="do texto, em hexadecimal (padrão: 000000, preto)")
    sub.add_argument(
        "--posicao",
        choices=("center", "top-left", "top-right", "bottom-left", "bottom-right", "tile"),
        default="center",
        help="tile repete a marca pela página",
    )
    sub.add_argument("--atras", action="store_true", help="por baixo do conteúdo")
    sub.add_argument("--paginas", help="padrão: todas")

    sub = command("number", _number, "numera as páginas")
    sub.add_argument("--inicio", type=int, default=1)
    sub.add_argument("--tamanho", type=int, default=10)
    sub.add_argument(
        "--posicao",
        choices=("header-left", "header-center", "header-right", "footer-left", "footer-center", "footer-right"),
        default="footer-center",
    )
    sub.add_argument("--algarismos", choices=("arabicos", "romanos", "ROMANOS"), default="arabicos")
    sub.add_argument("--pular", type=int, default=0, metavar="N", help="deixa as N primeiras páginas sem número")
    sub.add_argument("--paginas", help="só estas páginas, numeradas em sequência (padrão: todas)")
    sub.add_argument("--rotulos", action="store_true", help="escreve os rótulos de página do documento")
    sub.add_argument("--fonte", choices=("normal", "negrito", "mono"), default="normal")

    sub = command("ocr", _ocr, "reconhece o texto de páginas escaneadas (Tesseract)")
    sub.add_argument("--idioma", default="por", help="idioma do Tesseract (padrão por; vários: por+eng)")
    sub.add_argument(
        "--paginas",
        choices=("escaneadas", "todas", "refazer"),
        default="escaneadas",
        help="refazer tira o texto de um OCR anterior e reconhece de novo",
    )
    sub.add_argument("--orientacao", action="store_true", help="lê páginas digitalizadas de lado")
    sub.add_argument("--endireitar", action="store_true", help="endireita as páginas tortas ou de lado no documento")

    sub = command("pdfa", _pdfa, "converte para PDF/A")
    sub.add_argument("--parte", type=int, choices=(1, 2, 3), default=2)
    sub.add_argument("--conformidade", choices=("A", "B", "U", "a", "b", "u"), default="B")

    sub = command("text", _text, "extrai o texto para um .txt")
    sub.add_argument("--layout", action="store_true", help="mantém o layout das colunas")

    sub = command("images", _images, "converte as páginas em imagens (numa pasta)", output="pasta")
    sub.add_argument("--escala", type=float, default=2.0, help="2 = 144 DPI (padrão)")
    sub.add_argument(
        "--formato", choices=("png", "jpeg", "tiff"), default="png", help="png (padrão), jpeg ou tiff (um arquivo multipágina)"
    )
    sub.add_argument("--paginas", help="padrão: todas")

    sub = command("info", _info, "mostra as propriedades do documento", output=None)
    sub.add_argument("--json", action="store_true", help="saída em JSON, para scripts")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        # Saída redirecionada no Windows usa a página de código local, que não tem todo
        # caractere de um nome de fonte ou de título.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = _parser().parse_args(argv)
    inputs = args.inputs if args.command == "merge" else [args.input]
    if args.senha is not None and args.command != "unlock":
        for path in inputs:
            remember_password(path, args.senha)
    try:
        message = args.handler(args)
    except KeyboardInterrupt:
        print("\nopenfolio: interrompido; nada foi gravado.", file=sys.stderr)
        return 130
    except OperationCancelled:
        return 130
    except RestrictedPDFError:
        return _error(_RESTRICTED.format(path=", ".join(inputs)))
    except EncryptedPDFError:
        return _error(_LOCKED.format(path=", ".join(inputs)))
    except FileNotFoundError as exc:
        return _error(f"arquivo não encontrado: {exc.filename}")
    except PermissionError as exc:
        return _error(f"sem permissão para usar {exc.filename} (está aberto em outro programa?)")
    except PyPdfError as exc:
        return _error(f"não deu para ler o PDF (corrompido ou não é PDF): {exc}")
    except (_Failure, ValueError, OSError, RuntimeError) as exc:  # RuntimeError: Tesseract ausente
        return _error(str(exc))
    finally:
        if _shows_progress(args):
            sys.stderr.write("\r\033[K")
    if message and (not args.quiet or args.command == "info"):
        print(message)
    return 0


def _error(message: str) -> int:
    print(f"openfolio: erro: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
