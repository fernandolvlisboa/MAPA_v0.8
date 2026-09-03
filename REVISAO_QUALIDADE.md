# Revisão de Qualidade — BP

Revisão de código e da suíte de testes na perspectiva de **revisor do
repositório**: procurar degradações silenciosas, medir o que a suíte realmente
valida, e deixar a rede de testes num estado em que o executor consegue
trabalhar com segurança.

**Base:** `master` após o PR #4 (Plano H — Template GT, Plano I — anos
flexíveis, auditoria de dependências).

**Este documento tem duas partes.** A revisão (§1–§7) mapeou as degradações e
construiu a rede de testes que as trava. O passe de arquitetura (§8) corrigiu
as que a rede cobria, usando os `xfail(strict=True)` como verificação: cada
correção virou XPASS e obrigou a remoção consciente da marca.

---

## Resumo executivo

| | Antes da revisão | Depois da arquitetura |
|---|---|---|
| `uv sync` + `pytest` (fluxo do README) | 169 passed, **6 errors de coleta** | **235 passed**, 6 skipped, 0 errors |
| `uv sync --extra ocr --extra curation` | 203 passed, 3 errors | **298 passed**, 2 skipped, 1 xfailed |
| Implementações de "texto → float" | **5 divergentes** | **1** |
| Contas do plano alcançáveis pelo matcher | 5.738 de 7.741 (**74,1%**) | 7.741 (**100%**) |
| `.txt` pelo dispatcher | **0 contas** | 468 contas |
| Rollup do balancete SPEZZIA | 7 discrepâncias | **0** (soma dos diffs = 0,00) |
| Testes do exporter | 5 verdes sobre **0 contas** | 9 verdes sobre **566 contas** |
| Suíte suja o working tree | sim (`data/match_cache.json`) | não |
| Cobertura `src/bp` | 61% | **68%** |
| Achados do ruff em `src/` | 14 | 12 |
| **Conferência aritmética da origem** | não existia | **14 de 17 balancetes íntegros** |
| **Cobertura de valor (pior caso do corpus)** | não medida | **88,6%** |
| **Testes rodados contra o corpus** | 3 arquivos | **31, com controle + amostra** |
| **Dupla contagem pai+filho na entrega** | possível | impossível por construção |

Resta **1 xfail estrito**: o `CSVParser` que não reconhece um balancete real
(§3c). É um defeito de parser, não de arquitetura, e precisa do layout do
arquivo para ser resolvido.

### O achado que muda a leitura de tudo

A suíte reportava verde. Mas os 5 testes do exporter apontavam para
`auxil/BP_teste/VIVAE ... .xls`, **que não existe no repositório**. O pipeline
engole o erro de leitura (`ParseyCaller.read()` → `except Exception: return
None`), o exporter gera uma planilha bem-formada com **zero contas**, e todas as
asserções passaram: `0 == 0`, laços vazios, comparações vacuosas.

Pior: o vazio mascarava um **erro real de índice**. `test_unmatched_consistency`
lia `row[8]` como `needs_review`, mas `row[8]` é `saldo_atual` — `needs_review` é
`row[14]`. Sobre dados reais o teste falharia. Ele só era verde porque não havia
dados.

> **Verde não é sinal de validação.** A regra que instituí nesta suíte é que
> nenhuma asserção sobre coleção pode passar vazia — todo teste que varre linhas
> afirma antes que há linhas para varrer.

### O achado mais grave: chegava ao cliente

