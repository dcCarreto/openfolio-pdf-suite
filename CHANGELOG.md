# O que mudou no OpenFolio PDF Suite

O OpenFolio PDF Suite não tem número de versão: há uma só, que recebe atualizações. Cada
atualização é identificada pela data em que foi publicada e só é instalada se você aceitar,
depois de ver o que ela traz (o texto de cada uma abaixo é o que aparece no aviso do app).

## 2026-10-25

### Visual

- Cores novas nos temas escuro e claro, com contraste conferido para leitura, e a fonte Inter
  embutida no app (licença livre OFL), igual em todos os sistemas.
- O foco do teclado aparece em botões, campos, caixas de marcar e abas.
- Exibir > Animações da interface liga ou desliga as transições da interface: o painel da
  ferramenta abre e fecha deslizando, a gaveta entra pela direita e o rodapé do painel troca
  de estado com um esmaecimento. Desligadas, tudo muda na hora.
- Ícones redesenhados, com o mesmo traço e as mesmas proporções em todo o app.
- F6 leva o foco à próxima região da janela (faixa do topo, barra do documento, documento,
  painel da ferramenta e coluna da direita) e Shift+F6 à anterior; dá para trocar as teclas
  em Editar > Atalhos de teclado.
- Todo botão tem área de clique de pelo menos 28 px, os botões só com ícone têm nome para
  leitores de tela e as dicas da coluna da direita mostram o atalho da ferramenta, se houver.
- Com uma operação em andamento, a barra de status mostra "N tarefas": o painel que ele abre
  lista as operações de todos os documentos, com o andamento e o resultado de cada uma.
- A coluna de miniaturas ganha um título com o número de páginas (ou de marcadores e anexos),
  e a página atual aparece com um contorno e o número em destaque.
- Menus, abas, a busca de ferramentas e comandos e o idioma ficam numa só faixa no topo,
  deixando mais altura para o documento. O idioma troca em "PT | EN".
- As abas de documento se reordenam arrastando. Com alterações não salvas, um ponto aparece
  no lugar do "x"; com uma operação em andamento, um arco gira no lugar do ícone.
- A barra sobre a página tem o número da página editável (digite e Enter), o zoom com um menu
  de tamanhos prontos e o modo Livro ao lado dos outros modos de exibição.
- Numa janela estreita, as miniaturas se recolhem enquanto uma ferramenta está aberta (e voltam
  quando ela fecha) e parte da barra do documento vai para o menu "...".
- Todas as ferramentas seguem o mesmo painel: o documento de entrada no topo, as opções no
  meio e, embaixo, onde gravar o resultado (no próprio documento ou num arquivo novo) e o
  botão da ação, que também roda com Ctrl+Enter.
- Enquanto a operação roda, o rodapé do painel mostra o andamento e o botão Cancelar. Ao
  terminar, o resultado aparece ali mesmo, com Desfazer, em vez de uma janela de aviso; a
  barra de status repete a mensagem. Um erro aparece no mesmo lugar, com Tentar de novo.
- Numa janela estreita, o painel da ferramenta abre por cima do documento; Esc ou um clique
  na página o recolhem.
- Sem documento aberto, o centro mostra onde soltar um PDF, com Abrir arquivo e os recentes,
  e o painel da ferramenta avisa que espera um documento.
- O Início tem uma área para soltar o PDF (vale soltar em qualquer parte da aba), os atalhos
  Criar, Mesclar, Converter e Comprimir e os recentes com a miniatura da primeira página, a
  pasta, o número de páginas e quando o arquivo mudou; o "..." de cada um abre, mostra na
  pasta ou tira da lista.
- A aba Ferramentas busca também por sinônimos ("cpf" acha Redigir, "assinar" acha as duas
  ferramentas de assinatura, "word" acha Converter), filtra por categoria e ajusta o número
  de colunas à largura da janela. Um alfinete marca as que estão na coluna da direita; Enter
  abre a primeira encontrada e as setas andam entre os cartões.
- A paleta de comandos (Ctrl+K) aparece sobre a janela escurecida, com os comandos em grupos
  (Ferramentas, Exibir, Navegar, Arquivos recentes, Ações), o atalho de cada um e Tab para
  ficar só num grupo. Ela também leva aos documentos abertos e aos arquivos recentes.
- Organizar páginas mostra a grade no lugar do documento, com uma barra para girar, duplicar,
  inserir em branco e apagar, e um controle do tamanho das miniaturas. As páginas selecionadas
  levam um ✓, as giradas e as em branco um selo, e uma barra mostra onde a página arrastada
  vai entrar. O painel lista cada alteração pendente, que pode ser desfeita sozinha pelo "×";
  "Aplicar N alterações" grava tudo num passo só. Com o foco na grade, Ctrl+[ e Ctrl+] giram.

### Atualizações

- O aviso de atualização mostra a data da edição nova e a da que você usa, as principais
  novidades e "Ver notas completas"; nada é baixado antes de "Baixar e instalar". A opção de
  avisar sobre novas edições fica no próprio aviso.

### Anotações e redação

- Com Anotações aberta, uma barra flutua sobre a página com as ferramentas de marcação, as
  cores, a espessura, quantas marcações estão pendentes e "Gravar", que as grava no documento
  num passo que Ctrl+Z desfaz ("Desfazer Gravar marcações"). A página desce um pouco para a
  barra não cobri-la; lendo com Selecionar, a barra esmaece e volta quando o mouse passa nela.
  Numa janela estreita, ela fica só com ícones e a cor e a espessura vão para um botão.
- Com o foco no documento, uma tecla escolhe a ferramenta: V (selecionar), H (realce),
  U (sublinhado), S (riscado), N (nota), P (caneta), R (retângulo), O (círculo), A (seta) e
  K (carimbo). Não valem num campo de texto e podem ser trocadas em Editar > Atalhos de teclado.
