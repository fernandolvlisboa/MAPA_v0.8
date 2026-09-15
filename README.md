# 📊 MAPA — Mapeamento de Plano de Contas

Sistema em Python que lê balancetes contábeis de **qualquer formato** (XLSX,
XLS, CSV, TXT, PDF) e de **qualquer empresa** — cada um com seu próprio plano
de contas e nomenclatura — e os **mapeia para um plano de contas de referência
único e padronizado**, aprendendo com cada balancete processado. A entrega
oficial é o **Template GT** da empresa, preenchido sem intervenção manual.

> **Nome do projeto**: MAPA (Mapeamento de Plano de Contas). O nome interno
> `bp` do pacote Python é histórico e permanece no código para não quebrar
> imports — pense em MAPA como o produto e `bp` como o módulo.

---

## 🚀 Comece por aqui

```bash
uv sync
uv run python main.py
```

Isso abre a **janela** que os colaboradores usam para virar balancete em
Template GT. Arrasta os arquivos, confere cliente e exercício, clica em
*Gerar*. Ver [`PLANO_J_INTERFACE.md`](PLANO_J_INTERFACE.md).

Nada de treinar, gerar plano, revisar pendências: essas coisas ficam no menu
de terminal, atrás de `--menu`, para o analista que **cuida** do MAPA.

---

## 🎯 Objetivo real

Um contador que atende várias empresas recebe balancetes com:

- códigos de conta diferentes em cada empresa (`1.1.01` numa, `1.1.1.4.2` noutra);
- descrições diferentes para a mesma conta (`BENS NUMERÁRIOS`, `CAIXA GERAL`,
  `DISPONIBILIDADES` — todas são "Caixa");
- formatos de arquivo diferentes (Excel, PDF escaneado, CSV, TXT).

Hoje esse trabalho de "de-para" é **manual, conta a conta**. O MAPA automatiza:

```
Balancete de origem  ─►  Parser  ─►  Matching inteligente  ─►  Plano Referencial  ─►  Template GT
(qualquer formato)       (extrai)     (fuzzy + sinônimos +      (código único e         (entrega ao
                                       aprendizado)              padronizado)             cliente)
```

E, crucialmente, **aprende**: cada balancete revisado alimenta um dicionário de
variações que melhora os próximos matchings. O plano-alvo é o **Plano de Contas
Referencial da RFB — PJ em Geral** (`L100A` Balanço + `L300A` DRE, 1.109 contas,
esquema de código único). Ver [`PLANO_REFERENCIAL.md`](PLANO_REFERENCIAL.md)
para o porquê da escolha e [`PLANO_B.md`](PLANO_B.md) para a camada de
qualidade do matching.

---

O plano-alvo é o **Plano de Contas Referencial da RFB — PJ em Geral**
(`L100A` Balanço + `L300A` DRE, 1.226 contas, esquema de código único).
O vocabulário de **L100B** (Instituições Financeiras) e **L100C** (Seguradoras)
é incorporado como variações de descrição dos códigos L100A equivalentes —
ampliando o reconhecimento sem contaminar o plano-alvo. Ver
[`PLANO_REFERENCIAL.md`](PLANO_REFERENCIAL.md) para o porquê dessa escolha e
[`PLANO_B.md`](PLANO_B.md) para a camada de qualidade do matching.

---

## 🧩 Como as peças se encaixam

| Componente | Onde | O que faz |
|---|---|---|
| **Janela** | `src/bp/app/` | UI (`ui.py`), palpites e validação (`service.py`), drag-and-drop (`dnd.py`), regras de arquivo do .exe (`paths.py`) |
| **Parsers** | `src/bp/parsers/` | Lê cada formato. `ParseyCaller` (dispatcher) detecta o tipo e extrai `[{codigo, descricao, saldo}]`. Inclui OCR para PDF escaneado. |
| **Plano de contas** | `src/bp/generators/` | `PlanodeContas` carrega o JSON-alvo. `plano_referencial.py` extrai o alvo limpo do master ECF. |
| **Matcher** | `src/bp/matchers/` | `ContaMatcher`: fuzzy (RapidFuzz) + sinônimos + heurísticas + cache + desempate por IA injetável. |
| **Sinônimos** | `src/bp/utils/synonyms.py` | Expande descrições de origem para o vocabulário canônico e descarta linhas-lixo. |
| **Treinamento** | `src/bp/training/` | `AccountTrainer` processa balancetes incrementalmente e aprende variações. `review_wizard` para revisão manual. |
| **Saída GT** | `src/bp/output/` | `build_gt_output`: preenche o Template GT com os dados padronizados. |
| **Exporter diagnóstico** | `src/bp/exporters/` | Gera `.xlsx` estruturado (resumo, contas, hierarquia, não-casadas, variações). |