`build_gt_output` (a entrega ao cliente, PR #4) herdava as degradações de
conversão numérica. Com 5 contas sintéticas cobrindo os formatos que aparecem em
balancete brasileiro real, **3 saíam com valor errado — todas com `score = 1.0`
na aba de auditoria e nenhuma em "Contas Não Identificadas"**. Corrigido em §8;
o diagnóstico está em §7.

---

## 1. Conversão numérica: cinco implementações divergentes

`ARQUITETURA.md` §3H registrava **três** implementações duplicadas e as
classificava como *"média prioridade (higiene)"*. São **cinco**, e não é higiene.

| # | Implementação | Quem usa |
|---|---|---|
| 1 | `BaseParser._normalize_saldo` | csv_parser, txt_parser, pdf_parser |
| 2 | conversão inline em `ParseyCaller.parse` (dispatcher.py:149) | **trainer** e **entrega GT** |
| 3 | `_parse_number` em `_parse_accounts_from_df` (dispatcher.py:517) | **xlsx_exporter** |
| 4 | `PDFBalanceParser._to_float` | PDFs de balancete |
| 5 | `_to_float_safe` em `_primary_saldo` (xlsx_exporter.py:78) | rollups |

Comportamento medido (`tests/test_contrato_numerico.py`):

| Entrada | BaseParser | disp. `parse()` | disp. `parse_with_original()` | PDFBalance | exporter |
|---|---|---|---|---|---|
| `"1.234,56"` | 1234.56 | 1234.56 | 1234.56 | 1234.56 | 1234.56 |
| `"1234.56"` | **123456.0** | **123456.0** | **123456.0** | 1234.56 | **123456.0** |
| `"(1.234,56)"` | **0.0** | **0.0** | **None** | -1234.56 | **0.0** |
| `"1.234,56 C"` | 1234.56 | **0.0** | **None** | 1234.56 | **0.0** |
| `"abc"` | **0.0** | **0.0** | None | None | **0.0** |
| `NaN` | **NaN** | 0.0 | None | None | **NaN** |

**1a — Negativo entre parênteses vira zero.** `(1.234,56)` é a notação contábil
padrão de valor negativo. Quatro das cinco implementações perdem o valor **e** o
sinal, sem sinalizar. Só `PDFBalanceParser._to_float` acerta.

**1b — Sufixo D/C zera o saldo.** `"1.234,56 C"` (Devedor/Credor) aparece em
quase todo balancete brasileiro. O dispatcher e o exporter não removem o
marcador; o `float()` falha e o saldo vira `0.0`/`None`.

**1c — Decimal com ponto infla 100×.** `"1234.56"` → `123456.0`. Quatro das cinco
removem *todo* ponto como separador de milhar sem olhar o formato. Basta um
float serializado como string (`str(1234.56)`, CSV em locale EN, célula lida
como texto) para o saldo entrar cem vezes maior no balanço. **É o erro mais
provável de ocorrer em produção e o mais difícil de notar a olho nu.**

**1d — Falha de leitura é indistinguível de saldo zero.** `_normalize_saldo`
devolve `0.0` para entrada ilegível. Nenhum validador a jusante consegue
recuperar a informação de que houve falha: uma conta que o parser não conseguiu
ler é reportada como conta zerada.

**Correção recomendada:** promover `PDFBalanceParser._to_float` a
`src/bp/utils/numero.py` (é a única que já detecta o separador pelo formato e
entende parênteses), acrescentar remoção do sufixo D/C, e fazer as outras quatro
delegarem a ela. Devolver `None` (não `0.0`) em falha, e deixar o chamador
decidir. É a **Fase 1, item 3** do `ARQUITETURA.md` — mas com escopo maior do que
o documento assumia.

---

## 2. NaN envenena o rollup e a validação aprova

O rollup é a única checagem aritmética do sistema — soma os filhos diretos e
compara com o saldo do pai. É o que a aba `Validation` e a métrica
`Rollup Discrepancies` reportam ao usuário final.

A falha mais cara não é o rollup errar. É ele **afirmar que está certo quando os
dados estão corrompidos**. É o que acontece hoje:

```
1        ATIVO       saldo=0.0    calc=0.0    rollup_ok=True
1.1      CIRCULANTE  saldo=0.0    calc=NaN    rollup_ok=True   <-- contaminado
1.1.01   CAIXA       saldo=100.0  calc=100.0  rollup_ok=True
1.1.02   BANCOS      saldo=NaN    calc=NaN    rollup_ok=True   <-- origem
```

**2a — `_primary_saldo` devolve NaN.** `float(nan)` não levanta exceção, então o
`try/except` não pega. O mesmo vale para `_normalize_saldo`, cujo docstring
promete *"0.0 se não puder converter"*.

**2b — `rollup_ok` fica `True`.** Em Python `abs(nan) > tolerância` é `False`,
logo `rollup_ok = not (False and ...) = True`. Um único NaN numa conta-folha
zera a confiabilidade de todo o ramo acima dela **sem levantar nenhuma bandeira**.

**2c — O validador de schema aceita NaN e Infinity.** A validação crítica
"saldos numéricos válidos" é `float(saldo)` dentro de `try/except (ValueError,
TypeError)`. `float('nan')`, `float('inf')` e as strings `"nan"`/`"Infinity"`
convertem sem levantar. Passam como válidos e ainda envenenam a métrica
`avg_saldo`.

Como o pandas produz `NaN` naturalmente em célula vazia, este caminho não é
hipotético.

**Correção recomendada:** em `_primary_saldo`, `_normalize_saldo` e
`validate_parsed_accounts`, tratar `math.isfinite(v)` como condição de
aceitação, não `float(v)` sem exceção. Em `_compute_rollups`, propagar um flag
de "saldo ausente" em vez de somar.

Travado em `tests/test_integridade_rollup.py`.

---

## 3. Roteamento do dispatcher: TXT e CSV silenciosamente vazios

**3a — `parse()` e `parse_with_original()` discordam.** As duas implementações
numéricas dentro do próprio `dispatcher.py` fazem o **trainer e o exporter lerem
saldos diferentes do mesmo arquivo**. Para toda entrada ilegível o trainer vê
`0.0` e o exporter vê `None`. Além disso, `parse()` só lê uma coluna de saldo —
ignora a estrutura de movimento (`saldo_anterior`/`credito`/`debito`) que
`_parse_accounts_from_df` monta. O trainer **e a entrega ao cliente** aprendem e
reportam sobre uma visão empobrecida dos dados.

**3b — `.txt` está declarado como suportado mas não é roteado.**
`SUPPORTED_EXTENSIONS` inclui `.txt` e o trainer usa essa tupla para varrer o
corpus. Mas `parse()` só tem desvio dedicado para `.csv` e `.pdf`; `.txt` cai no
caminho genérico de DataFrame, não acha coluna de descrição e devolve `[]`.

Medido em `src/bp/training/DFS_Exemple/2019-01.TXT` (82 KB):

| Caminho | Contas |
|---|---|
| `TXTParser(arquivo).parse()` direto | **468** |
| `ParseyCaller(arquivo).parse()` (produção) | **0** |

O `TXTParser` — 307 linhas, parser de largura fixa que funciona — **nunca é
chamado em produção**. O trainer descobre o arquivo, processa, extrai zero
contas e o marca como processado. Nada no relatório do treino distingue "arquivo
sem contas" de "arquivo que o roteador não sabe abrir". Na entrega GT o efeito é
uma planilha vazia — mas ali `_validar()` **acusa** (ver §7).

`ARQUITETURA.md` §6 afirma *"o `.txt` agora funciona"*. Funciona no parser;
não funciona pelo dispatcher, que é o caminho que o produto usa.

**Correção:** espelhar em `parse()` o desvio que `.csv` já tem — três linhas.
É o melhor retorno por esforço de toda esta revisão.

**3c — CSV real rende zero contas.** `1544 - BALANCETE 1222024.csv` (61 KB,
separador `;`, preâmbulo de cabeçalho antes da tabela) → 0 contas. Aqui o
roteamento existe; o `CSVParser` é que não reconhece o layout. Cobertura do
`csv_parser.py`: 51%, sem nenhum teste sobre um CSV real.

Travado em `tests/test_dispatcher_roteamento.py`.

---

## 4. O índice do matcher perde 26% do plano de contas

`_prepare_fuzzy_data` monta o índice de busca assim:

```python
self.fuzzy_map[normalize(descricao)] = {...}
```

Chaveado pela **descrição normalizada**. Num plano de contas, descrições se
repetem em ramos diferentes por natureza. Como a chave é a descrição, **a última
conta lida sobrescreve as anteriores** e as demais deixam de existir para o
matcher.

Censo nos planos reais:

| Plano | Contas | Descrições distintas | **Inalcançáveis** |
|---|---|---|---|
| `data/plano_contas.json` | 7.741 | 5.738 | **2.003 (25,9%)** |
| `data/plano_referencial.json` | 1.226 | 1.039 | **187 (15,3%)** |

Os piores casos: `"outros"` (56 códigos → 1 sobrevive), `"outras"` (20),
`"outras provisoes"` (15), `"titulos publicos federais - tesouro nacional"` (14).

**4a — Um quarto do plano é invisível ao fuzzy matching.**

**4b — O Plano C não pode funcionar, por construção.** A restrição por classe
contábil foi criada exatamente para desambiguar homônimos ("Clientes" no ativo
vs. no passivo). Mas ela recebe candidatos de um índice que **já colapsou os
homônimos**. O Plano C consegue *rejeitar* o candidato de classe errada
(derrubando o score), nunca *achar* o certo — ele não está no índice. O
resultado prático é `needs_review=True` onde deveria haver um match correto.

**4c — O cache anula o Plano C a partir da segunda chamada.** O cache é chaveado
só por `normalize(descricao)`, mas a decisão depende também de
`classe`/`tipo`/`natureza`. A consulta ao cache é o **passo 1** de `match()`,
antes de qualquer restrição de classe. Uma decisão gravada num contexto (ATIVO)
é devolvida com `needs_review=False` num contexto incompatível (PASSIVO).

**4d — Na entrega GT o Plano C nem chega a ser ativado.** `build_gt_output`
chama `matcher.match(descricao, codigo_origem=codigo_origem)`. Mas quando o
balancete não tem coluna de código, o dispatcher preenche `codigo = descricao`
(estratégia description-first). Aí `classe_from_codigo("CAIXA GERAL")` devolve
`None` e a restrição por classe fica desligada — sem aviso.

Este é o padrão de degradação mais importante do repositório: **uma camada nova
(Plano C) foi empilhada sobre duas camadas antigas (índice e cache) cujas
chaves são mais pobres que a decisão que a camada nova precisa tomar.** É a
justificativa concreta para o `ScoringPipeline` da Fase 3 do `ARQUITETURA.md` —
mas o pipeline não resolve sozinho: **a chave do índice e a do cache têm de
incluir o código da conta**, senão o problema reaparece na stage nova.

**Correção recomendada:**
1. `fuzzy_map` chaveado por `codigo` (único), com `fuzzy_choices` mantendo a
   lista de descrições e um índice descrição → lista de códigos.
2. Chave do cache = `(descricao_normalizada, classe)`, no mínimo.
3. Na entrega GT, não passar como `codigo_origem` algo que não é código.

Travado em `tests/test_integridade_indice_matcher.py`.

---

## 5. Higiene da suíte

**5a — Testes escreviam no estado versionado.** `ContaMatcher` sem `cache_path`
grava em `data/match_cache.json`, que está sob controle de versão. Rodar
`pytest` sujava o working tree em 16 linhas e tornava o resultado dependente da
ordem dos testes. Resolvido por um fixture autouse de sessão em `conftest.py`
que restaura os JSON de estado ao final. **O fixture é uma rede, não a
correção**: o certo é `ContaMatcher.__init__` não fazer IO em caminho fixo
(item B do `ARQUITETURA.md` §2). O commit `bf5a03e` já atacou o sintoma no
`build_gt_output` (cache efêmero por default) — é a direção certa, falta
generalizar.

**5b — Scripts ad-hoc na raiz quebravam a coleta.** `test_phase3.py`,
`test_matching_complete.py` e `test_phase3_simple.py` têm funções
`test_file(file_path, ...)` que o pytest tentava coletar como teste — 3 erros
num `pytest` puro. Resolvido com `testpaths = ["tests"]`. **Os arquivos
continuam na raiz**: são scripts de diagnóstico, e o lugar deles é `auxil/` ou
`scripts/`.

**5c — Testes que retornavam em vez de assertar.** `test_pdf_parsers_simple.py`
tem funções que fazem `return {...}` — o pytest avisa, mas o teste não valida
nada. Agora `PytestReturnNotNoneWarning` é erro via `filterwarnings`.

**5d — Fixture no diretório errado.** 6 testes de `test_financial_statement_parser.py`
procuravam `auxil/BP_PDF_ex/DF_completa/Voll S.A_60_DF 2023.pdf`. O arquivo
existe um nível acima. Corrigido o caminho — os 6 testes passam.

**5e — Lint não cobre os testes.** `ARQUITETURA.md` §6 reporta "13 achados do
ruff restantes". É verdade para `src/` (14 hoje), mas o total do repositório é
**~100**: 53 em `tests/` e ~28 nos scripts da raiz. Os arquivos criados nesta
revisão passam limpos.

**5f — A auditoria de dependências quebrou o fluxo documentado.** O PR #4
separou os extras `ocr`/`curation`/`windows-xls` (825 MB → 166 MB, ótimo
resultado). Mas o `README` manda `uv sync` e depois `uv run pytest -q`, e nesse
ambiente a suíte terminava em **6 erros de coleta**: 4 módulos importam
`pdf_utils`, que carrega `fitz` (PyMuPDF, extra `ocr`) de forma ansiosa em
`detector.py:13`; e `test_generators.py` precisa de `pydantic` (extra
`curation`). Resolvido com `pytest.importorskip` — os módulos agora **pulam**
em vez de derrubar a coleta, e a suíte fica verde nos dois ambientes.

O núcleo em si está correto: verifiquei que `PDFBalanceParser` extrai 35 contas
de um PDF nativo sem nenhum extra instalado, como o `pyproject` promete.

Fica uma pergunta de empacotamento para o executor: **`FinancialStatementParser`
é núcleo ou curadoria?** Ele parseia DFs *nativas* (não escaneadas), mas depende
de `pdf_utils/detector.py` → `fitz` → extra `ocr`. Se for para ser núcleo, o
`import fitz` precisa virar import tardio.

**5g — O guard de import opcional em `test_pdf_ocr.py` não funcionava.** O
padrão era `try: import ... except ImportError: PDF_UTILS_AVAILABLE = False` +
`pytestmark = skipif(...)`. Não protege: `pytestmark` pula os *testes*, mas os
decoradores `@pytest.mark.skipif(not OCREngine.is_tesseract_installed())` mais
abaixo são avaliados na **coleta**, quando `OCREngine` não existe — o módulo
morria com `NameError` em vez de pular. Trocado por `importorskip`.

---

## 6. Cobertura: onde a rede não existe

| Módulo | Cobertura | Risco |
|---|---|---|
| `parsers/pdf_parser.py` | **0%** (272 stmts) | 11 `except`, 3 engolidos |
| `training/review_wizard.py` | **0%** (247 stmts) | CLI interativo |
| `generators/plano_referencial.py` | **0%** (115 stmts) | — |
| `training/apply_llm_mappings.py` | **0%** | escreve em 2 fontes de verdade (§2C do ARQUITETURA) |
| `parsers/xls_parser.py` | **18%** | **12 `except`, 5 engolidos** — pior combinação do repo |
| `parsers/pdf_utils/ocr_engine.py` | 37% | depende de Tesseract ausente |
| `parsers/txt_parser.py` | 47% | inalcançável em produção (§3b) |
| `parsers/csv_parser.py` | 51% | 0 contas em CSV real (§3c) |
| **`output/` (novo, PR #4)** | **92%** | **referência de como fazer** |

`xls_parser.py` é o alvo prioritário: é o formato mais usado no corpus, tem a
maior densidade de falha silenciosa e a menor cobertura.

O módulo `output/` do PR #4 é o melhor testado do repositório (27 testes, 92%),
inclui `test_arquivo_inexistente_falha_cedo` e `test_template_original_nao_e_modificado`.
É o padrão a replicar nos parsers.

---

## 7. A entrega ao cliente herda tudo

`build_gt_output` consome `ParseyCaller(input_path).parse()` — o caminho do §3a,
o mais pobre dos dois. Balancete sintético com 5 contas nos formatos que
aparecem em balancete real (`escala=1.0`):

| Conta | Valor real | **Valor entregue** | Score no de-para |
|---|---|---|---|
| CAIXA GERAL | `1.234,56` | 1234.56 | 1.0 |
| BANCOS CONTA MOVIMENTO | `1234.56` | **123456** | 1.0 |
| CLIENTES | `(5.000,00)` | **0** | 1.0 |
| FORNECEDORES | `3.000,00 C` | **0** | 1.0 |
| ESTOQUES | `2.000,00` | 2000 | 1.0 |

**7a — 100× inflado chega ao cliente** (§1c).
**7b — Duas contas chegam zeradas** (§1a, §1b). FORNECEDORES era o único passivo,
então o total de Passivo+PL sai 0.

**O que torna isso perigoso não é o número: é a ausência de sinal.**
"Contas Tratadas" — a aba de auditoria do de-para — registra `score = 1.0` nas
três contas corrompidas. "Contas Não Identificadas" sai **vazia**. Para o
analista que confere a entrega, o processamento foi perfeito.

**7c — A rede existe, mas aponta para o lugar errado.** `_validar()` acusa:
`"[2024] Ativo (126,690.6) != Passivo+PL (0.0) — revise 'Contas Não
Identificadas' e a convenção de sinais."` O aviso está certo em disparar e
errado no diagnóstico: manda revisar a convenção de sinais e uma aba vazia,
quando a causa é o parser ter zerado duas contas. Vale acrescentar ao aviso a
contagem de contas com valor zero vindo de origem não-vazia.

Crédito onde é devido: no caso do `.txt` (§3b) a rede funciona bem —
`"Nenhuma linha escrita — o parser provavelmente falhou."` é exatamente o aviso
certo, e é mais do que o trainer faz na mesma situação.

**7d — O sinal do saldo é descartado.**
`valor = abs(valor) * projector.sign_for(codigo_template)` joga fora o sinal
lido e o rederiva da convenção do template. Medido: um saldo de `-5000.0` chega
ao cliente como `5000`. Pode ser decisão de projeto — a convenção de sinal é do
template —, mas o efeito colateral é que **nenhuma anomalia de sinal na origem
chega a ser vista**: um banco a descoberto vira ativo positivo. Se a decisão for
mantida, o valor com o sinal original merece uma coluna na aba de auditoria.

Travado em `tests/test_integridade_entrega_gt.py`.

---

## 8. O passe de arquitetura — o que foi feito

Correção das degradações que a rede de testes cobria. Os `xfail(strict=True)`
da revisão serviram de verificação: cada correção virou XPASS, o que obrigou a
transformar o teste numa trava do comportamento novo. **36 xfail viraram
travas; sobrou 1.**

### 8.1 `utils/numero.py` — uma conversão (§1)

As cinco implementações viram uma. O separador decimal passa a ser decidido
pelo **formato** (`1.234` = milhar, `1234.56` = decimal), parênteses são
negativo, o sufixo D/C é removido e não-finito nunca é saldo.

O contrato é `parse_saldo(v) -> float | None`. **`None` para ilegível, nunca
`0.0`** — porque `0.0` significa "conta zerada" e a distinção é o que permite
ao validador acusar dado corrompido. Quem precisa somar usa
`parse_saldo_ou(v, 0.0)`, e a decisão fica visível no ponto de chamada em vez
de escondida num `except`.

`BaseParser._normalize_saldo` continua devolvendo `float` (para não quebrar
csv/txt/pdf_parser), mas agora é um shim explícito sobre `parse_saldo_ou`.

### 8.2 `parsers/registro.py` — o contrato que não estava escrito

Rotear o `.txt` corretamente expôs um problema mais fundo: **cada parser tinha
vocabulário próprio**. O caminho tabular emite `credito`/`debito`/`saldo`/
`nivel`; o `TXTParser` emite `creditos`/`debitos`/`classificacao` e **nenhum**
campo `saldo` — que é o que todo consumidor lê. As 468 contas recuperadas
chegavam ao exporter e à entrega com valor zero.

O contrato não estava escrito em lugar nenhum: estava implícito no parser que
cada consumidor tinha testado. Agora está num módulo, e **o dispatcher é a
fronteira que o garante** — normaliza sinônimos, deriva `saldo`/`nivel`,
promove o código hierárquico e preserva o interno em `codigo_interno`.

### 8.3 `dispatcher` — um caminho, não dois (§3a, §3b)

`parse()` tinha um extrator inline mais pobre que `_parse_accounts_from_df`
(sem colunas de movimento, sem extração do código embutido na descrição) e com
conversão numérica própria. `parse()` passa a delegar: **−80 linhas**, e
trainer e exporter passam a ler o mesmo arquivo do mesmo jeito.

`.txt` ganhou o desvio dedicado que `.csv`/`.pdf` já tinham: **0 → 468 contas**.

### 8.4 Rollup e validador param de aprovar dado corrompido (§2)

`_saldo_ilegivel` marca a conta cujo campo de saldo existe mas não pôde ser
lido; o ramo sai com `rollup_ok=False` e `rollup_motivo`.

Dois bugs correlatos corrigidos no caminho: a tolerância relativa usava
`abs(diff) / saldo_original` — com saldo **negativo** a razão saía negativa e a
comparação aprovava qualquer diferença (isso só passou a importar agora que os
negativos sobrevivem ao parsing). E `validate_parsed_accounts` trocou
`float(saldo)` por `parse_saldo`: NaN e Infinity deixam de passar como
"numéricos válidos".

### 8.5 Índice do matcher por conta, não por descrição (§4)

`fuzzy_map[descricao] = conta` virou `entradas_por_texto[texto] = [contas]`.
`fuzzy_choices` guarda os textos **distintos** (o que o RapidFuzz pesquisa) e
cada acerto expande para todas as contas daquele texto, que competem pelos
filtros de classe/tipo/natureza.

**Alcançabilidade no plano real: 74,1% → 100%** (2.003 contas recuperadas),
com indexação em 0,27s. `match("CLIENTES", classe="ATIVO")` → `1.1.02.01` e
`classe="PASSIVO"` → `2.1.05.01`: **o Plano C passa a funcionar de fato.**

A chave do cache passou a incluir a classe. Consultas sem classe mantêm a chave
antiga, preservando as decisões já gravadas em `data/match_cache.json`.

### 8.6 `utils/json_store.py` — persistência única

O padrão `if path.exists(): open/json.load ... else: default` estava em seis
pares no `AccountTrainer` mais o `MatchCache`. A duplicação escondia uma
inconsistência: **só um dos seis tratava `JSONDecodeError`** — nos outros
cinco, um arquivo de estado truncado derrubava a rodada de treino inteira.

`load_json` degrada para o default e avisa. `save_json` grava de forma
**atômica** (escreve ao lado, `os.replace`): estado acumulado ao longo de
várias sessões de treino é caro demais para se perder numa gravação
interrompida.

### 8.7 O aviso da entrega aponta a causa certa (§7c)

`BuildResult.saldos_ilegiveis` conta as contas cujo saldo não pôde ser
convertido, e `_validar` reporta isso **antes** do desequilíbrio do balanço —
que agora diz "há contas com saldo ilegível (acima)" em vez de mandar revisar a
convenção de sinais.

### 8.8 Efeito medido no balancete real (SPEZZIA, 566 contas)

| Métrica | Antes | Depois |
|---|---|---|
| Rollup Discrepancies | 7 | **0** (soma dos diffs = 0,00) |
| Match Rate (sintéticas) | 96,3% | 90,1% |
| Needs Review | 3 | 8 |

O rollup fechar **exatamente** é o sinal mais forte de que a conversão numérica
está certa: com 134 contas de saldo não-zero e valores até 14 milhões, a
hierarquia inteira reconcilia.

**A queda do match rate é precisão, não regressão.** Antes o matcher aceitava
automaticamente, com confiança 1.0, a homônima que por acaso sobrevivera à
indexação — podendo ser a errada, que é exatamente o §4b. Agora, quando
homônimas competem e nenhuma vence o filtro de classe, a conta vai para revisão
humana. As 8 na fila são genuinamente ambíguas (`COTAS DE CONSORCIO BANCO DO
BRASIL`, `CUSTOS INDIRETOS DE PRODUÇÃO`). Num sistema contábil, um "não sei"
honesto vale mais que um acerto por sorte — mas é uma troca, e quem decide se
ela é aceitável é você.

### 8.9 O que ficou de fora

- **`CSVParser` não lê um balancete real** (§3c). Único xfail restante. É
  defeito de parser, precisa do layout do arquivo.
- **O sinal do saldo continua descartado** na entrega (§7d):
  `abs(valor) * sign_for(codigo)`. É decisão de projeto do Template GT, não
  defeito — mas agora que os negativos sobrevivem ao parsing, vale decidir se
  o valor com sinal original merece uma coluna na auditoria.
- **Módulos gigantes continuam gigantes**: `conta_matcher.py` (752),
  `xlsx_exporter.py` (719), `trainer.py` (712). O `ARQUITETURA.md` §5 é
  explícito em não quebrá-los antes de arrumar as abstrações — e o passe de
  hoje arrumou as abstrações de dados (número, registro, persistência), não as
  de fluxo (`ScoringPipeline`, `ConversionPipeline`). Essa é a próxima etapa.
- **53 achados de ruff em `tests/`** e ~28 nos scripts da raiz: pré-existentes
  e cosméticos. Os arquivos tocados nesta rodada passam limpos.

---

## 9. O balanço que não fecha — hierarquia

Reportado a partir da interface: 663 contas lidas, 321 identificadas, **324
para revisar**, 50% de aproveitamento, e o balanço não fechando em 2022 e 2024.
Entre as "não identificadas": `SICOOB - UNISUDESTE - RBM 62540-0`,
`SICREDI RBM - 92688-4`, `APLICAÇÃO FINANCEIRA - BB RF MAIS AUTOMATICO`.

### 9.1 O diagnóstico

Essas contas **não podem** casar com plano de contas nenhum — são nomes
próprios do cliente. E não precisam: o agrupador delas existe e já carrega o
total.

```
1.1.1.02        BANCOS CONTA MOVIMENTO              -46.529,09
├ ...0005       SICOOB - UNISUDESTE - RBM 62540-0     9.805,30
├ ...0006       BANCO DO BRASIL S.A - RBM              -814,38
├ ...0007       SANTANDER - RBM                           0,00
├ ...0008       SICOOB RBM - CREDIMATA 20203118-7   -24.850,17
├ ...0009       SICREDI RBM - 92688-4               -24.162,06
└ ...0010       SICREDI RBM FILIAL - 97385-8         -6.507,78
                                                   ─────────────
                                                    -46.529,09  ✓
```

`build_gt_output` **não tinha nenhuma noção de hierarquia** — nem pai, nem
nível, nem rollup. Emitia uma linha por conta que casasse, o que produzia os
dois erros opostos ao mesmo tempo:

- **dupla contagem** quando o agrupador *e* os filhos casavam (o ramo entrava
  duas vezes);
- **valor perdido** quando a folha com nome próprio não casava — e o valor
  simplesmente sumia do balanço.

**Era a causa direta de o balanço não fechar.**

### 9.2 A origem estava certa o tempo todo

Medido com o novo `validators/hierarquia.py`:

| Balancete | Agrupadores que conferem | Equação contábil |
|---|---|---|
| RBM (537 contas) | **80 de 80** | Ativo + Passivo + Resultado = **0,00** |
| SPEZZIA (566 contas) | **81 de 81** | fecha |

O balancete do cliente é aritmeticamente perfeito ao centavo. O defeito era
todo nosso.

### 9.3 Três armadilhas descobertas ao construir o verificador

**a) Código repetido é normal.** No RBM, `2.1.1.01.0010` cobre duas contas
distintas (EMPRESTIMO SANTANDER e JUROS A APROPRIAR). Nove códigos se repetem
= onze contas. Qualquer `dict[codigo] = conta` as descarta em silêncio — e foi
exatamente isso que fez 4 dos 80 rollups "falharem" na primeira medição: **o
defeito estava no medidor**. `xlsx_exporter._build_hierarchy` tinha o mesmo
padrão e perdia as mesmas onze contas; agora funde homônimas somando.

**b) Linhas de totalização viram raízes-fantasma.** O parser emite as linhas de
subtotal com um *número* no código e na descrição (`"-2647871.8"` /
`"3166245.14"`). Oito delas somavam 20,7 milhões de totais inexistentes e
faziam a equação "não fechar". `participa_da_arvore` as exclui reusando
`is_garbage_description` — a definição de linha-lixo que o matcher já tinha.

**c) O pai é o ancestral mais próximo que existe.** Se o balancete traz `1.1` e
`1.1.1.02` mas não `1.1.1`, usar só o prefixo imediato orfana a subárvore
inteira.

### 9.4 A regra de seleção

`selecionar_para_projecao` escolhe **um corte** da árvore — nenhum código
selecionado é ancestral de outro, então não há dupla contagem:

1. Se todos os ramos abaixo do nó são cobertos sem perda, **desce** (mais
   detalhe, mesmo total).
2. Senão, se o nó é mapeado, **para nele**; os filhos são *absorvidos* — o
   valor deles está no total do nó, pela identidade do rollup.
3. Senão, desce e **registra a perda** com o valor exato.

Sem a regra 1 o corte pararia em "ATIVO" e o template receberia o balanço
inteiro em quatro linhas. Sem a regra 2, as contas com nome próprio se perdem.

