# Plano J — A interface do usuário final

> Estado: **implementado** em `src/bp/app/`, aberto por `app.py`.
> Público: o colaborador da empresa que só quer entregar a planilha.

---

## 1. O problema

Todo o BP hoje é operado por quem sabe o que é `uv run python -m ...`. O público
real não é esse. O colega que recebe um balancete de cliente por e-mail precisa,
sem instalar nada e sem entender nada de Python:

1. dizer **qual arquivo** é o balancete;
2. dizer **de que exercício** ele é e **de que cliente**;
3. receber o **Template GT preenchido**;
4. saber, olhando, **se dá para entregar** — ou o que falta revisar.

Só isso. Treinar o matcher, revisar variações, gerar o plano referencial: nada
disso é tarefa dele. Continua no `main.py`, que é a bancada do analista.

**A pergunta que decide a interface inteira** é: depois de gerar, a pessoa sabe
se pode mandar o arquivo para o cliente? Se a tela não responde isso, ela falhou
mesmo tendo gerado o arquivo certo.

---

## 2. A forma: uma janela, uma tarefa, três estados

Nada de menu, abas ou assistente de vários passos. Uma tarefa só cabe numa tela.

```
┌──────────────────────────────────────────────────────────────┐
│ BP    Padronização de balancetes para o Template GT          │  ← roxo #4F2D7F
├──────────────────────────────────────────────────────────────┤
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐  │
│                          [ícone]                             │
│  │            Arraste os balancetes para cá              │   │
│               ou clique para procurar no computador          │
│  │          xlsx · xls · csv · txt · pdf                 │   │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │
│                                                              │
│  ┌────────────────────────────────────────── Exercício ───┐  │
│  │ 2 arquivo(s)                                           │  │
│  │ Balancete 072022 122022 - RBM.xlsx        [ 2022 ]  ×  │  │
│  │ Balancete 2024 - RBM.xlsx                 [ 2024 ]  ×  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Cliente                     Valores no balancete            │
│  [ RBM                   ]   (•) Em reais (o BP converte)    │
│  vai impresso na capa        ( ) Já estão em milhares        │
│                                                              │
│  Salvar em                                                   │
│  C:\Users\...\Documentos\BP                    [ Alterar… ]  │
│                                                              │
│  «o que falta preencher»                 [ Gerar planilha ]  │
└──────────────────────────────────────────────────────────────┘
```