---

## ⚙️ Requisitos

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (gerenciador de dependências recomendado)
- Em Linux, o `tkinter` pode não vir instalado: `sudo apt install python3-tk`.
  No Windows e no macOS ele já vem com o Python.
- Para OCR de PDF escaneado (opcional): **Tesseract** (`por`) e **poppler**.
- Para gerar o `.exe` (opcional, Windows): PyInstaller já vem no extra
  `packaging` — `uv sync --extra packaging`.

---

## ▶️ Bancada do analista: o menu de terminal

`main.py --menu` abre três opções — treinar, padronizar, revisar. Existe para
o dono do MAPA, não para o colaborador; por isso o menu não aparece na janela.

```bash
uv run python main.py --menu
```

O passo a passo detalhado abaixo mostra cada etapa isolada; o menu só as
orquestra.

---

## 🚀 Passo a passo do analista

> Todos os comandos assumem a raiz do projeto e o `uv`.

### Passo 0 — Instalar dependências

```bash
uv sync                                  # núcleo (166 MB) — roda tudo do fluxo abaixo
uv sync --extra ocr --extra curation     # + OCR de escaneados e geração do master
uv sync --extra packaging                # + PyInstaller (para gerar o .exe)
```

O núcleo cobre XLSX/XLS/CSV/TXT e **PDF nativo**. Os extras são só para a
estação de curadoria — ver [`DEPENDENCIAS.md`](DEPENDENCIAS.md).

Confere se está tudo no lugar rodando a suíte de testes:

```bash
uv run pytest -q
```

### Passo 1 — (Opcional) Gerar o plano master a partir do Excel

O repositório **já inclui** `data/plano_contas.json`. Só refaça se mudar a
planilha-fonte `src/plano_master.xlsx`:

```bash
uv run python -m src.bp.generators.plano_contas_generator \
    -i src/plano_master.xlsx -o data/plano_contas.json
```

### Passo 2 — Gerar o Plano Referencial (alvo limpo)

Extrai do master ECF apenas o plano-alvo consistente (`L100A` + `L300A`). Gera
`data/plano_referencial.json`:

```bash
uv run python -m src.bp.generators.plano_referencial
```

Saída esperada: `1.226 contas` (raízes `1` Ativo, `2` Passivo/PL, `3` DRE).

### Passo 3 — Treinar (aprender com balancetes reais)

1. Coloque balancetes na pasta de treino:

   ```bash
   cp meus_balancetes/*.xlsx data/samples/
   ```

   Formatos aceitos: `.xlsx`, `.xls`, `.csv`, `.txt`, `.pdf`.

2. Rode o treinamento incremental (processa **apenas arquivos novos**):

   ```bash
   uv run python src/bp/training/train.py
   ```

3. Leia o relatório gerado:

   ```
   output/training_report.md
   ```

O treino filtra contas analíticas (fornecedor específico, c/c bancária, CNPJ),
descarta linhas-lixo e grava o que aprendeu em
`src/bp/training/account_variations.json` — que o matcher passa a usar sozinho.

### Passo 4 — Revisar os casos que precisam de decisão humana

O relatório aponta contas "precisam de revisão". Use o assistente:

```bash
uv run python -m src.bp.training.review_wizard --all --list        # lista
uv run python -m src.bp.training.review_wizard --all --limit 10    # revisa
```

| Tecla | Ação |
|-------|------|
| `s` | Buscar candidatos por descrição (fuzzy) |
| `h` | Navegar pela hierarquia (Ativo → Circulante → …) |
| `c` | Informar o código manualmente |
| `i` | Ignorar permanentemente |
| `k` | Pular nesta sessão |
| `q` | Sair |

Depois de revisar, **rode o Passo 3 de novo** para consolidar o aprendizado.

### Passo 5 — Gerar a entrega no Template GT (via API)

A janela faz isso — este é o modo programático:
Esta é a **saída oficial**: o template da empresa povoado com o balancete
padronizado (ver [`PLANO_H.md`](PLANO_H.md) e [`docs/TEMPLATE_GT_BP.md`](docs/TEMPLATE_GT_BP.md)).

**Um exercício:**