### 9.5 Resultado no RBM

| | Antes | Depois |
|---|---|---|
| Contas não identificadas | **324** | **3** |
| Contas absorvidas pelo agrupador | 0 | **366** |
| Match rate | **50%** | **96,8%** |

Números do RBM. Ele é o **pior caso** do corpus em cobertura de valor (88,6%,
contra 100% em quatro dos sete balancetes medidos) — ver §10 sobre por que isso
importa.
| Ativo reconstruído vs origem | — | **exato (0,00 de diferença)** |
| Resultado reconstruído vs origem | — | **exato** |
| Passivo | — | faltam **540.192,45** |

Os 540 mil que faltam são honestos: `2.2.1.05 PARCELAMENTOS` e três folhas
abaixo dela **não têm destino no template** — nem elas, nem nenhum agrupador
acima (`2`, `2.2`, `2.2.1` são recusados como "agrupador de topo").

### 9.6 Reconciliação: provar *por que* não fecha

Dizer "não fecha" não serve para nada. O analista precisa ver que a diferença
**é exatamente** a soma de N contas nomeadas — aí ele sabe que não há nada
escondido e decide com segurança.

A identidade sai de duas garantias já estabelecidas: a origem fecha
(Ativo + Passivo + Resultado = 0) e a cobertura é completa (emitido + sem
destino = origem). Logo `emitido == -sem_destino`, e o **resíduo tem de ser
zero**.

```
Diferença do balanço:          540.192,45
Soma das contas sem destino:  -540.192,45
Resíduo sem explicação:              0,00
Conclusão: a diferença é 100% explicada por 3 contas — nada mais falta

CONTAS QUE EXPLICAM A DIFERENÇA
2.2.1.05.0008  PARCELAMENTO PGN - DIVIDA ATIVA  -345.347,77  sem match confiável
2.2.1.05.0009  PARCELAMENTO ISSQN               -177.954,40  casou mas o template não captura
2.2.1.05.0006  PARCELA IR - 00006738216          -16.890,28  sem match confiável
                                        TOTAL   -540.192,45
```

Isso sai na interface **e** na aba `Sumário` do arquivo entregue, com as contas
ordenadas por peso — o analista ataca primeiro o que mais importa.

O caso perigoso tem tratamento próprio: se o resíduo **não** é zero, há conta
contada duas vezes ou perdida, e a mensagem grita `ATENÇÃO` em vez de
tranquilizar. Um resíduo diferente de zero é problema estrutural que nenhuma
revisão manual resolveria.

### 9.7 A invariante que passa a valer sempre

```
para cada classe contábil:  emitido + não coberto == total da origem
```

`BuildResult.cobertura_completa`. Se ela quebra, há conta contada duas vezes ou
perdida, e **nenhum total a jusante é confiável** — a saída sai marcada com
"FALHA GRAVE: não use esta saída".

`balanco_confere` foi reescrito: antes comparava `total_ativo` com
`total_passivo`, dois números já passados por `abs()` e portanto incapazes de
detectar um sinal perdido ou uma conta a menos. Agora exige as três coisas: a
origem consistente, cobertura completa, e todo valor com destino.

Travado em `tests/test_hierarquia.py` (13 testes sobre árvores sintéticas) e
em `test_integridade_entrega_gt.py`, que roda a invariante sobre os balancetes
reais do corpus.

### 9.8 O que a conferência achou de quebra

**O `.TXT` perde o sinal das contas redutoras.** Em `2019-01.TXT`,
`(-) DEPRECIACOES` vem `+32.419.395,76`. Com o sinal certo, a soma dos filhos
de `1.2.03 IMOBILIZADO` dá exatamente os `48.257.635,28` declarados pelo pai.
São 17 agrupadores divergentes pela mesma causa. Fica como `xfail` estrito em
`test_dispatcher_roteamento.py` — é defeito do parser de largura fixa, precisa
do layout do arquivo.

---

## 10. Regra metodológica: nunca calibrar contra um arquivo

**Esta é a seção mais importante do documento.** As outras descrevem defeitos;
esta descreve o erro de método que produz defeitos novos.

### 10.1 O erro

Toda a rodada de correções de hierarquia (§9) foi verificada contra **um**
balancete: o RBM. Isso é sobreajuste. Se o RBM passa e os outros trinta
quebram, não consertamos nada — quebramos o modelo, e o teste verde esconde
isso. Pior: o defeito que o RBM não tem deixa de existir para nós.

Quando finalmente medi o corpus inteiro, o resultado foi este:

| Balancete | Cobertura de valor |
|---|---|
| SPEZZIA, 2025-06, 042025, VIVAE | **100%** |
| 202404 | 99,97% |
| ASP 2023 | 99,30% |
| **RBM** | **88,60%** |

**O RBM é o pior caso do corpus, não o representativo.** Eu passei uma rodada
inteira calibrando contra o outlier — e o `PARCELAMENTOS` que virou exemplo em
todo lugar é uma particularidade que deve acontecer num percentual alto dos
clientes, não um caso a modelar.

O erro também produziu um teste ruim antes de ser pego: eu havia escrito
`resolvidas / contas_lidas > 0.8`, um limiar tirado do RBM. Ele quebrou no
primeiro arquivo diferente — e ao investigar, a métrica em si estava errada
(contar *contas* não mede nada: um código emitido cobre várias homônimas, e
uma folha absorvida pelo agrupador não é conta perdida). A métrica certa é
**cobertura de valor**, que é comparável entre arquivos.

### 10.2 A regra

> **Nenhuma correção é considerada geral até ter sido medida no corpus inteiro,
> antes e depois.** Um defeito só é geral quando mais de um arquivo o exibe.
> Uma correção só é geral quando nenhum outro arquivo piora.

Na prática, três exigências:

**a) Todo teste sobre corpus roda um controle fixo E uma amostra aleatória.**
O controle é a linha de base determinística; a amostra é o que encontra o
defeito no arquivo que ninguém olha. `tests/test_corpus_regressao.py` faz as
duas coisas, e imprime a semente:

```
[corpus] semente da amostra = 605471  (BP_SEED=605471 para repetir)
```

Um teste aleatório sem semente reproduzível é um teste que não se depura.

**b) O controle é escolhido por forma, não por conveniência.** Hoje: hierarquia
profunda com códigos repetidos (RBM), hierarquia limpa (SPEZZIA), outro emissor
(202404), **sem** hierarquia (Real Life — o caso que não pode ser confundido
com sucesso), e largura fixa (`.TXT`).

**c) Nenhuma asserção sobre conta específica de balancete específico.** Não se
testa "PARCELAMENTOS não tem destino". Testa-se a invariante: *seja lá o que
fique de fora, tem de ser reconciliado e nada pode evaporar.* Números de um
arquivo entram como **piso** com folga (`PISO_COBERTURA_DE_VALOR = 0.85`, com o
pior caso observado em 88,6%), nunca como igualdade.

### 10.3 A linha de base do corpus

Medida sobre os 31 arquivos e travada em `test_corpus_regressao.py`. São
mínimos: melhorar é livre, piorar quebra o teste.

| Métrica | Base |
|---|---|
| Arquivos no corpus | 31 |
| Rendem ao menos uma conta | 22 |
| Expõem hierarquia | 17 |
| Rollup íntegro (todos os agrupadores fecham) | **14 de 17** |
| Equação contábil fecha | **14 de 17** |

Se um número desses cair, o commit tem de dizer por quê.

### 10.4 O que a medição do corpus revelou de novo

**Nove arquivos rendem zero contas** — e cinco deles são `.xls`, não CSV. A
causa da maioria é ambiental: `.xls` legado exige LibreOffice ou Excel para
converter, e o aviso já aparece no log (`All conversion strategies failed`).
Não é defeito de código, mas **é um buraco de cobertura que eu não tinha visto
porque só testava contra quatro arquivos**.

Os três `.TXT` divergem todos pela mesma causa única (sinal das contas
redutoras, §9.8) — três sintomas, um defeito.

## 11. Ordem sugerida — o que resta

Os itens 1–7 da lista original foram feitos (§8). O que sobra:

| # | Ação | Esforço | Efeito |
|---|---|---|---|
| 0 | **13 balancetes sem totalizador de classe** (§15.6) — 9 rendem zero contas, 4 não têm árvore | investigar | onde não há totalizador, o teste do core não roda: é o maior buraco restante de cobertura REAL |
| 0b | **`.TXT`: sinal das contas redutoras** — 3 arquivos com origem inconsistente (§15.7) | 1 dia | é o único bloqueio para o teste do core cobrir 19 de 19; a regra "(-) = negativo" foi testada e REPROVADA, precisa de outra |
| 1 | **Reprocessar as entregas já feitas** e comparar com as antigas | meio dia | um saldo 100x inflado que passou despercebido é um erro que o cliente pode ter usado |
| 2 | `CSVParser` reconhecer balancete real com preâmbulo (§3c) | 1 dia | o último xfail; hoje um .csv de cliente rende 0 contas |
| 3 | Testes de `xls_parser.py` (§6) | 1 dia | 18% de cobertura com 12 `except`, 5 engolidos — maior buraco restante |
| ~~4~~ | ~~Decidir sobre o sinal descartado na entrega (§7d)~~ | **feito (§15)** | não era decisão de produto: era defeito. O `abs()` inflava o Ativo em R$ 322.453,04 no balancete medido |
| 5 | `ScoringPipeline` — cada plano (A–G) vira uma stage | 1 sprint | `ARQUITETURA.md` Fase 3; a base de dados já está pronta |
| 6 | `ConversionPipeline` — `xlsx_exporter` volta a ser sink | 1 sprint | `ARQUITETURA.md` §3D |
| 7 | Decidir se `FinancialStatementParser` é núcleo ou curadoria (§5f) | conversa | hoje ele arrasta `fitz` (extra `ocr`) |
| 8 | **`XlsParser` lê o `.xlsx` irmão calado** (§14.3) | 1 dia | `ParseyCaller("X.xls")` pode estar parseando `X.xlsx` de outro período, sem verificação nem aviso |
| ~~9~~ | ~~Equação contábil do Trindade não fecha por 11.666.761,48~~ | **era bug meu (§16.5)** | eu somava as quatro classes como se tivessem sinal; sob natureza implícita a equação é `Ativo − Passivo − (Receitas − Despesas)` e fecha exata |
| ~~10~~ | ~~DRE não bate em 3 balancetes~~ | **feito (§18)** | duas eram da régua, uma era o `abs()` na DRE. 16 de 16 batem; xfail removido |

**O item 1 vem primeiro.** As correções de §8 mudam números. Antes de gerar
qualquer entrega nova, vale saber quais das antigas estavam erradas.

Os itens 5 e 6 são a continuação natural: o passe de hoje arrumou as abstrações
de **dados** (número, registro, persistência). As de **fluxo** — o pipeline de
scoring e o pipeline de conversão — continuam por fazer, e são o que
`ARQUITETURA.md` §5 dizia para resolver antes de quebrar os módulos gigantes.

### Como trabalhar com os xfail

Resta um: `test_csv_real_deveria_render_contas`. Ao corrigir o `CSVParser`:

1. Rode a suíte. O teste vira **XPASS → FAILED** (é `strict`).
2. Remova o `@pytest.mark.xfail`.
3. `test_csv_tem_desvio_dedicado_no_dispatcher` documenta o mecanismo atual e
   vai precisar de ajuste junto.

```bash
uv sync                                   # núcleo: 235 passed, 6 skipped
uv sync --extra ocr --extra curation      # completo: 298 passed, 2 skipped, 1 xfailed
uv run pytest -m contrato -q              # contratos entre camadas
uv run pytest -m integration -q           # o que depende do corpus real
```

---

## 12. A coluna de código que não era reconhecida

### 12.1 O gatilho

O revisor pegou um balancete, rodou, e a saída veio errada em duas frentes ao
mesmo tempo: valores que pareciam somados duas vezes, e contas de resultado
aparecendo no Balanço.

O arquivo **tinha** coluna de código hierárquico. Ela se chamava
`Conta contábil`, e trazia `'1'`, `'1.1.1.01.001'`. O detector procurava por
nome numa lista fixa:

```python
candidates = ["código", "codigo", "cod", "class"]
```

`"conta"` não está na lista. `_find_codigo_column` devolvia `None`.

### 12.2 A cascata

Um `None` numa função de detecção não falha — ele **degrada**, e a degradação
percorre o pipeline inteiro sem nunca virar erro:

| passo | o que acontece |
|---|---|
| 1 | sem código, `codigo = descricao` (fallback *description-first*) |
| 2 | `classe_from_codigo("ALUGUEIS")` → `None` |
| 3 | com classe `None`, o **Plano C** (restrição por classe) fica desligado |
| 4 | `conferir_hierarquia` reporta "SEM HIERARQUIA" |
| 5 | `selecionar_para_projecao` **nunca roda** — pai e filhos são ambos emitidos |
| 6 | o match vira texto puro: "ALUGUEL E CONDOMÍNIO **A PAGAR**" (passivo) casa "Condomínio" (despesa `3.x`) com score 1.0 |

Os passos 5 e 6 são, exatamente, as duas queixas do revisor. **Um único
defeito de detecção explica as duas.**

### 12.3 As correções

**Conteúdo decide, nome só desempata.** `_find_codigo_column` passou a
ranquear *todas* as colunas pela proporção de valores com 3+ segmentos
(`1.1.1`), excluindo a coluna de descrição. Nome de coluna é dica, não prova.

Medido: no balancete que expôs o defeito, a coluna certa marca **29,4%** e
todas as outras **0,0%**; nos demais balancetes do corpus, **95–97%**. O limiar
ficou em 10%.

**Esquema misto na mesma coluna.** O mesmo arquivo alterna dois esquemas: as
sintéticas trazem o código hierárquico alinhado à esquerda
(`"1.1.1.01.001      "`), as analíticas trazem um código interno plano
**indentado à direita** (`"             11111"`). A filiação está na *posição*,
não no prefixo.

Sem ler isso, cada analítica virava uma **raiz** própria — e como as sintéticas
também eram raízes, todo valor entrava duas vezes na equação contábil. Medido:
**23,3 milhões de excesso, 132 raízes onde deveria haver 4**.
`_resolver_codigo_indentado` pendura a analítica na sintética imediatamente
acima.

**A armadilha do encadeamento.** A primeira versão promovia a folha
sintetizada a novo "último sintético", produzindo
`1.1.2.01.007.11271.11273.11276` e 102 divergências de rollup. A guarda é uma
linha:

```python
if not codigo_interno and "." in codigo:
    ultimo_sintetico = codigo
```

Só um código hierárquico **de verdade** vira pai. Uma folha sintetizada nunca.

### 12.4 O efeito

| | antes | depois |
|---|---|---|
| hierarquia detectada | "SEM HIERARQUIA" | 67 pais conferem |
| pais divergentes | — | 0 |
| raízes | 132 | 4 |
| projeções que trocam de classe (corpus) | — | 0 |
| regressão nos demais balancetes | — | **nenhuma** |

### 12.5 A lição — e ela é sobre o §10

Este defeito passou pelo harness de corpus do §10. Por quê?

Porque a métrica estava errada. O harness contava **quantos arquivos têm
hierarquia** e travava esse número contra uma linha de base. Um arquivo cuja
coluna de código não fosse reconhecida caía silenciosamente no balde "não tem
hierarquia" — indistinguível de um arquivo que genuinamente não tem. A linha de
base continuava batendo. O teste continuava verde.

A métrica certa é a **negação**: *nenhum arquivo pode perder a hierarquia que
ele tem*. Ela está em `tests/test_deteccao_codigo.py`:

```python
def test_nenhum_balancete_perde_a_hierarquia_que_tem():
    # Para todo arquivo do corpus cuja ORIGEM traz código hierárquico,
    # o pipeline tem de reconhecê-lo.
```

O §10 dizia "não calibre contra um arquivo". Faltava o corolário:
**medir a propriedade, não a contagem**. Uma contagem agregada absorve um
defeito individual sem mudar de valor; a invariante por arquivo, não.


## 13. O asterisco do SUMIFS e o vão entre "escrito" e "entregue"

### 13.1 A observação

Ao abrir uma entrega real, o revisor apontou:

> "Colocar um asterisco pra fazer a conta não faz o menor sentido. Se a gente
> está falando de uma conta sintetizadora principalmente, porque a gente vai
> somar a conta sintetizadora e vai somar os filhos dela — conta pai e os
> filhos."

A fórmula de cada linha do template é:

```
=IFERROR(SUMIFS(_dados_padronizados!C:C, _dados_padronizados!$A:$A, $C9&"*"), 0)
```

