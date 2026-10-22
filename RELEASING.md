# Releases

Como publicar uma atualização do OpenFolio PDF Suite.

O app não tem número de versão para o usuário: há uma versão só, que recebe atualizações.
Cada atualização é identificada, por dentro, pela data em que é publicada (`AAAA.MM.DD`; uma
segunda no mesmo dia vira `AAAA.MM.DD.1`). O app compara esse identificador com o das releases
para saber se há atualização, mostra ao usuário o que ela traz e só a instala se ele aceitar.

## Passo a passo

1. No `CHANGELOG.md`, troque o título `## Próxima atualização` pela data da publicação
   (`## 2026-11-03`), tire a linha "Ainda não publicada." e revise o texto: é exatamente o
   que o usuário lê antes de aceitar.
2. Ponha o mesmo identificador em `pyproject.toml` (`version = "2026.11.3"`), o único lugar
   dele: o app o lê dos metadados do pacote (`core/version.py`).
3. Faça o commit dessas mudanças em `desenvolvimento` e leve `desenvolvimento` para `main`
   (merge): a tag sai de `main`.
4. Crie e publique a tag `v` + identificador:

   ```bash
   git tag v2026.11.3
   git push origin v2026.11.3
   ```

   O workflow recusa a release se a tag não bater com o `pyproject.toml`, se o
   `CHANGELOG.md` não tiver o trecho dela (`packaging/release_notes.py`) ou se o CI
   (`ci.yml`, chamado pelo próprio workflow de release) reprovar no commit da tag.

5. O workflow `.github/workflows/release.yml` builda automaticamente, um job por
   plataforma (cada um na VM nativa daquele SO):
   - **Windows**: instalador `OpenFolioPDFSuite-Setup.exe` (Inno Setup)
   - **Linux**: `OpenFolioPDFSuite-x86_64.AppImage` e `openfolio-pdf-suite_amd64.deb`
   - **macOS**: `OpenFolioPDFSuite.dmg` (sem assinatura/notarização)

   e publica os quatro arquivos numa GitHub Release, com o trecho do `CHANGELOG.md` como
   descrição. Os nomes dos arquivos não mudam de uma atualização para outra; o app do
   Windows baixa o `OpenFolioPDFSuite-Setup.exe` da release nova, confere o SHA-256 que o
   GitHub publica para ele e o roda com `/SILENT` (atualiza por cima e abre o app de novo).
6. Depois de publicar, abra uma seção `## Próxima atualização` no topo do `CHANGELOG.md`.

Uma release marcada como pré-release no GitHub é ignorada pela verificação do app: serve
para testar um build sem oferecê-lo a ninguém.

## Build local (por plataforma)

Precisa da dependência opcional `build` e do Tesseract instalado na máquina de build: o app
leva uma cópia dele (o usuário final não instala nada). Os idiomas que vão junto são baixados
antes, com o SHA-256 conferido:

```bash
pip install -c requirements-lock.txt -e ".[build]"
python packaging/fetch_tessdata.py
```

O Tesseract vem do instalador do UB Mannheim no Windows (no CI, `choco install tesseract`, e
o `llvm-strip --strip-debug` tira os ~90 MB de símbolos de depuração das DLLs), do
`apt install tesseract-ocr` no Linux e do `brew install tesseract` no macOS. O spec recusa o
build sem o Tesseract ou sem os idiomas.

### Windows

```powershell
pyinstaller packaging\pyinstaller\openfolio.spec --noconfirm
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=2026.10.21 packaging\windows\installer.iss
```

Gera `dist\installer\OpenFolioPDFSuite-Setup.exe`.

### Linux

```bash
pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
bash packaging/linux/build_appimage.sh
bash packaging/linux/build_deb.sh 2026.10.21
```

### macOS

```bash
pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
bash packaging/macos/build_dmg.sh
```

## Sobre a assinatura de código

Nenhum dos três instaladores é assinado digitalmente (exigiria um certificado pago de
assinatura de código no Windows e uma conta paga de desenvolvedor Apple no macOS). Na
prática:

- **Windows**: o SmartScreen pode avisar "O Windows protegeu o computador" no primeiro
  uso — clique em "Mais informações" → "Executar assim mesmo".
- **macOS**: o Gatekeeper vai bloquear a primeira abertura ("o app está danificado" ou
  "não foi possível verificar o desenvolvedor"). Clique com o botão direito no app →
  Abrir, ou rode `xattr -cr "/Applications/OpenFolioPDFSuite.app"` no Terminal.
- **Linux**: o AppImage pode precisar de `chmod +x` antes de rodar; o `.deb` não tem
  esse problema.

Isso é esperado num projeto open source sem orçamento para certificados — não indica
nenhum problema com o instalador em si.

## Estrutura do empacotamento

```text
packaging/
  pyinstaller/openfolio.spec   Spec compartilhado entre as 3 plataformas (leva o Tesseract junto)
  fetch_tessdata.py            Baixa os idiomas do Tesseract (eng, por, osd) para build/tessdata
  icons/                       icon.ico, icon.icns e icon_256.png gerados a partir de assets/icon.png
  windows/installer.iss        Script do Inno Setup
  linux/
    openfolio-pdf-suite.desktop
    build_appimage.sh
    build_deb.sh
  macos/build_dmg.sh
```

Os ícones em `packaging/icons/` são gerados a partir de `assets/icon.png`; para
regenerá-los depois de trocar o ícone da aplicação, use `Pillow`:

```python
from PIL import Image

src = Image.open("assets/icon.png").convert("RGBA")
src.save("packaging/icons/icon.ico", format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
sizes = [16, 32, 64, 128, 256, 512]
imgs = [src.resize((s, s), Image.LANCZOS) for s in sizes]
imgs[0].save("packaging/icons/icon.icns", format="ICNS", append_images=imgs[1:])
src.save("packaging/icons/icon_256.png")
```