```bash
uv run python -c "
from src.bp.output.build_gt_output import build_gt_output
build_gt_output(
    'data/samples/Balancete Real Life.xlsx',
    'output/gt/Cliente_2024.xlsx',
    ano_base=2024, nome_cliente='Cliente Ltda', data_base='2024-12-31')
"
```

**Série histórica — um arquivo por ano** (é assim que balancetes existem: cada
arquivo cobre um período, as colunas `Saldo Anterior/Débito/Crédito/Saldo Atual`
são movimentação do mesmo exercício, não anos distintos):

```bash
uv run python -c "
from src.bp.output.build_gt_output import build_gt_output, FonteBalancete
build_gt_output([
    FonteBalancete('balancete_2022.xlsx', 2022),
    FonteBalancete('balancete_2023.xlsx', 2023),
    FonteBalancete('balancete_2024.xlsx', 2024),
], 'output/gt/Cliente.xlsx', nome_cliente='Cliente Ltda')
"
```

Os anos **não** são fixos em 2021-2025: o template comporta cinco exercícios
quaisquer, e os rótulos são reescritos sozinhos. Abas: **BP_GT / DRE_GT** (a
entrega ao cliente, preenchidas pelas fórmulas SUMIFS do template) + **Sumário
/ Contas Tratadas / Contas Não Identificadas** (uso interno).

### Passo 6 — Gerar o `.exe`

Em máquina Windows, com o venv sincronizado (extra `packaging`):

```powershell
uv run python build.py
```bash
uv run python -m auxil.export_xlsx \
    -i "data/samples/Balancete Real Life.xlsx" \
    -o "output/exports/Real_Life_export.xlsx" \
    --plano data/plano_referencial.json
```

O script:

1. compila `dist\MAPA.exe` a partir de `bp.spec` (allowlist explícita);
2. roda `tests/test_build_seguranca.py` sobre o `.exe` gerado — falha se
   qualquer arquivo de cliente aparecer dentro;
3. imprime o tamanho final e o caminho.

Ver [`PLANO_K_EMPACOTAMENTO.md`](PLANO_K_EMPACOTAMENTO.md) para o que entra,
o que não entra e por quê.

---

## 🚨 Passo 7 — Compilar e distribuir o `.exe`

O `MAPA.exe` sai em `dist/MAPA.exe`, ~55 MB, **onefile**:

- Roda por duplo-clique. Sem instalador.
- **Não precisa de admin** — descompacta em `%TEMP%` do usuário na 1ª execução.
- Nada é gravado em `Program Files`, nada mexe no registry.
- SmartScreen pode alertar na primeira vez (executável não assinado). *Mais informações → Executar assim mesmo*.
- **Abra com duplo clique normal.** O Windows bloqueia arrastar-e-soltar em janela aberta como administrador (UIPI) — e falha calado.

### O `.exe` não entra no repositório

São 55 MB por build. Commitado, o git guarda **todos** para sempre e o histórico não encolhe depois. `dist/` está no `.gitignore` e é assim que fica.

A distribuição é por **GitHub Release**: até 2 GB por arquivo, fora do histórico, com link estável para circular.

### Publicar uma versão

Duas linhas, e o resto é automático:

```bash
git tag v0.8.1
git push origin v0.8.1
```

O workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) acorda sozinho, sobe uma máquina Windows e faz, nesta ordem:

1. `uv sync --extra packaging`
2. `uv run pytest -q` — a suíte inteira
3. `uv run python build.py` — compila, **audita** e **autotesta** o binário
4. publica a Release com o `MAPA.exe` anexado

Leva **5 a 8 minutos**. Acompanhe na aba **Actions**; quando terminar, o arquivo está em **Releases**, e o link para circular é `https://github.com/<owner>/<repo>/releases/latest`.

**Se qualquer passo falhar, não há Release.** Foi exatamente assim que um binário com o pandas quebrado chegou aos usuários — ver [`REVISAO_QUALIDADE.md`](REVISAO_QUALIDADE.md) §24. Os relatórios do build ficam anexados à execução do Actions mesmo quando ela falha.

**Numeração das tags:** `v<maior>.<menor>.<correção>` — `v0.8.1` para correção, `v0.9.0` quando muda o comportamento. A tag precisa começar com `v`, senão o workflow não dispara.

**Refazer uma versão** (algo saiu errado e você quer reaproveitar o número):