O curinga soma **tudo que começa com** o código da linha. A preocupação está
certa: se o template tiver uma linha `1.01` e outra `1.01.02`, todo valor sob
`1.01.02` é somado nas duas — dupla contagem por construção.

### 13.2 O que a medição mostrou

Duas medições, e a primeira estava errada.

**Primeira tentativa (errada).** Li a coluna C como se fosse o critério do
SUMIFS. Ela não é: uma linha da DRE traz `3.01.01.07.01.01|3.01.01.07.01.02|…`
— vários códigos unidos por `|` — e a fórmula correspondente é uma **soma de
vários SUMIFS**, um por código, com o critério literal dentro dela. Medindo
errado, "encontrei" 7 linhas somando R$ 3.467,95 que nenhuma linha capturava.
Não existiam. Foi o mesmo tipo de erro do §10: *o defeito estava no medidor*.

**Medição correta** — extraindo o critério de dentro de cada fórmula:

| | |
|---|---|
| linhas com SUMIFS | 44 |
| critérios de captura | 86, todos distintos |
| pares de prefixos aninhados | **0** |
| linhas escritas capturadas por 2+ linhas do template | **0** (corpus inteiro, 32 arquivos) |
| linhas escritas capturadas por 0 linhas | **0** |

Ou seja: **hoje o asterisco não gera dupla contagem**, e o que ele faz é
necessário — é ele que agrega os códigos referenciais mais profundos
(`3.01.01.07.01.02`) na linha da entrega. A dupla contagem que existia era
outra: pai e filho *da origem* sendo ambos emitidos, corrigida em §9 e §12.

### 13.3 Por que isso ainda era um problema

Porque a garantia era **acidental**. Nenhum teste verificava que os prefixos do
template não são aninhados; nenhum verificava que uma linha escrita chega à
entrega. Uma edição no Excel que acrescentasse uma linha totalizadora ao lado
das analíticas quebraria a entrega em silêncio.

E havia um vão pior, que ninguém media: **escrever em `_dados_padronizados` não
põe número nenhum na entrega**. Se um código escrito não casar com nenhum
critério, o valor está na aba de dados e não aparece em lugar nenhum — e o
Sumário ainda o conta como "conta tratada", afirmando 100% de match enquanto o
dinheiro evaporou.

### 13.4 O que passou a existir

**`TemplateProjector.linhas`** — o template deixou de ser modelado como um
conjunto solto de prefixos e passou a ser uma lista de `LinhaTemplate`
(aba, linha, rótulo, prefixos). Só o conjunto de prefixos não responde
"quantas *linhas* somam este código?", que é a pergunta que importa.

**`TemplateProjector.prefixos_aninhados()`** — devolve os pares em que um
prefixo captura o outro. Enquanto for vazio, o curinga é seguro.

**`_conferir_captura()`** em `build_gt_output` — para cada linha escrita,
conta quantas linhas do template a somam. O contrato é **exatamente uma**:

- **zero** → aviso `VALOR PERDIDO NA ENTREGA`, com o total e os códigos;
- **duas ou mais** → aviso `DUPLA CONTAGEM`, com quanto a entrega foi inflada;
- prefixos aninhados → aviso `TEMPLATE INCONSISTENTE`, nomeando a *causa* e
  não só o efeito.

`BuildResult` ganhou `captura_integra`, `valor_sem_captura` e
`valor_contado_duas_vezes`.

**`tests/test_captura_template.py`** (14 testes). O mais importante não é
nenhum dos dois acima:

```python
def test_prefixos_lidos_batem_com_os_criterios_reais_das_formulas():
```

O código modela o template lendo a **coluna C**; o Excel soma pelo **critério
dentro da fórmula**. Enquanto os dois coincidirem, o modelo é fiel. Se alguém
editar a fórmula e esquecer a coluna C (ou o contrário), o Python projeta para
um alvo que não existe e o valor some — sem erro, sem aviso. Este teste é a
única coisa que impede isso. Foi escrito depois de eu mesmo confundir as duas
fontes na primeira medição.

Os detectores são exercitados contra um **template sintético** com prefixos
aninhados de propósito (`_projector_sintetico`). Sem isso, os testes de corpus
também passariam com o detector permanentemente desligado — que é exatamente o
estado em que o defeito chegaria ao cliente.

A trava sobre balancetes reais segue a regra do §10: **controle fixo + amostra
aleatória com semente impressa** (`BP_SEED`).

### 13.5 Custos e despesas no Balanço — a trava que faltava

O revisor também apontou: *"custos e despesas foram parar no balanço, a conta é
claramente de resultado"*. A causa-raiz era a coluna de código não ser detectada
(§12): sem código, `classe_from_codigo` devolve `None`, o **Plano C** desliga, e
"ALUGUEL E CONDOMÍNIO A PAGAR" (passivo) casa com "Condomínio" (despesa `3.x`)
com score 1.0.

A causa foi corrigida, e a medição confirma: **0 projeções trocam de classe** em
todo o corpus. Mas de novo — garantia acidental. `_resolver()` ganhou a
conferência final, sobre o **código do template**, onde não depende de nenhuma
etapa anterior ter funcionado:

```python
classe_origem = classe_from_codigo(str(conta.get("codigo", "")))
classe_destino = classe_from_codigo(proj.codigo_template)
if classe_origem and classe_destino and classe_origem != classe_destino:
    return _Resolucao(conta, decisao=r.decision, motivo="classe incompatível: …")
```

Recusar custa o valor da conta — ela vai para "Contas Não Identificadas" e
aparece na reconciliação, visível. Aceitar custa a corretude do Balanço **e da
DRE ao mesmo tempo**, em silêncio. Recusar é a escolha certa.

Efeito medido no corpus: **nenhum**. É seguro por não mudar nada hoje, e é
exatamente por isso que vale — é seguro-contra-amanhã.

## 14. A cópia do original dentro da entrega

### 14.1 O pedido

> "Eu já pedi milhões de vezes para deixar a cópia do arquivo original dentro
> do output, para ficar fácil o rastreio."

Pedido legítimo e repetidamente ignorado. Uma entrega é o resultado de uma
cadeia de decisões (parser → matcher → projeção → SUMIFS); responder "de onde
saiu este número?" não pode depender de reencontrar, meses depois, o balancete
numa pasta de rede.

### 14.2 O que foi feito

**`src/bp/output/origem.py`** — transcreve o arquivo de origem e o escreve numa
aba `Balancete Original` (ou `Original <ano>` em série histórica), posicionada
entre as abas internas e as técnicas.

O cabeçalho da aba traz **nome, caminho, tamanho, data de modificação e
SHA-256**. O hash é o que transforma "parece o mesmo arquivo" em prova. O
Sumário ganhou um bloco **ORIGEM DOS DADOS** que indexa as origens pelo hash.

Por formato:

| formato | como é transcrito |
|---|---|
| `.csv`, `.txt` | uma linha do arquivo por linha da aba, **verbatim** |
| `.xlsx` | todas as abas, `header=None` — nada é descartado |
| `.xls` | via o `.xlsx` irmão, ou convertendo pelo LibreOffice |
| `.pdf` | texto extraído, página a página |

`header=None` é o ponto: o pipeline detecta cabeçalho e **descarta o
preâmbulo** — que é justamente onde estão empresa, período e data de emissão.
A cópia não descarta nada.

### 14.3 O achado de quebra: o `.xls` que não é lido

Construindo isso, apareceu um comportamento que ninguém tinha documentado.
`XlsParser.read()` tem um "fast path":

```python
sibling_xlsx = self.file_path.with_suffix(".xlsx")
if sibling_xlsx.exists():
    df = ExcelParser(sibling_xlsx).read()   # lê OUTRO ARQUIVO, calado
```

`ParseyCaller("Balancete.xls")` pode estar lendo `Balancete.xlsx`, sem
verificação de que são o mesmo balancete e sem avisar ninguém. No corpus isso é
inofensivo (os `.xlsx` são conversões dos `.xls`); numa pasta de cliente com um
`.xlsx` homônimo de outro período, não é.

Para a aba de rastreio isso é fatal: transcrever o `.xls` enquanto o pipeline
leu o `.xlsx` seria mostrar um arquivo que não gerou número nenhum — **o pior
tipo de rastreio, o que dá confiança errada**. Por isso `_conteudo_de()` segue
a mesma rota do parser e declara a troca na aba:

> ATENÇÃO: o conteúdo veio de Balancete SPEZZIA…xlsx, não do .xls — o parser
> prefere o .xlsx de mesmo nome quando ele existe

O SHA-256 continua sendo o do arquivo **pedido**; a procedência explica a troca.
A substituição silenciosa em si continua no `xls_parser.py` e entra na lista
do §11 — corrigi-la é mudar comportamento de parsing, não de rastreio.

### 14.4 Limite honesto

XLSX não guarda anexo binário pelo openpyxl. A aba é uma **transcrição fiel do
conteúdo**, não o arquivo embutido byte a byte: formatação, fórmulas e imagens
do balancete de origem não vêm junto — os valores e o texto, sim. O SHA-256
identifica o arquivo de onde vieram.

Um arquivo ilegível não derruba a entrega: vira uma `Origem` com `erro`
preenchido, que aparece na aba **e** nos avisos do Sumário. A entrega não pode
falhar porque o rastreio falhou, mas também não pode mentir que está tudo bem.

**`tests/test_copia_original.py`** (14 testes), incluindo a guarda de
não-vacuidade — uma aba criada só com o cabeçalho passaria em qualquer teste de
existência e não rastrearia nada — e a conferência de que os **valores
numéricos** do original chegam à aba, não só as descrições.


## 15. O teste do core: o Ativo entregue é o Ativo do balancete?

### 15.1 A cobrança, e ela estava certa

> "São trezentos, quatrocentos testes, mas ele não testa o core da coisa. Ele
> testa, sei lá o quê. Eu preciso desse teste geral. Qual é o ativo desses
> balancetes? Se o ativo desses balancetes soma dois milhões de reais, o ativo
> do resultado que você vai encontrar deve somar dois milhões de reais. O ativo
> é uma linha que quase sempre aparece no balancete já como um totalizador,
> isso é algo fácil de ser achado."

446 testes, e nenhum respondia isso. Todos mediam **proxy**: quantas contas
casaram, se a árvore da origem fecha, se cada linha escrita é capturada por uma
linha do template (§13). Proxy fica verde com o número final errado — e ficou.

### 15.2 O ponto cego era estrutural

**Escrever em `_dados_padronizados` não põe número na entrega.** Quem soma são
as fórmulas do template, e **nada em Python as executava**. Entre o último
teste e o número que o cliente lê havia uma camada inteira sem cobertura
nenhuma.

Foi por isso que o §13 errou de pergunta. Ele perguntou "quantas linhas do
template capturam cada linha escrita?" — e a resposta, exatamente uma, estava
certa. A pergunta certa era outra: **quanto dá o Ativo no final?**

### 15.3 O que a medição achou

`validators/entrega.py` interpreta as fórmulas de BP_GT/DRE_GT como o Excel as
interpretaria — inclusive o curinga `*` — e compara com o totalizador da
origem. Aplicado ao balancete que o revisor mandou:

| | |
|---|---|
| ATIVO declarado na origem | 2.361.053,53 |
| ATIVO entregue | **2.683.506,57** |
| diferença | **+322.453,04** |

E a causa não era o asterisco. Era esta linha:

```python
valor = abs(_escalar(bruto, escala)) * projector.sign_for(codigo_template)
```

O `abs()` **apaga o sinal da origem** e o substitui pelo sinal da *linha do
template*. Como nenhuma linha do BP_GT é `(-)`, toda conta redutora do Balanço
entrava positiva:

| conta | origem | entrega |
|---|---|---|
| (-) DEPRECIACOES, AMORT. E EXAUST. ACUM. | −155.617,00 | **+155.617,00** |
| (-) Amort. Lic. Uso Software | −5.609,52 | **+5.609,52** |

`2 × (155.617,00 + 5.609,52) = 322.453,04`. Exatamente a diferença medida.

### 15.4 A correção

Balanço e DRE seguem regras **diferentes**, e tratá-los igual era o defeito:

- **Balanço** — o sinal é o da ORIGEM. A conta redutora é negativa lá e tem de
  continuar negativa aqui. Só a *classe* é orientada
  (`_orientacao_por_classe`), para que Ativo e Passivo saiam ambos positivos —
  o check do template é `ROUND(D26-D52,2)=0`, uma **subtração**.
- **DRE** — a origem não carrega sinal utilizável: sob natureza implícita
  receita e despesa vêm ambas positivas. Quem decide é o rótulo da linha
  (`(-) Despesas com pessoal`), porque as fórmulas da DRE **somam**. Aí sim
  `abs() * sign_for()`.

A orientação por classe atende as duas convenções de balancete brasileiro: a
que traz Ativo e Passivo ambos positivos (natureza implícita) e a que traz o
Passivo negativo para as três classes somarem zero. Ela é decidida pelo
totalizador da classe, não conta a conta — é isso que preserva o sinal
*relativo* de dentro dela.

As duas convenções existem mesmo no corpus: **7 balancetes** trazem o Passivo
negativo (RBM −2.370.036,20; SPEZZIA −14.014.160,10; VIVAE −25.860.155,42;
202404 −202.331.833,64; e outros três). A orientação não é código defensivo
para um caso hipotético.

**A primeira versão da orientação estava errada**, e um teste antigo a pegou.
Sem árvore, ela inferia a convenção somando as contas da classe. Num recorte de
balancete — o sintético de cinco contas dos testes de formato numérico — a soma
do Ativo dá −530,88 **por acaso** (uma conta de clientes negativa maior que as
outras), e a inferência inverteu o arquivo inteiro: caixa de +1.234,56 virou
−1.234,56.

A regra corrigida: **só o totalizador declarado orienta**, e "declarado" exige
árvore de verdade (`tem_hierarquia`). Sem evidência, não se mexe no sinal — e
se a convenção for outra, quem denuncia é a própria conferência de totais.
Inverter em silêncio é sempre pior que entregar e acusar.

### 15.5 A identidade que o teste assere

Não basta `entrega == origem`: uma conta pode legitimamente não ter destino no
template — acontece num percentual alto dos clientes (§10) — e o valor fica de
fora por decisão consciente e reportada. A identidade certa é:

```
entrega + não coberto == origem
```

O resíduo dessa conta é o que não tem explicação, e é sempre defeito.

### 15.6 O discriminador, e por que ele não é nome de arquivo

Um balancete cuja **origem** já não fecha não pode produzir entrega
consistente. Nesses casos o que se exige é que o sistema **diga** que a origem
está quebrada — não que os totais batam.

O corte é por propriedade do dado (`rollup_integro`), nunca por nome de
arquivo. Medido no corpus:

| | |
|---|---|
| balancetes com totalizador | 19 |
| origem íntegra **e** identidade bate | **15 (100% dos íntegros)** |
| origem íntegra e identidade falha | **0** |
| origem já inconsistente (xfail conhecido do sinal em `.TXT`) | 4 |
| sem totalizador (nada a conferir) | 13 |

### 15.7 A regra que quase virou defeito

A tentação óbvia era: "descrição que começa com `(-)` marca conta redutora,
então negue o valor". Medi antes de aplicar, usando a identidade do rollup como
juiz:

| | divergências antes | depois da regra |
|---|---|---|
| 202404_2024 | 0 | **5** |
| Balancete-2025-06 | 0 | **2** |
| RBM / ASP / SPEZZIA / VIVAE | 0 | **1 cada** |
| 2019-01.TXT | 17 | 16 |

A regra **quebra 8 arquivos que hoje estão certos** e quase não ajuda os
`.TXT`. Em vários balancetes a conta marcada `(-)` já vem negativa, e negar de
novo inverte. **Não foi aplicada.** Fica o registro de que a hipótese foi
testada e reprovada — o xfail do `.TXT` continua sendo o caminho certo.

### 15.8 A prova de que o teste não é decorativo

Revertendo o `abs()` para o comportamento antigo, `tests/test_totais_da_entrega.py`
falha — e falha inclusive no **RBM**, que os 446 testes anteriores davam como
perfeito:

```
Balancete 072022 122022 - RBM.xls: o total da entrega não é o total do balancete.
  resíduo por classe: {'ATIVO': 288.99653999999964}
Balancete 042025 em excel.xlsx: …
  resíduo por classe: {'ATIVO': 36.2021, 'PASSIVO': 869.9999}
```

O teste tem piso de não-vacuidade (`PISO_CONFERIVEIS`): pelo menos três
balancetes do controle têm de chegar à conferência de verdade, senão ele
acusa que estaria passando por vacuidade. E o avaliador de fórmulas — que é a
régua — **levanta exceção** diante de uma fórmula que não modela, em vez de
devolver zero calado e fabricar um "confere".

