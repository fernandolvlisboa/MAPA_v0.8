# 🧭 Guia dos Próximos Treinamentos — o caminho a seguir

Runbook prático para rodar uma nova rodada de treinamento e chegar a um **output
decente** no Template GT. Complementa o [`GUIA_TREINAMENTO.md`](GUIA_TREINAMENTO.md)
(que detalha o sistema) com **o caminho passo a passo** e as **lições** desta
rodada. Feito para qualquer nível de senioridade — de sócio a trainee.

> **Regra que resume tudo:** o entregável é **o arquivo de saída**. O match rate
> importa, mas quem manda é a entrega. Um Sumário que abre com **✅ ENTREGA
> PRONTA** vale mais que qualquer porcentagem.

---

## 0. Antes de começar (uma vez)

```bash
uv sync                       # instala o núcleo
uv run pytest -q -m "not integration"   # sanidade (testes de corpus pulam sem os balancetes)
```

- **Onde os balancetes ficam:** `data/samples/` é o **único** lugar onde o MAPA
  procura. Formatos aceitos: `.xlsx`, `.xls`, `.csv`, `.txt`, `.pdf`.
- **Dado privado:** os balancetes carregam **valores** — nunca versione. O
  `.gitignore` já exclui `data/samples/**` (só o `README.md` fica). Número de
  conta, nome e CNPJ isolados não são o problema; **valor é**.
- **Guardar os balancetes fora do repo:** aponte `MAPA_SAMPLES_DIR` para a pasta
  deles (pen drive, Dropbox, rede) e o MAPA lê de lá.

---

## 1. O caminho, do balancete à entrega

```
 (1) adiciona balancetes   →   (2) treina   →   (3) revisa pendências
        data/samples/           train.py          review_wizard
                                                        │
 (5) entrega no Template GT  ←   (4) confere o resultado (o veredito)
        build_gt_output              Sumário: PRONTA / RESSALVAS / VAZIO
```

### Passo 1 — Adicionar balancetes

Copie os arquivos para `data/samples/`. O treino é **incremental**: só processa
arquivos **novos** (os já vistos ficam em `processed_files.json`). Para
reprocessar tudo, zere esse arquivo.

### Passo 2 — Treinar

```bash
uv run python -m src.bp.training.train
```

Lê o relatório em `output/training_report.md`. **Como ler o match rate:**

> **Match rate = casados ÷ contas _tentadas_**, não ÷ sintéticas. "Tentadas" são
> as contas de fato submetidas ao matcher (sintéticas **menos** linhas-lixo,
> totais e ignoradas). Dividir pelo total sintético mistura "não casou" com "nem
> era conta" e afunda a taxa sem motivo. Nesta rodada: **85%** sobre 9,6k contas.

Um match rate mais baixo **não é falha por si só**: contas de **seguradora**
(L100C), **banco** (L100B) e **DF em outra língua** ficam, corretamente, em
revisão — o plano-alvo é o **L100A (PJ em geral)** e forçar uma conta de
resseguro onde ela não existe seria erro contábil, não acerto.

### Passo 3 — Revisar pendências (o treinamento manual)

O relatório aponta contas "precisam de revisão". Ensine o sistema:

```bash
uv run python -m src.bp.training.review_wizard --all --list     # lista
uv run python -m src.bp.training.review_wizard --all --limit 10 # revisa
```

Teclas: `s` buscar · `h` hierarquia · `c` código manual · `i` ignorar sempre ·
`k` pular · `q` sair. Cada decisão vira variação aprendida e melhora o próximo
matching. Depois de revisar, **rode o Passo 2 de novo** para consolidar.

**Curadoria por sinônimos (alavanca maior):** um sinônimo generaliza para muitas
descrições de uma vez. Edite `data/accounting_synonyms.json` **com juízo
contábil** — só mapeamentos **inequívocos em qualquer contexto** (ex.: `adto →
adiantamento`, `mats → materiais`). Nunca mapeie algo ambíguo (um sinônimo
errado casa com confiança e **estraga o balanço**). Após editar, re-treine e
compare o match rate.

### Passo 4 — Conferir o resultado (o veredito)

Toda entrega abre o Sumário com uma linha **SITUAÇÃO**:

| Selo | Significa | O que fazer |
|---|---|---|
| ✅ **ENTREGA PRONTA** | os totais batem com o balancete | enviar BP_GT e DRE_GT ao cliente |
| ⚠️ **ENTREGA COM RESSALVAS** | template preenchido, totais não batem | ler "POR QUE NÃO FECHA" e a fila "Contas Não Identificadas" |
| ⛔ **NÃO FOI POSSÍVEL MONTAR** | nenhuma conta reconhecida | conferir se é balancete e em qual aba está o balanço |

**Invariante:** entrega vazia **nunca** sai marcada como pronta. Se aparecer
⛔, o problema é de leitura (aba errada, arquivo que não é balancete), não do
cliente.

### Passo 5 — Gerar a entrega

Pela **janela** (`uv run python main.py`) é o caminho do dia a dia: arrasta,
confere cliente/exercício, escolhe a pasta, clica *Gerar*. Programaticamente:

```python
from src.bp.output.build_gt_output import build_gt_output
build_gt_output("data/samples/Balancete X.xlsx", "output/gt/Cliente.xlsx",
                ano_base=2024, nome_cliente="Cliente Ltda")
```

---

## 2. Seleção de aba: a regra de ouro

> **Perguntar para gerar certo vale mais que chutar errado.**

O MAPA **pergunta** ao usuário qual aba usar **só quando há ambiguidade real**:

- o arquivo **não é balancete puro** (a empresa já consolidou) → *"em qual aba
  está o balanço?"*; ou
- ele traz **dois-ou-mais balancetes** → *"quais exercícios usar?"*.

Um balancete claro cercado de abas de apoio (`Parâmetros`, capa, `Output
Modelo`) **segue sozinho** — perguntar ali seria atrito. Isso vive em
`DiagnosticoArquivo.deve_perguntar` (`src/bp/parsers/abas.py`).

**Duas empresas no mesmo arquivo (holding + controlada).** Quando o arquivo traz
**2+ balancetes** em abas distintas, o diálogo mostra a caixa *"este arquivo tem
mais de uma empresa — gerar uma entrega SEPARADA para cada aba marcada"*. Ela vem
**marcada por padrão** quando as abas não formam uma série de anos (duas empresas
do mesmo período) e **desmarcada** quando são exercícios do mesmo cliente — mas
quem decide é você. Marcada, cada aba vira um arquivo próprio
(`Cliente - Holding_2024…`, `Cliente - Controlada_2024…`); desmarcada, os
exercícios viram colunas de uma só entrega. Ver `REVISAO_QUALIDADE.md` §34.

---

## 3. Armadilhas de leitura já resolvidas (e como reconhecê-las)

Detalhe técnico em `REVISAO_QUALIDADE.md` §30–§32. Se um arquivo novo falhar,
comece por aqui:

| Sintoma | Causa provável | Onde olhar |
|---|---|---|
| `.xls` rende **zero conta** fora do Windows | dependia de LibreOffice/Excel | estratégia `xlrd` já cobre (§30) |
| todas as contas com **`saldo=None`** | cabeçalho desalinhado (rótulo de saldo na coluna de código) | `_coluna_parece_saldo` (§31) |
| cabeçalho **em inglês** não reconhecido | vocabulário só em PT | `BALANCE_KEYWORDS` (§31) |
| entrega **vazia** de arquivo com contas | coluna de descrição é código plano; ou aba-modelo escondeu o balancete | `_find_description_column` / seleção de aba (§32) |
| valores **em milhares errados** | balancete já vinha em milhares | marque "em milhares" na janela |

**Como diagnosticar um arquivo novo rapidamente:**

```python
from src.bp.parsers.dispatcher import ParseyCaller
contas = ParseyCaller("data/samples/NOVO.xlsx").parse()
print(len(contas), "contas")
for c in contas[:5]: print(c.get("codigo"), "|", c.get("descricao"), "|", c.get("saldo"))
```

Se `codigo == descricao` e ambos são números → a **coluna de descrição** foi mal
detectada. Se `saldo` é sempre `None` → a **coluna de saldo** foi mal detectada.

---

## 4. Rastreabilidade: "por que ontem deu certo e hoje não?"

Toda entrega carimba, no Sumário e no **nome do arquivo**, a **impressão
digital** — versão + contagem/hash de três arquivos que mudam sozinhos:

```
Versão 0.8.3 · Plano referencial 1226/16e45bdb · Vocabulário 440/3e8414cc · Template 144/9c7ed510
```

Comparando dois Sumários (ou dois nomes de arquivo), dá para ver **em segundos**
se a diferença entre duas execuções é de **código** (versão) ou de **dado**
(hash do plano/vocabulário/template). A versão é fonte única em
`src/bp/versao.py` — **suba o número (`VERSAO`) a cada mudança que o usuário vê**.

---

## 5. Antes de commitar / publicar

1. **Não-regressão:** rode a suíte e compare com o estado anterior. As falhas de
   *corpus ausente* são esperadas em clone sem os balancetes privados — o que não
   pode aparecer é falha **nova** de código.
   ```bash
   uv run pytest -q -m "not integration"     # deve passar limpo
   ```
2. **Privacidade:** confirme que nenhum `.xls/.xlsx` de cliente entrou no commit
   (`git status`). Conhecimento de treino (`account_variations.json` — só
   descrições/códigos, **sem valores**) é versionado; saída e cache, não.
3. **Versão pública v0.8:** correções de **código** vão para `MAPA_v0.8`
   (público) na mesma branch; **nada com valores**. Traga de volta as melhorias
   que a v0.8 receber ("o melhor dos dois").

---

## 6. Checklist da rodada

- [ ] Balancetes novos em `data/samples/`
- [ ] `train.py` rodado; `training_report.md` revisado
- [ ] Match rate lido pelo denominador certo (÷ tentadas)
- [ ] Pendências revisadas no `review_wizard`; sinônimos com juízo contábil
- [ ] Entrega gerada; **Sumário conferido pelo veredito** (PRONTA/RESSALVAS/VAZIO)
- [ ] Nenhuma entrega vazia marcada como pronta
- [ ] Suíte sem regressão de código; nenhum dado com valor versionado