- O painel de Anotações lista as marcações pendentes e os comentários gravados, com o selo
  "Pendente" ou "Gravado", a cor e o tipo de cada um, e filtra pela página atual; clicar numa
  marcação mostra a página dela. O rodapé tem "Descartar" e "Gravar N marcações".
- Ctrl+Z desfaz as anotações e as áreas de redação ainda não gravadas, uma a uma, e Ctrl+Y as
  refaz; vale também para o que foi apagado e para "Descartar". Antes, o Ctrl+Z não fazia
  nada com elas.
- Realce, sublinhado e riscado aparecem sobre o texto enquanto você arrasta, antes de soltar.
- O carimbo aparece já no clique; arrastando, ele cresce a partir do clique no tamanho que você
  quiser, sempre na proporção certa, sem distorcer o texto, e é gravado desse tamanho.

## 2026-10-24

### Atualizações

- Com a verificação ao iniciar ligada, o app consulta se há atualização no máximo uma vez por
  dia, e não mais a cada abertura. Ajuda > Verificar atualizações continua consultando na hora.

## 2026-10-23

Primeira atualização depois da beta 0.2.0-beta.1. O app ainda não tem assinatura de código: no
primeiro uso, o Windows (SmartScreen) e o macOS (Gatekeeper) avisam que o programa é de um
desenvolvedor não identificado. As versões de Linux e macOS passaram pelos testes automáticos,
mas foram menos usadas na prática que a do Windows.

### Segurança e confiabilidade

- A redação funciona em páginas giradas e recortadas, confere o resultado antes de salvar e
  nunca grava um arquivo em que o texto marcado continue legível.
- A limpeza de dados ocultos varre o documento inteiro e mostra o que foi removido.
- A verificação de assinaturas digitais diz o que a assinatura cobre e se o documento foi
  alterado depois dela.
- Anexos extraídos não podem sair da pasta escolhida nem sobrescrever arquivos.
- Um PDF com páginas gigantes ou um arquivo do Office que descompacta para gigabytes não
  derruba mais o app: a página é renderizada com menos resolução e o arquivo é recusado.
- A chave do certificado de teste da assinatura fica só na memória, sem passar pelo disco.
- Os campos de senha ficam vazios depois de usados, e a senha digitada para abrir um PDF
  sai da memória quando o documento é fechado.
- Mesclar, dividir e reorganizar páginas mantêm marcadores, metadados, anexos, camadas e
  rótulos de página; toda gravação é feita por inteiro ou não é feita.

### Uso

- Janela nova, organizada em abas: Início (abrir um PDF, as ferramentas de partida e os
  recentes), Ferramentas (todas as ferramentas, por categoria) e uma aba por documento aberto,
  cada um com o próprio desfazer. Em cada documento, a barra do topo traz abrir, salvar e
  imprimir; a coluna da esquerda, miniaturas, marcadores e anexos; a da direita, as ferramentas
  mais usadas, num painel ao lado do documento com Fechar no topo.
- O modo de exibição das páginas (página única, rolagem contínua, página dupla ou livro) fica
  guardado para a próxima vez que o app abrir.
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
- Os modos novos de Mesclar e Dividir também estão na linha de comando (`openfolio merge` e
  `openfolio split`).
- A ferramenta escolhida em Anotações fica destacada, e Mesclar, Marcadores e Campos de
  formulário cabem no painel sem barra de rolagem lateral.
- PDF para imagens grava também JPEG ou um TIFF com todas as páginas e pode converter só
  as páginas escolhidas (ou as selecionadas nas miniaturas).
- Marca d'água com imagem ou logotipo, cor do texto, nos cantos ou em mosaico, atrás do
  conteúdo, só nas páginas escolhidas e com pré-visualização.
- A numeração de páginas escolhe a posição, algarismos romanos, a fonte e o tamanho, pula
  a capa, numera só as páginas escolhidas e pode escrever os rótulos de página do
  documento.
- O OCR pode ser refeito (o texto reconhecido antes sai, em vez de ficar duplicado) e
  endireita as páginas tortas ou digitalizadas de lado no próprio documento.
- A assinatura digital mostra o certificado antes de assinar, recusa um certificado vencido,
  põe no selo o nome do certificado (e, se quiser, a imagem da sua assinatura), grava motivo,
  local e contato, usa o formato PAdES e aceita um carimbo de tempo de um servidor TSA. O
  selo tem fundo branco, legível também sobre uma capa escura.
- Marcadores: edita os que o documento já tem (renomear, reordenar e aninhar, arrastando ou
  pelos botões) e gera um sumário a partir dos títulos do documento.
- Formulários: os campos existentes podem ser renomeados, ganhar dica, virar somente leitura
  ou obrigatórios, ser removidos e ter a ordem de tabulação mudada; o campo de data pode
  aceitar só datas (opcional, usa JavaScript).
- Anotações: retângulo, círculo e seta, espessura da caneta e das formas, autor escolhido
  (fica guardado), e os comentários existentes trocam de cor, mudam de lugar e de tamanho
  arrastando no visualizador.
- Propriedades do documento: edita a descrição (título, autor...) e o XMP completo e verifica
  o PDF/A e a acessibilidade, sem sair do diálogo.
- No Windows, o instalador oferece escolher o OpenFolio como programa padrão para PDF.
- No Linux, o AppImage oferece aparecer no menu de aplicativos e na escolha do programa para
  abrir PDF (Ajuda > Mostrar no menu de aplicativos).
- Com o OpenFolio já aberto, abrir outro PDF (duplo clique, "Abrir com") abre uma aba nova na
  janela aberta, mais rápido; uma operação num documento não trava os outros.
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
