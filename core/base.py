"""Classes base compartilhadas pelos módulos de core."""


class PDFOperation:
    """Interface base para operações sobre arquivos PDF."""

    def run(self, *args, **kwargs):
        raise NotImplementedError