```bash
git tag -d v0.8.1 && git push origin :refs/tags/v0.8.1   # apaga local e remoto
git tag v0.8.1 && git push origin v0.8.1                 # recria
```

Apague também a Release antiga pela interface do GitHub, senão ficam duas.

**Testar o workflow sem criar tag:** aba *Actions* → *Release do MAPA.exe* → *Run workflow*. Ele compila e autotesta, e não publica nada.

### Publicar à mão (sem esperar o CI)

Quando você já compilou na sua máquina e quer subir agora — precisa do [`gh`](https://cli.github.com):

```bash
uv run python build.py
gh release create v0.8.1 dist/MAPA.exe --generate-notes
```

O `build.py` só devolve `.exe` que passou na auditoria e no autoteste, então o que sobe por aqui tem a mesma garantia do CI.

### O que o build confere antes de entregar

| Passo | O que prova | Por que existe |
|---|---|---|
| `pytest -q` | o código faz o que promete | a suíte de sempre |
| auditoria do bundle | nenhum dado de cliente dentro; template, plano e `tkdnd` presentes | §23 — o `.exe` saiu sem a biblioteca do arrastar-e-soltar |
| `MAPA.exe --autoteste` | **o binário roda o pipeline completo** | §24 — o `.exe` saiu com o pandas quebrado |

O autoteste monta um balancete sintético, chama o motor de verdade sobre o template embarcado e confere que a entrega saiu. É a diferença entre auditar o *conteúdo* do artefato e provar que ele *funciona*. Ver [`PLANO_K_EMPACOTAMENTO.md`](PLANO_K_EMPACOTAMENTO.md).

---

## 🧠 Ordem lógica, resumida

```
uv sync                                   # 0. instalar
uv run python main.py                     # colaborador — janela
uv run python main.py --menu              # analista — menu
uv run python build.py                    # gerar o .exe (Windows)
```

---

## 🐍 Uso programático (API)

```python
from src.bp.generators.plano_contas import PlanodeContas
from src.bp.matchers import ContaMatcher

plano = PlanodeContas("data/plano_referencial.json")
matcher = ContaMatcher(plano, cache_path="data/match_cache.json")

r = matcher.match("BENS NUMERARIOS")
if r.decision:
    print(r.decision.codigo, r.decision.descricao, r.decision.score)
```

Desempate por IA (injetável, desacoplado do provedor):

```python
def meu_classificador(descricao, candidatos, contexto):
    ...  # chame um LLM aqui, devolva um MatchDecision ou None

matcher = ContaMatcher(plano, use_ai=True, ai_classifier=meu_classificador)
```

Treino programático:

```python
from src.bp.training.trainer import AccountTrainer

t = AccountTrainer()                 # usa data/plano_referencial.json por padrão
resultado = t.train()
print(f"match rate: {resultado['match_rate']:.1f}%")
t.export_report("output/training_report.md")
```

---

## 📂 Arquivos gerados pelo treino

| Arquivo | Conteúdo |
|---------|----------|
| `src/bp/training/account_variations.json` | Variações de descrição aprendidas — ~440 códigos (**usado pelo matcher**) |
| `src/bp/training/learned_patterns.json` | Sinônimos/abreviações identificados |
| `src/bp/training/training_cache.json` | Cache de matching do treino |
| `src/bp/training/processed_files.json` | Arquivos já processados (incremental) |
| `src/bp/training/training_stats.json` | Estatísticas acumuladas por sessão |
| `src/bp/training/training_ignore.json` | Descrições marcadas como ruído permanente |
| `output/training_report.md` | Relatório legível do último treino |

### O que é versionado e o que não é

**Versionado (é conhecimento):** `account_variations.json` e os demais JSON de
treino em `src/bp/training/`. É o que o sistema aprendeu; perder isso é perder
trabalho de curadoria.

**Não versionado (é saída ou cache):** `data/match_cache.json`, `output/*.xlsx`
e tudo em `output/exports/` e `output/gt/`. São deriváveis, mudam a cada
execução, e as planilhas ainda carregam dados individuais de cliente — que a
política de segurança do projeto já manda não versionar.

Esses arquivos **estavam rastreados por acidente**, e o efeito era o
`git status` aparecer sujo depois de qualquer execução, atrapalhando todo
`pull`. Se você tem um clone antigo e o `pull` reclamar deles:

```bash
git reset                 # tira do stage o que foi gerado
git checkout -- .         # descarta as modificações locais (são deriváveis)
git pull
```

O cache é recriado sozinho conforme você usa; nenhuma decisão manual é perdida
(a geração da entrega não escreve nele — usa cache efêmero por padrão).

---

## 🗂️ Estrutura do projeto

```
MAPA/
├── main.py                            # ← ponto de entrada (janela + --menu)
├── app.py                             # ← alvo do PyInstaller (mesma janela)
├── build.py                           # ← constrói e valida o .exe
├── bp.spec                            # ← spec do PyInstaller (allowlist)
├── src/
│   ├── plano_master.xlsx              # Fonte Excel do plano master (ECF)
│   └── bp/                            # (nome histórico — o pacote Python)
│       ├── app/                       # A janela do usuário final (Plano J)
│       │   ├── paths.py               # onde ler / onde escrever (regra do .exe)
│       │   ├── service.py             # ponte GUI → núcleo (palpites, validação)
│       │   ├── dnd.py                 # arrastar-e-soltar, com degradação
│       │   └── ui.py                  # a janela
│       ├── parsers/                   # XLSX/XLS/CSV/TXT/PDF + dispatcher
│       ├── generators/                # PlanodeContas + geradores do plano
│       ├── matchers/                  # ContaMatcher + MatchCache
│       ├── output/                    # build_gt_output → Template GT
│       ├── exporters/                 # xlsx_exporter (diagnóstico)
│       └── training/                  # trainer, review_wizard, DFS_Exemple/
│       ├── utils/
│       │   ├── normalizer.py
│       │   └── synonyms.py            # expansão de sinônimos + guarda anti-lixo
│       ├── exporters/                 # xlsx_exporter
│       ├── validators/                # schema de exportação
│       └── training/
│           ├── trainer.py             # AccountTrainer
│           ├── train.py               # script de treino
│           ├── review_wizard.py       # revisão interativa
│           └── data/samples/ (fora da árvore)             # ← coloque balancetes aqui
├── data/
│   ├── plano_contas.json              # master ECF (7.741 contas, todos os blocos)
│   ├── plano_referencial.json         # alvo limpo (1.226 contas) ← usado no matching
│   ├── accounting_synonyms.json       # dicionário de sinônimos contábeis
│   └── match_cache.json
├── auxil/
│   ├── export_xlsx.py                 # CLI de exportação
│   └── ...                            # scripts de apoio
├── app.py                             # ← ponto de entrada da janela (vira o .exe)
├── tests/                             # suíte pytest
├── output/                            # saídas geradas
├── PLANO_REFERENCIAL.md               # Plano A: por que o alvo referencial
├── PLANO_B.md                         # Plano B: qualidade de matching
└── README.md                          # este arquivo
```

---

## 🔎 Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| Janela não abre; erro de `tkinter` | Linux sem Tk instalado | `sudo apt install python3-tk` |
| Arrastar não funciona na janela | driver `tkdnd` ausente | use o botão *Clique para escolher* — o programa funciona igual |
| Balanço não fecha na tela de resultado | conta com saldo ilegível ou classe errada | abrir a planilha e conferir *Contas Não Identificadas* |
| `Plano de contas não encontrado` | falta `data/plano_referencial.json` | rode o **Passo 2** |
| Match rate baixo | poucos exemplos ou sem revisão | mais **Passo 3** + revisão no **Passo 4** |
| `Nenhum arquivo novo encontrado` | balancetes já processados | adicione novos em `data/samples/` ou apague `processed_files.json` para reprocessar |
| Match rate baixo | poucos exemplos / sem revisão | rode mais o **Passo 3** e revise no **Passo 4** |
| Erro ao parsear | encoding ou colunas faltando | garanta colunas `codigo`, `descricao`, `saldo`; UTF-8 |
| PDF escaneado sem texto | falta OCR | instale Tesseract (`por`) e poppler |
| `.exe` não abre | Windows antigo (< 10) ou antivírus | testar em `C:\Users\<usuario>\Desktop`; se antivírus, exceção pontual |

---

## 📌 Estado atual

- ✅ Janela do usuário final — **Plano J**
- ✅ Empacotamento em `.exe` com allowlist + teste anti-vazamento — **Plano K**
- ✅ Saída no **Template GT** da empresa (entrega ao cliente) — **Plano H**
- ✅ Anos flexíveis + série histórica multi-arquivo — **Plano I**
- ✅ Parsers (XLSX/XLS/CSV/TXT/PDF nativo), dispatcher, exporter
  - `.xls` legado lê em Linux/CI sem LibreOffice (estratégia `xlrd`) — ver
    [`REVISAO_QUALIDADE.md`](REVISAO_QUALIDADE.md) §30
  - detecção de coluna por **conteúdo** (código plano, saldo com rótulo
    desalinhado, cabeçalho em inglês) — §31/§32
- ✅ Plano referencial (alvo único e consistente) — **Plano A**
- ✅ Matching com sinônimos, guarda anti-lixo e desempate — **Plano B**
- ✅ Desambiguação por classe contábil Ativo/Passivo/Resultado — **Plano C**
- ✅ Suporte multilíngue PT/EN/ES (dicionário trilíngue) — **Plano D**
- ✅ Enriquecimento do plano-alvo com linhas de balancete ausentes — **Plano E**
- ✅ Extração de balancetes em PDF nativo (2-col e coluna única) — **Plano F**
- ✅ Classificador LLM + enriquecimento guiado por dados (47% de match) — **Plano G**
- ✅ Saída no **Template GT** da empresa (entrega ao cliente) — **Plano H**
- ✅ Anos flexíveis + série histórica multi-arquivo — **Plano I**
- ✅ Janela do usuário final (arrastar-e-soltar → Template GT) — **Plano J**
- ✅ Vocabulário L100B/C (Financeiras e Seguradoras) incorporado como variações
- ✅ Treino incremental + review wizard — **85% de auto-aceite** sobre 9,6k
  contas *tentadas* (denominador honesto: exclui totais/linhas-lixo) nos 12
  balancetes de exemplo
- ✅ **Veredito ao usuário** no Sumário da entrega — *PRONTA / COM RESSALVAS /
  NÃO FOI POSSÍVEL* —, para qualquer senioridade (sócio ou trainee) saber pelo
  RESULTADO o que fazer com o arquivo; entrega vazia nunca sai marcada "OK" (§32)
- ✅ Seleção de aba pergunta ao usuário só quando há ambiguidade real (arquivo
  não é balancete puro, ou traz dois-ou-mais balancetes); um balancete claro
  entre abas de apoio segue sozinho
- ✅ **Uma entrega por entidade**: arquivo com holding + controlada (2+ balanços
  em abas) gera um Template GT por empresa, em vez de somá-las numa só planilha
  (§33/§34)
- ✅ **Rastreabilidade** (`src/bp/versao.py`): versão + impressão digital
  (contagem/hash de plano, vocabulário e mapa do template) no cabeçalho da
  janela, no Sumário e no **nome do arquivo de saída** — responde "o que mudou?"
  entre duas execuções sem abrir a planilha (mesclado da linha pública v0.8)
- ✅ Robustez de console no Windows (cp1252) e caixa de avisos rolável na tela —
  os botões de ação nunca são empurrados para fora quando os avisos crescem
- ✅ Reconciliação por dígito-raiz (`emitido_por_raiz`/`residuo_da_equacao`):
  não confunde Custos (3) com Receitas (4) num plano de quatro classes
- ✅ Núcleo enxuto: 825 MB → 166 MB (ver [`DEPENDENCIAS.md`](DEPENDENCIAS.md))
- ✅ Suíte de testes higienizada; integração com corpus pula quando os
  balancetes privados não estão presentes
- 🔜 OCR para PDFs escaneados (requer Tesseract) — pipeline existe, falta ligar

**Para a próxima rodada:** [`GUIA_PROXIMOS_TREINAMENTOS.md`](GUIA_PROXIMOS_TREINAMENTOS.md)
— o caminho passo a passo.

Documentos de arquitetura: [`ARQUITETURA.md`](ARQUITETURA.md),
[`PLANO_REFERENCIAL.md`](PLANO_REFERENCIAL.md) (A),
[`PLANO_B.md`](PLANO_B.md) (B), [`PLANO_C.md`](PLANO_C.md) (C),
[`PLANO_D.md`](PLANO_D.md) (D), [`PLANO_E.md`](PLANO_E.md) (E),
[`PLANO_F.md`](PLANO_F.md) (F), [`PLANO_G.md`](PLANO_G.md) (G),
[`PLANO_H.md`](PLANO_H.md) (H), [`PLANO_I.md`](PLANO_I.md) (I),
[`PLANO_J_INTERFACE.md`](PLANO_J_INTERFACE.md) (J — a janela do usuário final),
[`PLANO_K_EMPACOTAMENTO.md`](PLANO_K_EMPACOTAMENTO.md) (K — build e `.exe`).

---