### 15.9 O que mudou na entrega

- `BuildResult.entrega` carrega a conferência; `balanco_confere` passou a
  **exigi-la** (as outras conferências são proxy, e proxy já ficou verde com o
  total errado).
- O Sumário abre com **CONFERÊNCIA DOS TOTAIS**: o total no balancete, o total
  na entrega e a diferença, em vermelho quando não bate.
- Um aviso nomeia a divergência: *"TOTAL DA ENTREGA NÃO BATE COM A ORIGEM …
  O número que o cliente lê está errado; não use esta saída."*

### 15.10 A lição

O §10 disse "não calibre contra um arquivo". O §12 acrescentou "meça a
propriedade, não a contagem". Falta o terceiro, e é o mais caro:

**Meça o número que o cliente lê, não a etapa anterior a ele.** Toda métrica
intermediária — match rate, cobertura, integridade de captura — pode estar
perfeita enquanto o total final está errado. Se existe uma camada que o teste
não executa, é exatamente lá que o defeito mora.


## 16. A receita que virou custo

### 16.1 O que o revisor viu

> "Ele simplesmente ignorou receita, e o balanço não fecha, não por nada, mas
> porque ele ignorou a receita. Como é que o negócio ignora a receita? Como é
> que linhas são ignoradas? Como é que não existe um teste que consiga
> visualizar esse tipo de coisa? E o DRE tá todo errado. Todo."

Não foi "ignorou" — foi pior. A receita **foi classificada como custo**:

```
3.01.01.03.01.03   Servicos prestados - mercado interno   -4.937,53
```

`3.01.01.03` é a linha **"(-) Custos dos produtos, mercadorias e serviços
vendidos"**. Erro duplo: a receita some da DRE **e** o custo infla pelo mesmo
valor, de modo que o resultado do exercício erra por **duas vezes** o valor da
conta.

### 16.2 Por que nada pegou

O Plano C restringe por classe: ATIVO / PASSIVO / RESULTADO. Origem e destino
eram **ambos RESULTADO** — não havia o que restringir.

E o cache tinha gravado, com `manual: false` e score 1.0:

```
'servicos prestados' -> {"codigo": "3.01.01.03.01.03",
                         "descricao": "(-) Custo dos Serviços Prestados",
                         "score": 1.0}
```

A consulta ao cache é o **passo 1** de `match()`, antes de qualquer filtro.
Era a armadilha que o §4c descreveu para classe e que se repetiu um nível
abaixo. **Apagar a entrada não seria correção** — seria limpar o sintoma e
esperar a próxima.

### 16.3 A correção: natureza de resultado

`src/bp/utils/natureza.py`. RESULTADO não é uma classe, são **duas naturezas**
com sinais opostos. A natureza é lida da **árvore**, e a mesma função serve os
dois lados:

| lado | conta | o que ela declara | o ramo |
|---|---|---|---|
| balancete | `Servicos prestados - mercado interno` | nada | `4 RECEITAS` → **RECEITA** |
| balancete | `Servicos prestados por terceiros` | nada | `3.2 DESPESAS OPERACIONAIS` → **DESPESA** |
| referencial | `Serviços Prestados por Terceiros` | nada | `3.90.02 Despesas Administrativas` → **DESPESA** |
| referencial | `(-) Custo dos Serviços Prestados` | `(-)` → DESPESA | — |

As duas primeiras estão **no mesmo balancete**, com nomes quase idênticos e
sinais opostos. É esse par que o Plano C não separava.

**Ancestral mais próximo, não o mais alto.** A regra do "mais alto" parece mais
estrutural e quebra feio: a raiz `3` do Plano Referencial da RFB tem descrição
*"Redução do IPI na **Venda** de Bens de Informática..."* — declararia RECEITA e
classificaria as 451 contas de resultado do plano inteiro como receita, custos
e deduções inclusive. Medido, não suposto.

A natureza entra em três lugares: no **índice** do matcher (cada candidato
carrega a sua), na **chave do cache** (senão o passo 1 continua atropelando a
restrição) e como **penalidade cruzada** de 0,3 — mais dura que a de classe
(0,5), porque o erro é pior: inverte o sinal e conta duas vezes.

Foi preciso também o **simétrico**: um bônus de +5 para o candidato de natureza
certa. Sem ele, um candidato de natureza *desconhecida* escapa da penalidade e
vence por meio ponto — medido: `Receita da Prestação de Serviços no Mercado
Interno` fazia 76,0 contra 76,5 de `Serviços Prestados por Terceiros`.

E uma trava final em `_resolver`, sobre o destino, para o caso de tudo isso
falhar.

### 16.4 O balancete aberto

> "O balancete costuma ser aberto; em algum ponto pode se indicar que a
> diferença pode estar no resultado."

Exato, e é o resto da explicação. Balancete de verificação mensal vem **aberto**:
as contas de resultado ainda têm saldo e o lucro **não foi transferido** ao PL.
Nesse estado, Ativo ≠ Passivo + PL *por construção* — a diferença **é** o
resultado:

```
Ativo 2.361.053,53 − (Passivo + PL) 891.480,90 = 1.469.572,63
Receitas 4.941.899,84 − Despesas 3.472.327,21 = 1.469.572,63
```

`_transferir_resultado_do_periodo` lança o resultado em
`2.03.04.01 Lucros/prejuízos acumulados` — onde ele mora contabilmente
enquanto não há encerramento. O PL passa de 523 para **1.992,85** e o Balanço
fecha em 2.361,05. Medido no corpus: **6 dos 15 balancetes conferíveis são
abertos**.

**A conferência dupla é o ponto.** `Ativo − Passivo` diferente de zero *não*
prova balancete aberto — também aparece quando a extração perdeu uma conta.
Plugar cegamente fabricaria um balanço fechado em cima de um erro, escondendo
justamente o que precisa aparecer. A transferência só acontece quando os dois
caminhos independentes concordam; quando divergem, nada é lançado e fica o
aviso. Falha de forma segura.

### 16.5 Meu erro anterior, corrigido

O "**a equação não fecha por 11.666.761,48**" que eu reportei por várias
rodadas **era bug meu**. Eu somava as quatro classes como se tivessem sinal:

```
2.361.053,53 + 891.480,90 + 3.472.327,21 + 4.941.899,84 = 11.666.761,48
```

Sob natureza implícita — todos os saldos positivos — a equação é outra, e
fecha exata:

```
Ativo − Passivo − (Receitas − Despesas) = 0,00
```

Eu vinha oferecendo isso como "provável questão de convenção de sinal, decisão
sua". Não era decisão nenhuma: era o medidor errado, de novo.

### 16.6 O que ficou aberto, e está travado

`conferir_dre` compara o lucro líquido entregue com `Receitas − Despesas` da
origem. Ele **acha defeito em 3 dos 8 balancetes conferíveis**:

| balancete | diferença |
|---|---|
| 202404_2024 | −216,64 |
| ASP 2023 | −92,44 |
| VIVAE 12.2023 | −383,13 |
| **Trindade / RBM** | **batem ao centavo** |

Duas causas, uma identificada e uma não:

**(a) Ramos sem natureza declarada.** ASP tem `3 RESULTADO LÍQUIDO DO PERÍODO
ANTES DO IRPJ...` e `4 IMPOSTOS E PARTICIPAÇÕES SOBRE O LUCRO` — nenhum dos
dois declara natureza, então o ramo de IRPJ/CSLL (87,40 mil) fica **fora da
referência de origem**. A entrega o subtrai corretamente; a comparação é que é
injusta. Mesma coisa em 202404 (`4 RESULTADO DO EXERCICIO`).

**(b) VIVAE.** 92 de 92 contas classificadas e ainda assim diverge em 383,13.
**Causa não encontrada.**

Está travado como `xfail(strict=True)` em
`test_lucro_liquido_da_entrega_e_receitas_menos_despesas`, com os números
medidos no motivo. Ao corrigir, o marcador vira XPASS → FAILED e exige remoção
consciente.

Não fechei isso e não vou fingir que fechei. O que está verificado é a
correção do defeito reportado e o fechamento do Balanço; a conferência da DRE
existe, roda, e denuncia o que ainda não bate.

### 16.7 Um teste meu que se auto-sabotou

Escrevendo o teste do balancete aberto, pus no controle
`VIVAE ... Emitido em 06.06.2024.xls`. O arquivo real é
`Emitido em 03.05.2024.xls`. O `if not caminho.exists(): continue` fazia o
VIVAE **sumir do controle em silêncio** — e cair na amostra aleatória, onde a
cobertura vira sorteio.

É exatamente a armadilha do §5 (fixture ausente → teste verde sobre nada), que
esta revisão existe para impedir, cometida por mim. Agora controle ausente é
`assert`, não `continue`.


## 17. Os balancetes reais, e os quatro defeitos que eles expuseram

### 17.1 O teste que importava

Seis balancetes de clientes, recebidos nos últimos meses — os casos para os
quais o programa está sendo feito — foram postos no corpus.

**Os seis rendiam zero contas.** Um derrubava o parser com exceção.

Nenhum teste da suíte podia ter pego isso. Todos rodavam sobre o corpus
antigo, e **um arquivo que o pipeline não consegue ler não aparece em métrica
nenhuma** — não entra na contagem de parseados, não entra na conferência de
totais, não entra na amostra aleatória. É o ponto cego do §15 um nível antes:
lá o número final não era medido; aqui o arquivo nem chegava a ser lido.

### 17.2 Defeito 1 — vocabulário fechado

Três dos seis têm estrutura impecável:

```
Conta Contábil | Cod. R. | Nome da Conta | S. Anterior | Débito | Crédito | S. Atual
1.00.00.00.00000000 | 1   | Ativo        | 951.987.061,71 | ... | 1.038.290.891,22
```

`has_balance_keywords` tinha oito palavras e exigia duas. Casava **uma**:
"conta". `Cod. R.` não é "codigo"; `S. Atual` não é "saldo"; `Débito` e
`Crédito` nem estavam na lista. O portão que decide se a tabela é um balancete
dizia **não**, e `read()` devolvia `None`.

Mesmo erro do §12 noutro lugar: **nome é dica, não prova.** A correção tem
duas partes — a lista foi ampliada com o vocabulário que balancete real usa, e
ganhou uma rede sob ela, `parece_balancete()`, que julga pelo **conteúdo**:
existe coluna com códigos contábeis hierárquicos e coluna numérica? Nenhuma
planilha que não seja balancete satisfaz isso por acaso.

### 17.3 Defeito 2 — código de largura fixa

```
1.00.00.00.00000000   Ativo
1.01.00.00.00000000   CIRCULANTE
1.01.01.00.00000000   DISPONIBILIDADES
1.01.01.01.00000001   Caixa Geral
```

Todos os níveis com **cinco segmentos**. Nenhum é prefixo do outro, então
`mapear_filhos` não encontra pai nenhum: a árvore inteira vira raízes irmãs, o
rollup não é conferido, e `selecionar_para_projecao` — que evita dupla
contagem — nunca roda. Os arquivos rendiam contas e caíam em "SEM HIERARQUIA".

Segmento todo-zero é **preenchimento, não nível**. Cortando, a filiação por
prefixo volta:

```
1  ->  1.01  ->  1.01.01  ->  1.01.01.01  ->  1.01.01.01.00000001
```

**E aqui eu quebrei um arquivo que estava certo.** A primeira versão cortava
registro a registro. No `202404`, `1.5.00 CLIENTES` virou `1.5` — que já
existia como "ATIVO NÃO CIRCULANTE". Duas contas distintas colapsaram num
código só, e o rollup, íntegro, passou a divergir em **3.274.223,12**. Ali o
"00" é nível de verdade.

A decisão passou a ser do **balancete inteiro**, com dois testes baratos:

1. **largura fixa** — 80% dos códigos com o mesmo número de segmentos;
2. **sem colisão** — nenhum par de códigos distintos pode virar o mesmo.

Falhando qualquer um, nada é cortado. Não cortar devolve o comportamento
anterior; cortar errado inventa uma árvore que não existe.

### 17.4 Defeito 3 — colunas duplicadas derrubavam o parser

```
AttributeError: 'DataFrame' object has no attribute 'str'
```

`df[col]` devolve um **DataFrame** quando o rótulo se repete, e a primeira
operação de texto estoura. O código era meu, escrito no §12. Planilha de
trabalho repete cabeçalho o tempo todo — colunas de meses com o mesmo rótulo,
blocos colados lado a lado —, então não é caso de borda. As repetições passam
a ser renomeadas `nome.1`, `nome.2`, preservando a primeira ocorrência.

### 17.5 Defeito 4 — o balancete estava em outra aba

Planilha de trabalho tem dezenas de abas, e a primeira costuma ser um modelo
de saída:

| arquivo | abas | aba 0 |
|---|---:|---|
| Mascara Balancete Core | 11 | `Output Modelo (BP)` |
| SmartRio | 8 | `Balancetes 2020` |
| Mascara PCH | 20 | `Balancete (2)` |

`read()` devolvia a **primeira** aba que passasse no portão — zero contas, com
nove abas de balancete ao lado. A escolha passou a ser por **resultado**:
vence a aba de que se extraem mais contas. Nome de aba não decide: "Output
Modelo (BP)" e "Balancete mensal Jun-2026" são igualmente plausíveis pelo
nome, e só a extração distingue.

A varredura só roda quando a leitura normal foi pobre (menos de 60 contas).
Sem essa porta, ler todas as abas de todas as planilhas custaria segundos por
arquivo — preço que apareceria no app do analista, não só na suíte.

### 17.6 O resultado

| balancete | contas | agrupadores conferem | divergem |
|---|---:|---:|---:|
| IBH 18 | 109 | 46 | **0** |
| Infraestrutura Brasil III | 86 | 42 | **0** |
| Infraestrutura Brasil III-A | 102 | 48 | **0** |

Os três entram na conferência de totais com **resíduo 0,00** no Ativo e no
Passivo, e a equação contábil fecha exata nos três (convenção com Passivo
negativo). O corpus passou de 15 para **18 de 18**, sem regressão.

### 17.7 Pasta de trabalho: quem escolhe a aba é o analista

Os outros três **não são balancetes**, são pastas de trabalho:

- **SmartRio** — 8 abas, `Balancetes 2020` a `Balancetes 2026`. É série
  histórica; o template comporta cinco exercícios.
- **Mascara Core** — 11 abas, `Dez-2024` a `Jun-2026`. Export SAP com código
  plano (`110111002`), sem hierarquia — caso *description-first*, legítimo.
- **Mascara PCH** — 20 abas, incluindo `Plano de contas` e `Consolidado`.

**A decisão foi devolvida a quem a tem.** Três degraus, em ordem:

1. **Escolha explícita** (`aba=`) manda, e nada a sobrepõe.
2. **Nome inequívoco** — uma aba chamada exatamente `Balancete` é uma
   declaração do próprio arquivo, e vale mais que qualquer contagem. No
   Mascara PCH, `Balancete` e `Balancete (2)` rendem **2.275** e **1.869**
   contas: o critério "a maior" escolheria a errada, por 400 contas de
   diferença que não significam nada.
3. **Varredura por resultado**, só quando a leitura normal foi pobre
   (menos de 60 contas) — senão o custo de ler vinte abas apareceria no app.

**A tabela de marcação.** `parsers/abas.listar_abas()` levanta os candidatos
com a contagem de contas **medida** — não estimada — e o período deduzido do
nome:

| aba | contas | período |
|---|---:|---|
| Balancetes 2020 | 317 | 2020 |
| Balancetes 2021 | 513 | 2021 |
| … | | |
| Balancetes 2026 | 818 | 2026 |

A interface abre essa tabela com caixas de marcação quando — e só quando — o
arquivo tem mais de uma aba de balancete. Arquivo de aba única não pergunta
nada. Os exercícios mais recentes já vêm marcados, até o teto de cinco do
template, e marcar o sexto acende o aviso em vez de aceitar em silêncio.

**Um arquivo passa a poder ocupar vários exercícios.** `FonteBalancete` e
`service.Entrada` ganharam `aba`; a validação de duplicidade passou a olhar
`(arquivo, aba)`, não só o arquivo. A série histórica do SmartRio — cinco
exercícios de 2022 a 2026 — sai numa entrega só, com uma cópia do original por
exercício.

**Uma armadilha que o teste pegou.** A dedução do mês casava `out` dentro de
`**Out**put Modelo (BP)`: a aba de modelo ganhava "outubro" como período. A
fronteira `(?![a-z])` resolve, e os nomes por extenso ("Dezembro") passaram a
ser reconhecidos junto.

