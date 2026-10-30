"""Textos para o usuário que a interface consegue traduzir.

O `core` não depende da interface e escreve as mensagens em português. Uma mensagem fixa
("Senha incorreta.") é traduzida pela interface pelo próprio texto. Uma mensagem com valores
("Página 7 não existe: o documento tem 5 páginas.") não pode ser procurada no dicionário
depois de montada; por isso é criada com `Message(modelo, **valores)`, que se comporta como
o texto pronto (é um `str`) mas guarda o modelo e os valores para a interface traduzir o
modelo e montar de novo (`ui.i18n.tr_message`).

Uso: `raise ValueError(Message("Página {page} não existe.", page=7))`, ou numa lista de
avisos devolvida por uma operação.
"""


class Message(str):
    template: str
    params: dict

    def __new__(cls, template: str, **params):
        text = template.format(**params) if params else template
        obj = super().__new__(cls, text)
        obj.template = template
        obj.params = params
        return obj

    def __reduce__(self):
        return (_rebuild, (self.template, self.params))


def _rebuild(template: str, params: dict) -> "Message":
    return Message(template, **params)


def plural_message(count: int, one: str, many: str, **params) -> Message:
    """"1 página" ou "25 páginas": a `Message` no singular (`one`, sem {count}) ou no plural
    (`many`, com {count}); a interface traduz o modelo escolhido."""
    return Message(one if count == 1 else many, count=count, **params)


# "O documento tem 25 páginas: confira as páginas informadas." (páginas escolhidas fora do documento)
DOC_PAGES = (
    "O documento tem 1 página: confira as páginas informadas.",
    "O documento tem {count} páginas: confira as páginas informadas.",
)