**Estado 2 — processando.** A mesma janela mostra cliente + exercícios, uma
barra e a frase do que está acontecendo agora (*"Lendo e classificando o
balancete de 2022 (1 de 2)"*). O trabalho roda em thread; a janela nunca
congela, nunca vira "não está respondendo".

**Estado 3 — resultado.** É a tela que responde à pergunta da §1:

```
!  Gerada — confira os avisos antes de entregar
   RBM_2022-2024.xlsx
   C:\Users\...\Documentos\BP

   663          321            324           50%             NÃO
   Contas lidas Identificadas  Para revisar  Aproveitamento  Balanço fecha

   ┌ 2022: O balanço não fechou: Ativo e Passivo+PL ficaram diferentes. ─┐
   │ 2024: Algumas contas tinham saldo que não deu para ler...          │
   └────────────────────────────────────────────────────────────────────┘

   Contas que o BP não soube classificar (324)
   ┌──────────────────────────────────────┬───────────┬──────────┐
   │ SICOOB - UNISUDESTE - RBM 62540-0    │   2022    │     9,81 │
   └──────────────────────────────────────┴───────────┴──────────┘

   [Padronizar outro]            [Abrir pasta]  [ Abrir planilha ]
```

Verde só quando **não há aviso nenhum e o balanço fecha**. Qualquer outra coisa
é amarelo com o motivo escrito. Um "✓ pronto!" sobre um balanço que não fecha
seria a pior coisa que este programa poderia fazer.

---

## 3. Decisões e o porquê

### 3.1 Arrastar-e-soltar **não** precisa de pasta temporária

Era a dúvida que originou este plano. Não precisa: quando um arquivo é
arrastado do Explorer, o sistema operacional entrega o **caminho completo**. O
BP abre o original onde ele está e nunca o modifica — nada é copiado, nada
precisa ser limpo depois.

A única exceção real é arrastar um anexo **direto do Outlook** (ou de dentro de
um `.zip`): aí não existe arquivo no disco, o que chega é um fluxo de bytes sem
caminho. Copiar isso para uma pasta temporária às escondidas resolveria o
arrasto e criaria um problema pior — o usuário passaria a padronizar um arquivo
que não existe mais em lugar nenhum, sem saber. A tela diz a verdade:
*"salve o anexo numa pasta primeiro e arraste de lá"*.

O Tk que vem com o Python não aceita arrasto externo — isso é a extensão
`tkdnd`. `src/bp/app/dnd.py` tenta `tkinterdnd2`, depois `windnd`, e **degrada
sozinho**: sem backend, a área tracejada continua existindo como um botão
grande que abre o seletor de arquivos. O programa nunca fica sem caminho.

### 3.2 Pedir o caminho da pasta e listar os arquivos: **descartado**

Era a ideia original. Ela troca um gesto (arrastar) por: digitar/colar caminho →
esperar listar → escolher da lista. O seletor de arquivos do próprio Windows já
faz isso melhor, com busca, histórico e favoritos. Ficaram os dois caminhos que
o usuário já conhece: **arrastar** ou **clicar e procurar**. Arrastar a *pasta*
funciona e traz os arquivos legíveis de dentro dela.

### 3.3 Janela nativa, não navegador

Um servidor local + navegador dá arrasto de graça e é bonito. Em máquina
corporativa também dá: alerta de firewall na primeira execução, porta ocupada,
antivírus curioso — cada um deles é um chamado para você. `tkinter` vem com o
Python, não abre porta, não pede permissão e o PyInstaller já sabe empacotar.
Custa aparência; economiza suporte. A aparência foi comprada de volta com a
paleta do próprio template (roxo `#4F2D7F`, teal `#00A7B5`, fundo `#F2F0EE` —
lidos de `Template_GT_BP_Padrao_v3.xlsx`), então o app parece a mesma coisa que
a planilha que ele entrega.

### 3.4 O programa adivinha o que já está escrito

Ninguém deveria digitar o que o nome do arquivo já diz. `service.ano_do_nome()`
cobre os formatos que existem no corpus real — `Balancete 2024`, `202404_2024`,
`1222024` (MMAAAA colado), `2012-12`, `Balanc dez 25`, `Dez24`, `3T25` — e
`cliente_do_nome()` tira datas, números e as palavras que descrevem o documento
("balancete", "consolidado", "parecer") até sobrar o cliente: *Balancete 072022
122022 - RBM* → **RBM**.

Tudo isso é **sugestão preenchida**, editável em um clique. E quando não sobra
nada confiável, o campo fica **vazio de propósito**: chutar "Balancete 042025 em
excel" como nome de cliente é pior do que não chutar — sairia impresso na capa
da entrega. O botão só liga quando o campo tem conteúdo.

### 3.5 O campo perigoso é a escala

`escala=1000` divide os valores porque o template diz "Em milhares de reais". Um
erro aqui produz uma entrega mil vezes errada que *parece* certa. Por isso a
pergunta não é "está em milhares? (s/N)" como no terminal, e sim duas opções
escritas por extenso, com o padrão no caso comum: **"Em reais (o BP converte
para milhares)"**.

> Melhoria já identificada para a v2: mostrar o maior saldo lido e o que ele
> vira no template (*"12.345.678,00 → 12.346"*) antes de gerar. É a checagem que
> torna o erro impossível de passar batido.

### 3.6 Nunca sobrescrever

Gerar duas vezes cria `RBM_2022-2024 (2).xlsx`. Sobrescrever em silêncio a
entrega anterior — possivelmente já revisada à mão — é a forma mais barata de
perder trabalho. `caminho_sem_colisao()` é testado.

### 3.7 Onde o programa lê e onde escreve