### 17.8 Quando o arquivo não é balancete: dizer, e perguntar

**Mascara Core** e **Mascara PCH** não são balancetes. A empresa **já fez a
consolidação** antes de mandar:

| arquivo | onde está o trabalho pronto | forma |
|---|---|---|
| Mascara PCH | aba `Consolidado (jun26)` | uma linha por conta do BP, **uma coluna por empresa** (IB16, IB17, PHOL, …) mais "Combinado" |
| Mascara Core | aba `Output Modelo (BP)` | De-Para em inglês (`Assets`, `Current Assets`, `Cash and Equivalents`), **períodos em colunas** |

O programa lia alguma aba desses arquivos, tirava centenas de contas e
entregava — **sem conseguir conferir nada contra a origem**, porque origem
hierárquica não havia. Entregar assim é o pior desfecho: número plausível sem
prova nenhuma por trás.

**A saída não é adivinhar melhor, é perguntar.** `diagnosticar()` responde
"este arquivo é um balancete puro?" olhando o que importa — **alguma aba rende
árvore de códigos conferível?** — e, quando não, a interface diz o motivo e
pergunta:

> *06.2026 - Mascara PCH - Balanco.vCore5.xlsx não parece um balancete puro.*
> nenhuma aba traz código de conta hierárquico — o arquivo parece um
> demonstrativo já padronizado, não um balancete.
> **Em qual aba está o balanço?** Marque até 5 — o template é preenchido do
> mesmo jeito, mas os totais não poderão ser conferidos contra a origem.

Três decisões de projeto nessa tela:

1. **Lista TODAS as abas**, não só as que passam no filtro de balancete. A
   resposta certa no PCH é `Consolidado (jun26)` — **36 linhas**, que o filtro
   normal descartaria. Perguntar sem oferecer a resposta certa é pior que não
   perguntar.
2. **Nada vem pré-marcado.** Se o programa soubesse qual aba tem o balanço,
   não estaria perguntando; marcar sozinho seria palpite com cara de resposta.
3. **A limitação é dita junto com a oferta**, não escondida no fim: o template
   é preenchido, mas rollup e totais não podem ser conferidos.

**A árvore passou a valer mais que a contagem** na escolha do recorte
(`_pontuar` devolve `(tem árvore, nº de contas)`). Escolhendo só pelo tamanho,
um recorte que perde a coluna de código vencia outro que a mantinha, e o
balancete caía em "SEM HIERARQUIA" por uma linha de cabeçalho.

**Um "não" que ninguém mediu.** A primeira versão de `e_balancete_puro`
respondia `False` para arquivo de **aba única** — porque não havia abas para
classificar. O IBH, um balancete perfeito, era declarado impuro por falta de
lista. Sem abas, o veredito passa a vir do próprio arquivo.

### 17.9 O que continua sem resposta

**As colunas de período.** Nos dois arquivos consolidados o exercício é uma
**coluna**, não uma aba: escolher a aba resolve *onde*, não *qual período*.
Hoje o leitor pega a última coluna numérica. É previsível e documentado, mas é
convenção — não escolha do analista.

**SmartRio de 2023 em diante** — *este parágrafo estava errado, ver §18.8.*
Eu havia registrado que "não há código na origem". Há: o código é **plano**,
guardado como inteiro, e o Excel o exibe com separador de milhar. Corrigido.

### 17.10 A lição

O §10 disse "não calibre contra um arquivo". O §12, "meça a propriedade, não a
contagem". O §15, "meça o número que o cliente lê". Falta o quarto:

**Um arquivo que o pipeline não lê é invisível para toda métrica.** Zero contas
não aparece como falha em cobertura, em match rate, em conferência de totais —
aparece como *ausência*, e ausência não dispara nada. A trava é
`test_nenhum_balancete_do_corpus_derruba_o_parser` mais a exigência explícita,
por arquivo, de que balancete de cliente seja lido e feche.


## 18. VIVAE: o crédito dentro do ramo de despesa

### 18.1 O que estava travado

O §16.6 deixou um `xfail(strict=True)`: o lucro líquido entregue não batia com
o resultado da origem em três dos oito balancetes conferíveis — 202404
(−216,64), ASP (−92,44) e **VIVAE (−383,13)**. Trindade e RBM batiam ao
centavo. Eu havia identificado uma das causas e registrado que a do VIVAE
**não tinha sido encontrada**.

Eram três causas distintas, e a última é a mais instrutiva.

### 18.2 A causa do VIVAE

Comparando linha a linha o que foi emitido contra a origem, o erro está numa
conta só:

| | |
|---|---|
| conta | `5.5.1.004.0001 CREDITO DE PIS E COFINS` |
| saldo na origem | **−191.565,72** |
| natureza (herdada do ramo `5.5.1`) | DESPESA |
| entregue | −191,57 mil |
| deveria ser | **+191,57 mil** |
| erro | `2 × 191,57 = 383,13` |

É um **crédito** dentro do ramo de despesas financeiras: ele *reduz* a
despesa. Classificado DESPESA pelo ramo — corretamente — e passado por
`abs() * sign_for()`, saiu negativo quando devia sair positivo.

**É o mesmo `abs()` do §15**, do outro lado. Lá eu o removi do Balanço e
argumentei que na DRE ele continuava certo, "porque sob natureza implícita
receita e despesa vêm ambas positivas". O argumento vale — para balancete de
natureza implícita. O VIVAE usa a **outra** convenção, e nela o sinal da
origem é informação.

### 18.3 A regra, agora completa

| convenção | Balanço | DRE |
|---|---|---|
| **natureza implícita** (tudo positivo) | sinal da origem, classe orientada | `abs() × sign_for(linha)` |
| **com sinal** (Passivo negativo) | sinal da origem, classe orientada | **sinal da origem** |

### 18.4 O discriminador, e o erro de ter dois

A primeira versão deduzia a convenção da DRE pelo **sinal das naturezas**:
receita e despesa com sinais opostos → origem com sinal. Parecia natural e
**quebrou**.

`Infraestrutura Brasil III` teve **lucro**. Nele, o ramo de resultado
classificado DESPESA soma **negativo** — o lucro está lá dentro. Os dois
totais ficaram com o mesmo sinal, a dedução concluiu "natureza implícita", e a
referência saiu invertida: origem −8.598,15 contra entrega +8.673,38, acusando
**17,27 milhões de erro numa entrega correta**.

O defeito de fundo era ter **dois sinais para a mesma pergunta**: o Balanço
olhava o Passivo, a DRE olhava as naturezas. O Passivo não compensa receita
com despesa, e por isso responde certo mesmo em ano de lucro. Passou a ser o
discriminador único do arquivo:

```python
def _origem_com_sinal(hierarquia) -> bool:
    return hierarquia.totais_por_classe.get("PASSIVO", 0.0) < 0
```

### 18.5 As outras duas causas: era a régua

ASP (−92,44) e 202404 (−216,64) **não eram defeito da entrega**.

A referência da origem vinha de `|receitas| − |despesas|`, calculada sobre o
mapa de naturezas. No ASP, os ramos `3 RESULTADO LÍQUIDO DO PERÍODO ANTES DO
IRPJ` e `4 IMPOSTOS E PARTICIPAÇÕES SOBRE O LUCRO` **não declaram natureza
nenhuma** — ficam fora do mapa. A entrega subtraía o IRPJ/CSLL corretamente; a
referência é que deixava 86,73 mil de fora.

Com origem com sinal, a referência passou a ser `-(total da classe RESULTADO)`,
que **não passa pelo mapa de naturezas** e por isso não tem esse buraco. E a
identidade ganhou o termo que faltava, igual à do Balanço:

```
entrega + não coberto == resultado da origem
```

### 18.6 O resultado

| | antes | depois |
|---|---|---|
| DRE bate (origem íntegra) | 5 de 8 | **16 de 16** |
| Balanço bate | 15 de 15 | **18 de 18** |
| `xfail` da DRE | travado | **removido** |

`BuildResult.dre` entrou na entrega: o Sumário mostra o lucro líquido do
balancete contra o entregue, e `balanco_confere` passou a exigir os dois. Um
Balanço que fecha com a DRE errada deixa de ser reportado como "OK" — era
exatamente o que acontecia quando R$ 4,9 milhões de receita entravam como
custo (§16) e o ATIVO TOTAL continuava correto.

### 18.7 A lição

O §15.10 dizia: *meça o número que o cliente lê, não a etapa anterior a ele*.
Faltava o corolário: **quando a medida acusa erro, o suspeito é a régua tanto
quanto o dado**. Das três divergências travadas no xfail, **duas eram da
comparação**. Se eu tivesse "corrigido" a entrega para bater com a referência
errada, teria quebrado dois arquivos corretos para fazer um teste ficar verde.


### 18.8 O código plano: eu disse que não havia, e havia

O revisor estranhou o §17.9 e mandou a tela do SmartRio. Ele estava certo.

O que eu li como "a coluna Conta traz texto" era a **primeira linha** da aba.
Abaixo dela:

| `Conta` | `Nome` | `No.` |
|---:|---|---:|
| 1 | ATIVO | 1 |
| 101 | ATIVO CIRCULANTE | 3 |
| 10101 | CAIXA E EQUIVALENTES DE CAIXA | 5 |
| 10101001 | CAIXA GERAL | 8 |
| 101010010001 | GALPAO 1 | 12 |

O código é **plano, guardado como inteiro**. O Excel exibe `101.010.010.001`
com separador de milhar, o que faz parecer código pontuado. E a coluna `No.` é
literalmente a **contagem de dígitos** — o marcador de nível.

O pai de `101010010001` é `10101001`: prefixo direto. Medido: **97,9% das
contas têm o pai presente** em 2023 e 95,9% em 2025. A árvore sempre esteve
lá, invisível para quem procura ponto.

**A correção.** `detectar_niveis_planos` deduz as larguras do próprio balancete
— `(1, 3, 5, 8, 12)` — e `pontuar_codigo_plano` converte para
`1.01.01.001.0001`. Pontuar em vez de comparar prefixos direto é o que faz o
resto do pipeline funcionar sem mudança nenhuma: nível, classe contábil,
mapeamento de filhos e seleção da projeção já falam essa língua.

**Duas travas, ambas descobertas errando.**

*Numeração de linha vira hierarquia.* Inteiros consecutivos formam prefixos por
acidente — "1" é prefixo de "12", que é de "123". A coluna `n`, de 1 a 668, foi
promovida a código de conta e o rollup divergiu em **65 agrupadores com somas
de bilhões**. Contador é denso e contíguo; código de conta tem buracos enormes
(668 códigos espalhados até 999999999999).

*Escolher o nível por frequência apaga o topo do plano.* Um plano real tem três
ou quatro contas de nível 1 (Ativo, Passivo, Receitas, Despesas) contra
centenas de folhas; um piso de frequência as descarta. O que define um nível
não é quantos códigos ele tem, é **quantos filhos encontram pai nele**.

E dentro dessa regra, uma sutileza que custou outra rodada: escolher "o
ancestral mais bem coberto" **pula os níveis intermediários**, porque a
cobertura é monótona — se o prefixo de 8 dígitos existe, o de 5 também existe.
O certo é o **ancestral mais próximo que cobre**. Errar isso levou de 162
agrupadores conferindo para 6.

| exercício | antes | depois |
|---|---|---|
| Balancetes 2023 | SEM HIERARQUIA | **162 conferem / 6 divergem** |
| Balancetes 2025 | SEM HIERARQUIA | **191 / 3** |
| Balancetes 2026 | SEM HIERARQUIA | **183 / 9** |

Balanço 18/18 e DRE 16/16 seguem intactos.

**A lição.** Eu não só deixei de ler o arquivo: **documentei a minha falha de
leitura como propriedade do dado** — "não há código na origem, é o dado, não o
parser". É a pior forma de errar, porque fecha a investigação. O §19 registra
o padrão de medir a coisa errada; este registra o seguinte: *quando a conclusão
é "o dado é que é assim", o ônus da prova sobe, não desce.*


### 18.9 O total certo com a repartição errada

Conferindo um arquivo a pedido do revisor — ele havia rodado e recebido saída
vazia —, apareceu isto:

| | origem | entrega |
|---|---:|---:|
| Ativo Circulante | 652,56 | **20,77** |
| Ativo Não Circulante | 282.048,64 | **282.680,44** |
| **ATIVO TOTAL** | 282.701,21 | **282.701,21** ✓ |

O total bate ao centavo e a repartição está errada: 631,79 mil de circulante
entregues como não circulante. **O total esconde, porque ele é a soma.**

Medido no corpus: **9 de 18** balancetes entregavam o Circulante errado, um
deles deslocando **R$ 28,7 milhões**. Nenhum teste pegava — a conferência do
§15 olha os totais de topo, e liquidez é metade da leitura de um balanço.

**Duas causas.**

*O eixo que faltava.* `Aplicação Financeira - CDB` — conta do circulante —
casou com `1.02.03.01` (Imobilizado). É o mesmo padrão do §16, um nível mais
fundo:

| eixo | separa |
|---|---|
| Plano C (classe) | ATIVO / PASSIVO / RESULTADO |
| `utils.natureza` | RECEITA / DESPESA, dentro de RESULTADO |
| **`utils.prazo`** | **CIRCULANTE / NÃO CIRCULANTE, dentro de ATIVO e PASSIVO** |

No plano referencial o prazo se lê do **código** (a RFB é explícita: `1.01`
circulante, `1.02` não circulante); no balancete, da **árvore**, como a
natureza. `2.03` (Patrimônio Líquido) devolve `None` de propósito — restringir
o PL por prazo excluiria os alvos certos.

