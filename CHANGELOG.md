# O que mudou no OpenFolio PDF Suite

O OpenFolio PDF Suite não tem número de versão: há uma só, que recebe atualizações. Cada
atualização é identificada pela data em que foi publicada e só é instalada se você aceitar,
depois de ver o que ela traz (o texto de cada uma abaixo é o que aparece no aviso do app).

## Próxima atualização

Ainda não publicada.

### Segurança e confiabilidade

- A redação funciona em páginas giradas e recortadas, confere o resultado antes de salvar e
  nunca grava um arquivo em que o texto marcado continue legível.
- A limpeza de dados ocultos varre o documento inteiro e mostra o que foi removido.
- A verificação de assinaturas digitais diz o que a assinatura cobre e se o documento foi
  alterado depois dela.
- Anexos extraídos não podem sair da pasta escolhida nem sobrescrever arquivos.
- Mesclar, dividir e reorganizar páginas mantêm marcadores, metadados, anexos, camadas e
  rótulos de página; toda gravação é feita por inteiro ou não é feita.

### Uso

- Operações longas mostram o andamento e podem ser canceladas, sem travar a janela.
- O documento aberto ganha desfazer e refazer (Ctrl+Z e Ctrl+Y) para todas as ferramentas.
- Novas ferramentas: imprimir, organizar páginas, preencher formulários direto no documento,
  preencher e assinar, processar uma pasta em lote, redigir por busca de texto, limpar
  escaneados, comparar dois documentos lado a lado, comentários existentes e XFDF,
  propriedades do documento.
- Novas conversões: PDF para Word, Excel e texto; HTML, Markdown e texto para PDF.
- Mesclar escolhe as páginas de cada arquivo, pode criar um marcador por arquivo (com os
  marcadores dele dentro) e intercala frentes e versos escaneados em arquivos separados.
- Dividir também por intervalos (ou as páginas selecionadas nas miniaturas), por tamanho
  máximo de arquivo e a cada página em branco de um lote escaneado.
- No Windows, o instalador oferece escolher o OpenFolio como programa padrão para PDF.
- No Linux, o AppImage oferece aparecer no menu de aplicativos e na escolha do programa para
  abrir PDF (Ajuda > Mostrar no menu de aplicativos).
- Com o OpenFolio já aberto, abrir outro PDF (duplo clique, "Abrir com") abre uma janela nova
  no app aberto, mais rápido; uma operação numa janela não trava as outras.
- Tema claro ou o do sistema, modo apresentação, página dupla e livro, paleta de comandos
  (Ctrl+K) e atalhos de teclado configuráveis.
- Linha de comando (`openfolio`) para usar as ferramentas em scripts, que vem com os
  instaladores (no Windows, a tarefa opcional do instalador a põe no PATH).

### Sem depender de outros programas

- O reconhecimento de texto (OCR) vem com o app, com português, inglês e a detecção de
  páginas escaneadas de lado: não é preciso instalar nada.
- A conversão de Word, Excel e PowerPoint (.docx, .xlsx, .pptx) é feita pelo próprio app.
  Os formatos antigos (.doc, .xls, .ppt) e os do LibreOffice deixaram de ser aceitos.
- O app não usa mais o Ghostscript nem o veraPDF.

### Atualizações

- Ajuda > Verificar atualizações mostra o que a atualização traz e só a instala se você
  aceitar; no Windows, o app baixa, confere o arquivo e instala sozinho. A verificação ao
  iniciar continua desligada até você ligá-la.
- Ajuda > Sobre mostra o arquivo de log, para anexar ao relatar um problema, e as licenças
  dos componentes de terceiros, com a versão exata do Qt, do Tesseract e das bibliotecas
  dele e os textos das licenças. O código-fonte das bibliotecas GPL e LGPL vai junto em cada
  atualização, na página de releases.
