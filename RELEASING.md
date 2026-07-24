# Releases

Como gerar uma nova release (beta ou estável) do OpenFolio PDF Suite.

## Passo a passo

1. Atualize a versão em `pyproject.toml` (`version = "..."`) e em `ui/main_window.py`
   (`APP_VERSION = "..."`), se ainda não estiver correta.
2. Faça o commit dessa mudança em `main`.
3. Crie e publique uma tag começando com `v`:

   ```bash
   git tag v0.2.0-beta.1
   git push origin v0.2.0-beta.1
   ```

4. O workflow `.github/workflows/release.yml` builda automaticamente, um job por
   plataforma (cada um na VM nativa daquele SO):
   - **Windows**: instalador `OpenFolioPDFSuite-Setup-<versão>.exe` (Inno Setup)
   - **Linux**: `OpenFolioPDFSuite-<versão>-x86_64.AppImage` e
     `openfolio-pdf-suite_<versão>_amd64.deb`
   - **macOS**: `OpenFolioPDFSuite-<versão>.dmg` (sem assinatura/notarização)

   e publica os quatro arquivos numa GitHub Release com o mesmo nome da tag. Se a
   versão contiver `beta`, a release é marcada automaticamente como pré-release.

## Build local (por plataforma)

Precisa da dependência opcional `build`:

```bash
pip install -e ".[build]"
```

### Windows

```powershell
pyinstaller packaging\pyinstaller\openfolio.spec --noconfirm
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.2.0-beta.1 packaging\windows\installer.iss
```

Gera `dist\installer\OpenFolioPDFSuite-Setup-0.2.0-beta.1.exe`.

### Linux

```bash
pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
bash packaging/linux/build_appimage.sh 0.2.0-beta.1
bash packaging/linux/build_deb.sh 0.2.0-beta.1
```

### macOS

```bash
pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm
bash packaging/macos/build_dmg.sh 0.2.0-beta.1
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

Isso é esperado numa release beta de um projeto open source sem orçamento pra
certificados — não indica nenhum problema com o instalador em si.

## Estrutura do empacotamento

```text
packaging/
  pyinstaller/openfolio.spec   Spec compartilhado entre as 3 plataformas
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