*A raiz de classe parando o corte.* Pior, e já existia. Num balancete real o
Ativo **inteiro** — R$ 197.840.840 — era emitido numa linha só, casada com
"Outros ativos circulantes". A regra 2 de `selecionar_para_projecao` ("se o nó
é mapeado, para nele e absorve os filhos") é certa para um agrupador de
verdade e desastrosa para "ATIVO": raiz de classe é totalizador, e o template
calcula os totais sozinho. O Balanço até fechava; a leitura era ficção.

| | antes | depois |
|---|---:|---:|
| Ativo Circulante bate | 9 de 18 | **18 de 18** |
| Balanço | 18/18 | 18/18 |
| DRE | 16/16 | 16/16 |

**A lição, e é a terceira vez que ela aparece com outra roupa.** O §15 disse
"meça o número que o cliente lê". O §18.7 acrescentou "quando a medida acusa
erro, o suspeito é a régua tanto quanto o dado". Falta este: **um total que
fecha não prova que as partes estão certas.** A soma é indiferente a como o
valor se reparte entre as linhas — e é a repartição que o cliente lê.


## 19. Sobre o asterisco: o que eu errei, em ordem

O revisor afirmou, categoricamente, que o asterisco estava fazendo mal ao
balancete, e mostrou a fórmula e o resultado. Eu respondi que a medição não
confirmava. Ele estava certo sobre a existência do defeito; eu estava medindo
a coisa errada. O histórico, porque o processo importa mais que a conclusão:

**Erro 1 — medi a coluna, não a fórmula (§13.2).** Li a coluna C como se fosse
o critério do SUMIFS. Ela traz vários códigos unidos por `|`; o critério está
dentro da fórmula. Achei 7 linhas perdidas que não existiam.

**Erro 2 — corrigi a medição e parei na pergunta errada (§13).** Passei a
perguntar "quantas linhas do template capturam cada linha escrita?". A
resposta — exatamente uma — estava certa, e eu a apresentei como se
respondesse a preocupação dele. Não respondia. A pergunta certa era *"quanto
dá o Ativo no final?"*.

**Erro 3 — apresentei ausência de evidência como evidência de ausência.**
Escrevi "hoje o asterisco não gera dupla contagem". O que eu tinha era: uma
métrica que não olhava para o total final não acusou nada.

**O que a pergunta certa achou.** Ativo entregue 2.683.506,57 contra
2.361.053,53 na origem — **R$ 322.453,04 a mais**, e o defeito não era o
asterisco: era o `abs()` apagando o sinal das contas redutoras (§15.3). Dois
mecanismos diferentes, o mesmo sintoma que ele viu na tela.

**A lição que fica registrada.** Quando alguém aponta um número errado na
saída, a obrigação é reproduzir **aquele número**, não validar o mecanismo que
eu suspeito. Métrica intermediária verde não é resposta a um total errado — é
mudança de assunto. E foi por isso que o defeito sobreviveu a 446 testes: eles
todos mediam etapas anteriores ao número que o cliente lê.


## 20. O que NÃO foi alterado, e por quê

- **Os módulos gigantes** (`conta_matcher.py` 752, `xlsx_exporter.py` 719,
  `trainer.py` 712). `ARQUITETURA.md` §5 é explícito: dividi-los antes de
  arrumar as abstrações de fluxo só espalha o spaghetti. Ver §11, itens 5–6.
- **`review_wizard.py`, `apply_llm_mappings.py`, `plano_referencial.py`** —
  0% de cobertura, intocados. Mexer sem rede seria o oposto do que esta revisão
  defende.
- **Os 2 skips** no ambiente completo (`test_pdf_ocr.py`) dependem do binário
  Tesseract, ausente aqui. No núcleo somam-se 4 de módulos que exigem os
  extras — todos legítimos.
- **Os ~53 achados de ruff em `tests/`** e ~28 nos scripts da raiz: são
  pré-existentes e cosméticos (`W293`, `I001`, `F401`). Corrigi-los agora
  poluiria o diff. Os arquivos tocados nesta rodada passam limpos.
- **A pergunta de empacotamento do §5f** precisa de uma decisão de produto
  antes de virar código.

---

## 21. A coluna de saldo errada, e o verde que a escondia

### O pedido

> "Olha o 2021 na sequência."

A aba `Balancetes 2021` do arquivo SmartRio conferia **62 pais e divergia em
74** — o pior número de toda a série de sete exercícios. Fui olhar, e o
problema não estava na hierarquia.

### O que a aba de 2021 tem

```
n | Codigo | Codigo1 | Codigo2 | No. | Código | Classificação | Descrição | 2020-12 | ... | 2021-12 |  | 100
1 |        |         |         |  2  |   1    | 1.            | ATIVO     | 59.472.554,37 | ... | 1.077.464.672,19 |  | 100
```

A última coluna tem o valor **100 em todas as 513 linhas**. É uma coluna
auxiliar da planilha. E o critério de escolha da coluna de valor era, literal:

```python
# Return last numeric column (usually the saldo)
if numeric_columns:
    return numeric_columns[-1]
```

*A última coluna numérica.* Era essa. **Todas as 513 contas do exercício de
2021 chegavam com saldo = 100,00.**

Daí os 62 pais que "conferiam": são exatamente os pais de filho único —
100 == 100. E os 74 divergentes são os de dois ou mais filhos: um pai com 124
filhos declarava 100 e somava 12.400.

### O mesmo defeito, na outra forma

Com a coluna auxiliar identificada, varri as sete abas. Duas estavam piores:

| aba | contas | contas com saldo lido |
|---|---|---|
| Balancetes 2024 | 774 | **1** |
| Balancetes 2025 | 824 | **3** |

Nessas duas, a coluna escolhida era uma **coluna-fantasma à direita do último
mês** — sobra de planilha, com três valores em 825 linhas. Como o critério
amostra `dropna().head(20)`, uma coluna com três valores numéricos passa no
filtro de "70% numérica" tão bem quanto uma com 825.

### O terceiro defeito: por que ninguém viu

Este é o que importa. O relatório de hierarquia da aba de 2025, com 821 de 824
contas sem valor nenhum, dizia:

```
824 contas | 184 pais conferem, 3 divergem | equação contábil fecha
```

**Verde.** Porque `_saldo()` devolve `0.0` para saldo ilegível — e então todo
pai bate com a soma dos filhos (0 == 0) e a equação contábil fecha (0 == 0).
Quanto menos o programa lê, mais perfeito ele se declara.

É o §15 outra vez, um nível antes, e é o ponto que o cliente vem repetindo:
"são trezentos, quatrocentos testes, mas ele não testa o core da coisa". Aqui
o core não era só não-testado — era **anti-testado**: a falha total produzia o
melhor relatório possível.

### As três correções

1. **`_find_saldo_column` recusa coluna degenerada**
   (`dispatcher._coluna_informativa`). Duas formas de uma coluna não ter
   informação de saldo: preencher menos de 20% das linhas (a coluna-fantasma) ou
   ter **um único valor distinto** em 10+ linhas (a coluna de `100`). Se
   nenhuma coluna numérica sobreviver ao filtro, o comportamento anterior volta
   — a guarda estreita a escolha, não pode zerá-la.

2. **`RelatorioHierarquia.saldos_legiveis`.** Metade das contas precisa ter
   trazido saldo para que qualquer conferência valha. `rollup_integro` e
   `equacao_fecha` passam a ser falsos sem isso, e `resumo()` diz
   `SEM SALDO LEGÍVEL`. Zero continua sendo saldo; `None` é ausência.

3. **`_pontuar` normaliza antes de conferir.** Achado de tabela: o rótulo das
   abas no diálogo de seleção dizia "já padronizado" para quatro dos sete
   exercícios. A pontuação existe para preferir o recorte **com árvore**, mas
   `parse()` só aplica `normalizar_registros` no fim — então a pontuação
   enxergava os códigos crus. Num plano plano (`1`, `101`, `10101`) não há
   ponto nenhum antes da normalização: a árvore marcava 0. Ver §18.8.

### Medido

| | antes | depois |
|---|---|---|
| Balancetes 2021 | 62 conferem / 74 divergem | **136 conferem / 0 divergem**, equação fecha |
| Balancetes 2024 | 1 conta com saldo em 774 | 774, com 400 saldos distintos |
| Balancetes 2025 | 3 contas com saldo em 824 | 824, com 456 saldos distintos |
| abas rotuladas "balancete" | 3 de 7 | **7 de 7** |

Repare que 2024 **piorou** na aparência: passou de "equação contábil fecha"
para "NÃO fecha (12.993.522,51)". É a correção funcionando. O verde anterior
era 0 == 0.

### O que fica aberto

Nas abas de 2024/2025/2026 sobram 7 a 10 agrupadores divergentes, e a causa é
outra: o plano de contas dessa origem tem **linhas de reapresentação**. O
mesmo sintético aparece duas vezes, com códigos de larguras diferentes:

```
    10104  ESTOQUES         47.269.629,89
  1010401  ESTOQUES         47.269.629,89   <- reapresentação
101040010002  ALMOXARIFADO  44.867.835,71
```

A grade de níveis dessa origem é (1, 3, 5, 8, 12) — e ela mesma a declara, na
coluna `No.`, que traz o comprimento do código em cada linha. `1010401` tem 7
caracteres: está **fora da grade**. Segmentado pela grade vira `1.01.04.01`,
irmão da subárvore de folhas que também pendura em `1.01.04` — e o pai soma
**exatamente o dobro** do que declara.

Não corrigi porque a regra segura ainda não está clara: das cinco linhas fora
da grade por aba, duas são reapresentação pura (mesma descrição, mesmo valor),
duas têm a mesma descrição e valor diferente, e uma (`60402003004`) é folha
legítima com o último segmento sem o zero à esquerda. Descartar as cinco
perderia dinheiro; descartar só as idênticas resolve 2 dos 10 casos. A coluna
`No.` da origem é a pista boa — ela diz o nível de cada linha sem adivinhação —
mas usá-la exige decidir o que fazer com o que ela contradiz.

Cheguei a medir uma regra candidata — *descartar o código fora da grade cuja
descrição é idêntica à do ancestral na grade e que não tem filhos próprios*:

| aba | antes | com a regra |
|---|---|---|
| Balancetes 2023 | 162 / 6 | 165 / 3 |
| Balancetes 2024 | 179 / 7 | 183 / 3 |
| Balancetes 2025 | 184 / 10 | 188 / 6 |
| Balancetes 2026 | 183 / 9 | 187 / 5 |

Melhora, e não resolve. Pior: numa das linhas que ela descartaria
(`1020601 ATIVO ARRENDAMENTO - IFRS16`, 7.292.667,75) o ancestral declara
**2.420.484,52** — os dois discordam, então um dos dois está errado e a regra
escolheria sem prova qual. Descartar ali é apagar 7,3 milhões por heurística de
texto. Pela regra do §10, não entra: o critério não pode ser calibrado contra
este arquivo.

**Enquanto isso, a divergência aparece no relatório.** É o comportamento certo
para um defeito não resolvido: ruidoso, não silencioso.

---


## 22. O repositório público subiu sem o pacote da entrega

Achado ao abrir `fernandolvlisboa/MAPA_v0.8` — a release pública. Ela é este
branch, arquivo a arquivo (160 idênticos), mais o empacotamento do PLANO K e
os READMEs por módulo. Menos uma coisa: **o pacote `src/bp/output/` inteiro**.

### A causa

A limpeza que preparou o repositório público acrescentou ao `.gitignore` uma
regra para não versionar a pasta de saída:

```
output/
```

Sem barra inicial, o padrão casa **qualquer** diretório com esse nome em
qualquer profundidade. E existe um:

```
$ git check-ignore -v src/bp/output/build_gt_output.py
.gitignore:58:output/	src/bp/output/build_gt_output.py
```

Foram junto `build_gt_output.py`, `origem.py`, `template_map.py` e o
`__init__.py`.

### O efeito

```
$ pytest --collect-only
ERROR tests/test_captura_template.py
ERROR tests/test_copia_original.py
ERROR tests/test_gt_output.py
ERROR tests/test_integridade_entrega_gt.py
ERROR tests/test_totais_da_entrega.py
E   ModuleNotFoundError: No module named 'src.bp.output'
```

E não é só teste. `service.py:387` e `main.py:121` importam `bp.output` de
forma **tardia** — então o programa abre normalmente, lê o balancete, mostra
a interface, e morre exatamente na hora de gerar o Template GT.

### Por que nenhum teste pegou

Porque o defeito não está no código. Está no que o código **não chegou a
ser**. Toda a suíte roda sobre a árvore local, e localmente o arquivo está
lá — só o git não o leva. É uma classe de defeito que nenhuma asserção sobre
comportamento alcança: a pergunta certa não é "isto funciona?", é "isto vai
junto quando eu empurrar?".

`tests/test_codigo_versionado.py` faz essa pergunta ao próprio git, e nomeia o
arquivo **e a linha do `.gitignore`** que o engole. Confere também o lado
oposto: dado de cliente tem de continuar ignorado.

### A segunda metade: a suíte pública abria vermelha

Com o pacote de volta, ainda: **26 falhas e 22 erros**. Causa diferente, mesma
família.

Os testes de corpus separavam "ausente por design" de "bug" pela **existência
do diretório** `data/samples`. Mas `data/samples/README.md` é versionado —
então o diretório existe no clone público, o corpus (que é dado de cliente)
não, e todo teste de corpus **falhava em vez de pular**.

São três estados, e faltava o do meio:

| estado | veredito |
|---|---|
| diretório inexistente, **ou existente e vazio de balancetes** | `skip` |
| corpus presente, arquivo nomeado ausente | `fail` — é caminho errado no teste |
| arquivo presente | devolve o caminho |

O `fail` do meio é o guard que pegou um nome de arquivo que eu tinha
inventado (§18) e não pode ser afrouxado. Quem decide agora é o **conteúdo**
do diretório: `conftest.corpus_disponivel()`.

Os sete testes de `test_gt_output.py` que geram a entrega de verdade ganharam
`@requer_balancete`.

### Medido

| | antes | depois |
|---|---|---|
| MAPA_v0.8 (público) | 5 erros de coleta; 26 failed, 22 errors | **428 passed, 139 skipped, 0 failed** |
| BP (com corpus) | 613 passed | **615 passed, 7 skipped, 2 xfailed** |

Os 139 skips do repositório público são os testes que dependem de balancete de
cliente — ausente por design (`docs/DADOS_PRIVADOS.md`). Não é verde vazio: é
verde declarado, e cada skip diz o motivo.

### O que continua aberto

Os **8 balancetes de cliente** rastreados em `src/bp/training/DFS_Exemple/`
neste repositório (o privado). O `.gitignore` agora impede que **novos**
entrem, mas `.gitignore` não desrastreia o que já está no índice, e o
histórico guarda o que já foi commitado. Os três caminhos de remediação estão
em `docs/DADOS_PRIVADOS.md`. O repositório público está limpo — a verificação
é `git ls-files | grep -iE "\.(xlsx|xls|csv|pdf)$"`, que lá devolve só
exemplos sintéticos, o template e o plano master.

---


## 23. O `.exe` saiu sem a biblioteca do arrastar-e-soltar

Relatado por quem recebeu o binário da v0.8: **arrastar o arquivo para a janela
não traz nada.** O executável compilado no repositório privado funcionava.

### A causa

`tkinterdnd2` são dois pedaços:

| pedaço | o que é | o PyInstaller acha sozinho? |
|---|---|---|
| `__init__.py`, `TkinterDnD.py` | módulo Python | sim, por importação |
| `tkdnd/<plataforma>/` (`.dll` + `pkgIndex.tcl`) | extensão Tcl | **não — é dado** |

O `bp.spec` declarava só `hiddenimports = ["tkinterdnd2"]`, com um comentário
que já admitia a dúvida: *"o hook oficial cobre, mas nomear aqui evita variação
entre versões"*. Nomear o módulo **não traz a pasta**. No binário distribuído:

```
TkinterDnD.Tk()
  -> tkroot.tk.call('package', 'require', 'tkdnd')
  -> TclError -> RuntimeError('Unable to load tkdnd library.')
```

`app/dnd.py` capturava com `except Exception: pass`, caía para o `tkinter.Tk`
puro, e a janela abria com a zona de soltar virada em botão. O build é
`console=False`: **nenhuma mensagem, nenhum log, nenhuma pista.**

### Por que nenhum teste podia ter pego

Na máquina que compila, `tkinterdnd2` está instalado e tudo funciona. O defeito
só existe **dentro do bundle**. É a mesma família do §22 — o código está certo,
o que falha é o que foi (ou não foi) empacotado — e a lição se repete: só o
conteúdo do artefato responde a pergunta.

### As correções

1. **`bp.spec` embarca a árvore `tkdnd`** (113 arquivos, 2,5 MB), declarada em
   vez de herdada de hook. Todas as plataformas entram de propósito:
   `_require()` escolhe a pasta em runtime por `platform.system()`,
   `PROCESSOR_ARCHITECTURE` e versão do Tcl. Filtrar pela máquina que compila é
   a mesma aposta que produziu o defeito. Usa `find_spec` em vez de `import`
   para não morrer numa máquina sem `tkinter`.
2. **`dnd.motivo_indisponivel` / `dnd.diagnostico()`** — a razão da queda
   sobrevive ao `except`.
3. **`ui.py`** diz *"arrastar-e-soltar indisponível nesta máquina"* em vez de só
   oferecer o clique, e põe o motivo técnico no rodapé da zona.
4. **`test_build_seguranca.py`** audita o binário: a pasta `tkdnd` tem de estar
   lá, com `pkgIndex.tcl`, com a biblioteca nativa, e com a variante da
   plataforma para a qual o `.exe` foi compilado.
5. **`build.py` para** quando `pyinstxtractor-ng` falta, em vez de deixar a
   auditoria pular calada. Build não auditado não sai.

### A regra que fica

Um `.exe` tem duas superfícies de falha: o que o código faz, e o que o
empacotamento leva. A suíte cobria a primeira e era cega para a segunda em
tudo que não fosse vazamento de dado de cliente. Agora a auditoria pergunta as
duas coisas — o que **não pode** entrar, e o que **tem** que entrar.

---

## 24. `pandas.plotting`: eu excluí do bundle um módulo que o pandas carrega

O `.exe` foi distribuído. Os usuários abriram, arrastaram o balancete, e na
hora de gerar:

```
Não deu para gerar
Não consegui carregar o motor do BP: No module named 'pandas.plotting'
```

### A causa, e o comentário que a escondia

`bp.spec` excluía do bundle:

```python
"pandas.tests", "pandas.plotting", "pandas.io.sql",
```

sob este comentário:

> *Cada exclusão foi verificada: nenhum import de `src/bp/app`,
> `src/bp/output`, `src/bp/parsers`, `src/bp/matchers` toca esses módulos.*

**A verificação estava certa. A conclusão, errada.** O que decide não é se
*nós* importamos o módulo — é se a *biblioteca* importa. E `pandas/__init__.py`,
linha 138:

```python
from pandas import api, arrays, errors, io, plotting, tseries
```

Medido: `import pandas` carrega `pandas.plotting` **e**, via `pandas.io.api`,
`pandas.io.sql`. Eram **duas** exclusões fatais, não uma — a segunda apareceria
logo depois de corrigir a primeira.

### Por que só apareceu na mão do usuário

Duas camadas de atraso, somadas:

1. **A suíte roda sobre a árvore de código**, onde o pandas está inteiro. Os
   617 testes verdes não diziam nada sobre o bundle.
2. **O motor é importado tarde.** `service.py` só importa `build_gt_output`
   quando o analista clica em Gerar. A janela abre, aceita o arquivo, mostra o
   cliente — e quebra na última etapa, com o trabalho já feito.

### O padrão, agora na terceira repetição

| § | o que falhou | o que a suíte cobria |
|---|---|---|
| 22 | `.gitignore` engoliu `src/bp/output/` | o código, não o repositório |
| 23 | `bp.spec` não levou a extensão `tkdnd` | o código, não o bundle |
| 24 | `bp.spec` excluiu módulo que o pandas carrega | o código, não o bundle |

Três vezes o mesmo enunciado: **o código estava certo; o que falhou foi o
artefato.** E as três vezes eu respondi construindo uma auditoria mais fina do
*conteúdo* do artefato — o que não fecha o buraco, porque conteúdo correto não
é o mesmo que artefato que funciona.

### As duas correções

1. **A lista de exclusões passa a ser medida, não raciocinada.**
   `tests/test_excludes_do_bundle.py` importa o que o app importa em runtime,
   num processo separado, e reprova qualquer nome da lista que tenha ido parar
   em `sys.modules`. Roda na suíte normal, sem compilar nada. Antes de
   acrescentar um nome aos `excludes`, o teste tem de continuar verde.

2. **O `.exe` prova que roda antes de sair.** `MAPA.exe --autoteste`
   (`src/bp/app/autoteste.py`) monta um balancete sintético, chama o
   `build_gt_output` de verdade sobre o template embarcado e confere que a
   entrega saiu com as abas obrigatórias. `build.py` roda isso no binário
   recém-compilado e **falha o build** se não passar. Em uma passada, exercita
   o que quebrou nas três vezes: `import pandas` completo, o pacote
   `src/bp/output` presente, os recursos do `bp.spec`, e o caminho de
   importação tardia do `service.py`.

### A regra que fica

Auditar o conteúdo do artefato é necessário e não é suficiente. **Um `.exe` só
se prova rodando** — e a prova tem de acontecer antes da distribuição, no mesmo
comando que o gera, sem depender de alguém lembrar de testar.

### E o caminho da distribuição

A prova só vale se estiver no caminho por onde o binário sai. Por isso o `.exe`
deixou de ser commitado (55 MB por build, e o histórico do git não encolhe
depois) e passou a sair por **GitHub Release**, publicada pelo workflow
`.github/workflows/release.yml`: `push` de tag `v*` → runner Windows →
`pytest` → `build.py` (compila, audita, autotesta) → Release com o `.exe`
anexado. Cinco a oito minutos, nenhum passo manual, e **falhou qualquer coisa,
não há Release**.

`tests/test_excludes_do_bundle.py` fecha o círculo: reprova se `dist/` voltar a
ser versionado, se o workflow deixar de chamar o `build.py` ou o `pytest`, ou
se o gatilho por tag sumir. O portão que só existe por convenção não é portão.

---

## 25. O portão reprovou um binário bom — e o handle que ficou aberto

O `build.py` recusou o `.exe` com "NAO DISTRIBUA". O relatório do usuário:

```
PermissionError: [WinError 32] O arquivo já está sendo usado por outro processo:
  '...\Temp\tmpb0r3002f\autoteste_balancete.xlsx'
  File "src\bp\app\autoteste.py", line 101, in executar
    with tempfile.TemporaryDirectory() as tmp:
```

Leia onde estourou: **`__exit__`**. O pipeline inteiro tinha passado — ler,
casar, projetar, escrever. O que falhou foi apagar a pasta temporária, depois
de tudo dar certo. **O portão reprovou um binário correto por causa da faxina
do próprio portão.**

### O defeito de verdade, que estava embaixo

O `WinError 32` não é capricho do Windows: alguém segurava o arquivo. Três
lugares abriam `pd.ExcelFile(...)` e nunca fechavam:

```python
abas = pd.ExcelFile(self.file_path).sheet_names   # dispatcher, 2 sítios
nomes = pd.ExcelFile(caminho).sheet_names          # abas.py
```

Sem `with`, o handle vive até o coletor de lixo passar. No Linux ninguém nota —
apagar arquivo aberto é permitido. No Windows, **o balancete do cliente fica
preso**: depois de processar, quem tentasse mover, renomear ou apagar o arquivo
era barrado até fechar o programa. Nunca apareceu na suíte porque a suíte roda
em Linux.

O autoteste não causou o defeito. Ele foi o primeiro a exercitar o caminho num
Windows e a exigir apagar o arquivo logo em seguida.

### As duas correções

1. **Os três `pd.ExcelFile` viram `with`.** É o bug do produto, e vale para
   quem usa o programa, não só para o build.

2. **`autoteste.executar()` nunca levanta.** Um portão que explode não reprova
   o binário — impede que ele seja avaliado, e o build para sem dizer se o
   programa funciona. Agora o corpo roda dentro de um `try`, e uma falha do
   próprio teste devolve um relatório que diz, com todas as letras, que aquilo
   *não é um veredito sobre o binário*. A pasta temporária usa
   `ignore_cleanup_errors=True`: apagá-la nunca foi o que este teste verifica.

### A regra que fica

Já sabíamos que auditar o conteúdo do artefato não basta (§24). Agora: **um
portão precisa distinguir "o que eu meço está ruim" de "eu quebrei"** — e dizer
qual dos dois. Sem essa distinção, ele para a entrega com a mesma cara nos dois
casos, e quem lê conclui a coisa errada sob pressão.

Vale a pena registrar a coincidência: a mensagem que o build imprimiu sugeria
`excludes` do `bp.spec` como causa típica. Era um palpite meu, escrito no §24,
e apontava para o lugar errado. **Mensagem de erro que adivinha a causa atrasa
quem está depurando** — o traceback já estava ali, e dizia outra coisa.

---

## 26. A entrega que saía limpa sem ter sido conferida

Medindo o corpus inteiro (COM e SEM o aprendizado, para responder se o cache
generaliza), apareceu um defeito pior que o da pergunta: **três balancetes
entregavam sem conferir nada, e um deles saía com cara de perfeito.**

`Balancete Real Life`: 96 linhas escritas, `captura_integra` verdadeiro, zero
avisos. Nenhuma palavra de que o balanço nunca fora checado. O motivo é
legítimo — o arquivo não traz código hierárquico (a hierarquia é por
indentação), então não há totalizador de classe para comparar —, mas o
silêncio não é: quem recebe lê uma entrega que parece validada.

Era o único caso em que o programa mentia por omissão. É o oposto exato da
regra que o próprio cliente formulou: *"entrega sem conferência é o único caso
em que o programa mente."*

### A correção (Fix A, universal)

Quando `conferir_totais` ou `conferir_dre` não conseguem rodar
(`conferivel=False`), a entrega passa a carregar um aviso alto:

> O TOTAL DA ENTREGA NÃO FOI CONFERIDO contra a origem (…). Não há garantia de
> que o Ativo entregue é o Ativo do balancete — confira à mão antes de usar.

Vale para todos os balancetes inconferíveis, não só os três. Um balancete que
CONFERE não ganha o aviso — testado dos dois lados para a mensagem não virar
ruído.

### O teste que estava errado junto

O harness de amostra aleatória exigia o aviso "BALANCETE DE ORIGEM não fecha"
sempre que `rollup_integro` fosse falso. Mas `rollup_integro` é falso por
**dois** motivos: a árvore diverge, ou não há árvore. O `Balancete JRMA`, um
CSV plano sem hierarquia, caía no segundo caso — e ele avisa, alto, por outro
caminho ("TOTAL DA ENTREGA NÃO BATE"). O teste falhava só em certas sementes,
escondido atrás do `BP_SEED` fixo.

A invariante correta é uma só, e agora é ela que o teste exige: **entrega
inconsistente tem de avisar — por qualquer mecanismo aplicável — nunca em
silêncio.** Resíduo diferente de zero acompanhado de aviso é divergência
honesta; sem aviso, é valor inventado ou perdido calado, e continua sendo o
pior caso.

### O que isto não resolve

Avisar que não conferiu é honestidade, não capacidade. Os três arquivos
continuam entregando sem conferência de verdade, cada um por um motivo
diferente — Real Life (hierarquia por indentação), mlb bal ecd (plano flat sem
totalizador), 2024-Ultimo.csv (coluna de saldo não lida). Fazê-los conferir é
trabalho de parser, tratado a seguir, um de cada vez e medido.

---

## 27. Balancete indentado: a hierarquia que estava na coluna, não no código

Primeiro dos três que entregavam sem conferir (§26). `Balancete Real Life` é um
formato **comum** no Brasil: o sistema exporta sem coluna de código
hierárquico e mostra a árvore pela **indentação** — a descrição de cada conta
fica numa coluna mais à direita conforme a profundidade.

```
col 5   ATIVO
col 7     ATIVO CIRCULANTE
col 9       DISPONÍVEL
col 10        CAIXA
col 11          CAIXA GERAL
col 10        BANCOS CONTA MOVIMENTO
```

O "Código" que o arquivo traz é numeração de linha (1, 2, 3, 646, 9…), inútil
como árvore. Sem código hierárquico, o programa caía em "SEM HIERARQUIA" e a
entrega saía sem ser conferida.

### A reconstrução, e a régua que a valida

`parsers/indentado.py` lê a grade crua, descobre a **banda de indentação** (as
colunas onde as descrições aparecem) e numera a árvore por outline: cada nível
mais fundo vira um segmento a mais. `CAIXA GERAL` acima vira `1.1.1.1.1`. O
código sintético é hierárquico de verdade — o pai é prefixo do filho — então o
pipeline inteiro funciona sem mudança.

**A reconstrução só é aceita se o rollup fechar.** É a mesma régua do resto da
suíte: um balancete indentado real tem o pai valendo a soma dos filhos, e a
numeração por outline preserva isso. Se a árvore reconstruída não fecha, não é
um balancete indentado — a função devolve `None` e o caminho normal segue. Por
isso é um **fallback puro**: só roda quando o caminho normal não achou árvore,
e só vale quando fecha. Medido no corpus: transformou o Real Life (`.xls` e
`.xlsx`) em 52 pais conferindo, 0 divergindo, ATIVO batendo ao centavo — e
**não tocou em nenhum** dos balancetes que já conferiam (RBM, SPEZZIA, VIVAE,
SmartRio, os Infraestrutura), nem resgatou os que genuinamente não têm árvore.

### O defeito que quase passou: nome com dígito não é valor

A primeira versão usava `parse_saldo` para decidir "esta célula é descrição ou
valor?". Mas `parse_saldo` é frouxo de propósito (para ler "R$ 1.820,20"), e
`parse_saldo("BS2 EMPRESAS")` devolve **2.0** — extrai o dígito de dentro do
texto. `"C6 BANK"` vira 6, `"B2W"` vira 2. Nomes de banco e empresa com número
no meio são comuns, e cada um fazia a conta **desaparecer**: a célula era tomada
por coluna de valor e a linha descartada. No Real Life sumia "BS2 EMPRESAS"
(1.820,20), e o rollup do pai deixava de fechar por esse exato valor — o teste
pegou.

A regra rígida: **valor não tem letra.** Se sobra qualquer caractere alfabético,
é descrição. É o mesmo erro do §21 numa forma nova — a régua frouxa que engana —
e o rollup foi de novo quem denunciou.

---

## 28. O CSV que lia a numeração de linha como código — e o número ambíguo

Terceiro dos três de §26. `Balancete 2024 -Ultimo.csv` lia 335 contas e
entregava **4 linhas**.

### A coluna errada (corrigido)

O `CSVParser` escolhe as colunas pelo NOME do cabeçalho, e este arquivo tem
duas candidatas a código:

```
CONTA, CLASSIFICAÇÃO, NOME DA CONTA CONTÁBIL, SALDO ANTERIOR, DÉBITO, ...
  1  ,      1       ,        ATIVO          ,  27.040.305   ,       , ...
  2  ,     1.1      ,   ATIVO CIRCULANTE     ,  17.509.657   ,       , ...
778  , 01.1.1.02.008,      BANCO ITAU        ,    20.00      ,       , ...
```

`CONTA` é numeração de linha (1, 2, 3, 778, 957…); `CLASSIFICAÇÃO` é o código
hierárquico. O casamento por nome batia "conta" e tomava a **numeração** por
código E por descrição, com saldo vazio — daí as 4 linhas.

O fallback relê pelo CONTEÚDO (a mesma detecção do Excel: a coluna cujos
valores *parecem* código é o código) e só substitui quando acha árvore onde o
`CSVParser` não achou. Resultado: 4 linhas → **329 contas, a árvore inteira**,
código vindo da `CLASSIFICAÇÃO`, saldo da `SALDO ANTERIOR` (a única preenchida).

### O número que eu NÃO forcei

Com as colunas certas, o rollup do arquivo **não fecha** — 21 agrupadores
divergem — e a causa é o formato do número, que é ambíguo dentro do próprio
arquivo:

```
02.2.1.04  PARCELAMENTOS         2.628.522     <- pai
02.2.1.04.002  Parcelamento INSS   318.90      <- filhos, somam 2.628,52
02.2.1.04.003  Parcelamento COFINS 161.98
...
```

Os filhos somam **2.628,52**; o pai mostra **2.628.522**. É a mesma grandeza
com escala diferente: os pais aparentam estar em reais (`2.628.522`), as folhas
em milhares (`318.90` = 318,90 mil). "20.00" não pode ser milhar (milhar tem
três dígitos), então é decimal; "2.628.522" com dois pontos é milhar. O mesmo
arquivo usa as duas convenções.

**Não dá para desambiguar sem um oráculo, e o oráculo seria o próprio rollup** —
tentar as duas leituras e ficar com a que fecha. É uma heurística poderosa e
arriscada, exatamente o tipo de "critério de corte" que pode inventar valor
errado. Não a apliquei sem decisão explícita.

O que o programa faz hoje é o certo pela regra do §26: lê as colunas
corretamente, e **avisa alto** que o total não bate e que a origem não fecha,
em vez de entregar 4 linhas em silêncio ou um Ativo 1000× errado com cara de
validado. A correção honesta é a leitura; a desambiguação do número fica
registrada como decisão pendente.

---

## §29 — Aprendizado do mlb bal ecd e correção do CI

**Data**: 2026-09-03

### Aprendizado do mlb bal ecd

O balancete `mlb bal ecd (1).xlsx` é um plano flat sem totalizador (1.791 contas,
nenhum código hierárquico). A entrega é inconferível por construção — não há como
comparar os totais — e o programa avisa corretamente ("NÃO FOI CONFERIDO").

O pipeline já extraía 313 linhas dele, mapeadas para 59 códigos GT distintos,
mas todas com saldo zero (o formato numérico do arquivo não é reconhecido). O
valor útil deste arquivo para o programa é o vocabulário: 307 descrições novas
que nunca tinham aparecido no `account_variations.json`.

Após a incorporação:

| Métrica                     | Antes   | Depois  |
|-----------------------------|---------|---------|
| Códigos GT no aprendizado   | 317     | 345     |
| Variações de descrição      | 928     | 1.235   |
| Suite de testes              | 656     | 657     |

Nenhuma regressão.

### Avaliação dos 4 com total errado

Medidos no corpus, 4 balancetes entregam total diferente da origem:

| Arquivo       | Classe afetada  | Diferença    | Contas sem destino | Resíduo |
|---------------|-----------------|-------------:|--------------------|---------|
| 202404        | ATIVO           | −3.157,94    | 8                  | 0,00    |
| RBM           | PASSIVO+PL      | −560,84      | 4                  | 0,00    |
| ASP 2023      | PASSIVO+PL      | −18,22       | 2                  | 0,00    |
| JRMA 1208.csv | ATIVO           | −9.703,79    | 52                 | 0,00    |

Causa: **contas sem destino no template GT**. O resíduo da reconciliação é zero
em todos — nenhum valor evaporou; a diferença é exatamente o que ficou de fora
por falta de linha no template. O programa avisa corretamente
("TOTAL DA ENTREGA NÃO BATE COM A ORIGEM"). Corrigir exige expandir o mapa do
template, que é decisão de modelagem, não de código.

### Correção do CI (Release workflow)

O workflow falhava com "exceeded the maximum execution time of 30m0s" porque o
timeout do job (30 min) é insuficiente para Windows: `uv sync` + pytest + build.py
(PyInstaller) somam mais que isso em `windows-latest`.

Correções:
- Timeout do job: 30 → 60 minutos
- Testes no CI: `pytest -m "not integration"` (555 testes, ~36s localmente;
  testes de integração precisam do corpus que não está no runner)
- Timeout individual: pytest 10 min, build.py 30 min
- Node.js 20: é aviso de depreciação forçada do GitHub, não do código; as actions
  ainda funcionam em Node.js 24

---