Esta é a diferença que o executável impõe, e é a fonte mais comum de bug em app
empacotado. `src/bp/app/paths.py` é a **única** fonte dessa distinção:

| | Da fonte | Congelado (.exe) |
|---|---|---|
| **Lê** (`resource_dir`) | raiz do repositório | `sys._MEIPASS`, pasta temporária |
| **Escreve** (`user_data_dir`) | `~/.local/share/BP` | `%LOCALAPPDATA%\BP` |
| **Entrega** (`default_output_dir`) | `~/Documentos/BP` | `Documentos\BP` do usuário |

"Documentos" é perguntado ao Windows via `SHGetFolderPathW`, não montado como
`~/Documents` — é o que faz o app achar a pasta certa quando ela está em
português, redirecionada para o OneDrive ou para um drive de rede. Um teste
trava a regra: nada gravável pode morar dentro de `resource_dir()`.

### 3.8 Erro vira frase

O usuário final não vê stacktrace. `service.gerar()` nunca levanta exceção: toda
falha vira `Resultado(ok=False, erro="...")`. Planilha aberta no Excel vira
*"feche o arquivo e tente de novo"*; e os avisos do núcleo (que falam com o
analista) são traduzidos para a linguagem da tela e **de-duplicados** — o aviso
de desequilíbrio cita o saldo ilegível como causa, e sem cuidado os dois viravam
o mesmo alerta repetido.

---

## 4. O que esta interface **não** faz

| Fora do escopo | Onde continua |
|---|---|
| Treinar com balancetes novos | `main.py` → opção 1 |
| Revisar pendências e ensinar o matcher | `main.py` → opção 3 (`review_wizard`) |
| Gerar plano master / referencial | passos 1 e 2 do README |
| OCR de PDF escaneado | estação de curadoria (extra `ocr`) |

São públicos diferentes. Misturar as duas coisas numa tela só transformaria a
ferramenta de entrega numa ferramenta de configuração.

---

## 5. Próximos passos

**v2 — revisar sem sair do app.** As contas não identificadas já aparecem na
tela de resultado, mas só para leitura. O passo seguinte é deixar classificar ali
mesmo (três sugestões do matcher + busca), gravar em `account_variations.json` e
oferecer *"Gerar de novo com as correções"*. É o que faz o BP melhorar com o uso
de **todo mundo**, não só com o seu. Junto vem a pergunta de quem guarda esse
aprendizado — hoje ele é local; um `variations.json` numa pasta de rede lida na
abertura resolveria, com você fazendo a curadoria do que entra.

**v2 — conferência de escala antes de gerar** (§3.5).

**`main.py` é a vitrine.** Rodar `uv run python main.py` (sem argumento) abre esta janela — o alvo é apresentar o programa pronto, sem passo intermediário. `--menu` guarda o antigo menu de terminal para a bancada do analista. Nenhum outro arquivo conhece a bandeira: os testes e o resto do projeto continuam chamando as mesmas funções (`AccountTrainer`, `build_gt_output`, `review_wizard`).

**Empacotamento (Plano K).** `app.py` é o ponto de entrada do PyInstaller. Os
recursos (`data/plano_referencial.json`, `templates/*.xlsx`,
`account_variations.json`) precisam entrar como `--add-data`, e o `tkdnd` do
`tkinterdnd2` também. Estimativa de `DEPENDENCIAS.md`: 80–120 MB.

---

## 6. Pendências honestas

- **O arrasto não foi verificado em Windows.** O ambiente onde isto foi
  desenvolvido não tem como testar o `tkdnd` (ele quebra sob o servidor X
  headless usado aqui). O caminho de degradação — clicar e procurar — foi
  testado e funciona; o arrasto precisa de um teste na máquina real. Se falhar,
  `BP_SEM_DND=1` desliga a tentativa, e trocar de backend é um arquivo.
- **50% de aproveitamento no corpus real** (663 contas lidas, 324 sem
  classificação num par de balancetes de teste). A interface expõe esse número
  em vez de escondê-lo, o que é o certo — mas é o número que o Plano G precisa
  continuar subindo.
