# Revisão de Arquitetura — BP

Este documento consolida a revisão de arquitetura pedida como segunda etapa do
passe de qualidade. Ele mapeia como os módulos se conectam hoje, aponta onde o
acoplamento e a altitude estão errados, e recomenda a próxima geração de
mudanças — separando o que é seguro fazer agora do que exige planejamento.

## 1. Mapa de dependências (estado atual)

```
                                 ┌──────────────────┐
                                 │  utils/          │
                                 │  normalizer,     │
                                 │  synonyms        │
                                 └──────────────────┘
                                        ▲
                    ┌───────────────────┼────────────────────┐
                    │                   │                    │
           ┌────────┴────────┐  ┌───────┴────────┐  ┌────────┴────────┐
           │  generators/    │  │  parsers/      │  │  matchers/       │
           │  PlanodeContas  │  │  dispatcher,   │  │  ContaMatcher,   │
           │  plano_refer.   │  │  csv/xls/xlsx, │  │  MatchCache      │
           │                 │  │  pdf,txt,pdf_  │  │                  │
           │                 │  │  utils/*, ...  │  │                  │
           └────────┬────────┘  └───────┬────────┘  └─────────┬────────┘
                    │                   │                     │
                    └───────────┬───────┴─────────────────────┘
                                │
                    ┌───────────┼──────────────┐
                    │           │              │
              ┌─────┴─────┐ ┌───┴───────┐ ┌────┴───────────┐
              │ training/ │ │ exporters │ │  validators/    │
              │ trainer,  │ │ xlsx_exp. │ │  export_schema  │
              │ wizard,   │ │           │ │                 │
              │ apply_llm │ │           │ │                 │
              └───────────┘ └───────────┘ └─────────────────┘
```

Não há **ciclos** de import. Bom sinal.

## 2. Contratos entre camadas (implícitos hoje)

| Camada | O que fornece | O que consome |
|--------|---------------|---------------|
| `utils` | Funções puras (normalize, expand_synonyms, is_garbage) | — |
| `generators` | `PlanodeContas` (carrega JSON, faz consultas O(1) e fuzzy simples) | `utils/normalizer` |
| `parsers` | `[{codigo, descricao, saldo, nivel}]` a partir de arquivos | `utils`, dispatcher orquestra |
| `matchers` | `MatchResult(decision, candidates, needs_review)` para uma descrição | `PlanodeContas`, `utils`, cache |
| `training` | Aprendizado incremental + revisão | Parsers + matcher + generators |
| `exporters` | .xlsx multi-aba | Parsers + matcher + generators + training-state |
| `validators` | Schema de saída | — |

O contrato **falha em três lugares**:

- **`exporters/xlsx_exporter.py` é orquestrador escondido** — importa parsers,
  matchers, generators e lê estado de treino. É a camada superior do sistema
  disfarçada de "escritor de xlsx".
- **`ContaMatcher.__init__` faz IO** (`_load_learned_variations`), misturando
  loader + matcher. O contrato "recebe plano + threshold" quebra na hora que
  algum lugar depende de um arquivo específico em disco.
- **`AccountTrainer` faz IO em três direções** (arquivos processados, cache
  próprio, variations, patterns, stats, ignore) sem uma camada de persistência
  isolada. Cada nova mudança rebate em 6 arquivos JSON.

## 3. Achados priorizados

### Alta prioridade (bandaid arquitetural — vai doer mais tarde)

**A. `ContaMatcher.match()` acumulou 7 camadas (Planos A–G) sem uma abstração
de pipeline.**
Cada plano empilhou um caso especial: cache → garbage → synonyms → fuzzy →
classe → heurística → IA stub. A penalidade de classe foi aplicada duas vezes
por bug (corrigido nesta rodada com um `set _already_penalized`, que é o
bandaid sobre o bandaid — o próprio simplify sinalizou). **Fix real:** um
`ScoringPipeline` composto de `Scorer`s nomeados; cada plano vira um stage
plugável. Elimina os "já passou por X?" implícitos e torna cada camada
testável isoladamente.

**B. O `dispatcher` mistura roteamento com o parser tabular genérico.**
`ParseyCaller.parse()` é hoje 550 linhas — a maior parte é um parser
description-first para DataFrames (usado por XLS/XLSX/TXT/CSV genérico), o
resto é `if suffix == ".csv"/".pdf"` short-circuit. **Fix real:** extrair
`TabularParser` para os casos DataFrame, e transformar `ParseyCaller` num
**Registry** onde parsers se registram por extensão. Adicionar um formato
novo hoje edita dois arquivos (dispatcher + trainer's SUPPORTED_EXTENSIONS,
já resolvido nesta rodada por importar do dispatcher).

**C. Duas fontes de verdade para "decisão manual".**
`apply_llm_mappings` escreve tanto em `account_variations.json` quanto em
`training_cache.json`. Quando divergem, qual vale? Ninguém sabe. **Fix real:**
uma camada de **Supervisão** (arquivo único, consultada com precedência maior
que fuzzy no `match()`). Cache e variations tornam-se views derivadas. Elimina
o "qual arquivo está certo?".

### Média prioridade (limpo o suficiente hoje, mas debita amanhã)

**D. `xlsx_exporter` é o orquestrador implícito.**
Ele já parseia, casa, faz rollup hierárquico e exporta. O nome vende só a
última parte. **Fix:** extrair `pipeline.py` ou `app.py` como orquestrador
top-level explícito (`Convert(input) → Match → Export`), e o exporter volta a
ser "só escreve o .xlsx".

**E. `PlanodeContas` não é fonte única para "classe da conta".**
Hoje `classe_from_codigo` vive em `conta_matcher.py`, e o Plano C precisou
propagá-la manualmente pelo `codigo_origem`. **Fix:** subir para `utils/` (ou
para o próprio `PlanodeContas`) — todo consumidor (matcher, exporter,
validator) faz a derivação do mesmo jeito.

**F. Imports mistos absolutos/relativos.**
4 arquivos usam `from src.bp.x` (só funciona rodando da raiz do repo), o resto
usa `from ..x`. `train.py` compensa com `sys.path.insert`. **Fix:** ou
padronizar tudo em relativo, ou instalar o pacote (`uv pip install -e .`) e
usar sempre `from bp.x`. Sinaliza um problema também em
`validators/__init__.py:11` que documenta `from bp.validators` (não funciona).

### Baixa prioridade (higiene)

**G. Módulos gigantes.**
`conta_matcher.py` (740), `trainer.py` (732), `xlsx_exporter.py` (713),
`dispatcher.py` (593). Todos deveriam quebrar em 3–5 arquivos. Barato,
melhora navegabilidade, mas não muda comportamento.

**H. Duplicações remanescentes (agent do simplify apontou, ficaram como C ou
maior refactor):**
- Parsing numérico BR (3 lugares: `BaseParser._normalize_saldo`,
  `dispatcher._parse_number`, `PDFBalanceParser._to_float`).
- Cálculo de nível a partir do código (2 lugares).
- Padrão de load/save JSON (`variations`, `cache`, `patterns`, `stats`,
  `ignore`, `processed_files` — 6 lugares muito parecidos).

Cada uma pede um utilitário em `utils/`.

## 4. Recomendação de sequência

**Fase 1 — Seguro agora (uma tarde):**
1. Extrair `utils/codigo.py` com `nivel_from_codigo` e `classe_from_codigo`.
2. Extrair `utils/json_store.py` com `load_json(path, default)` /
   `save_json(path, data)`. Rebate em 6 chamadores.
3. Consolidar `BaseParser._normalize_saldo` como fonte única e chamar em
   `dispatcher._parse_number` e `PDFBalanceParser._to_float`.
4. Padronizar imports (escolher relativo E deletar os `sys.path.insert`).

**Fase 2 — Muda a forma sem mudar comportamento (uma sprint curta):**
5. Extrair `TabularParser` do dispatcher; dispatcher vira Registry.
6. Extrair `pipeline.py` (`ConversionPipeline`) — `xlsx_exporter` volta a
   ser um sink.
7. Separar `AccountTrainer` em `PersistenceStore` + `TrainingLoop` + `Report`.
8. Quebrar `conta_matcher.py` em `matcher.py` + `scorers.py` + `pipeline.py`
   (base para o item 9).

**Fase 3 — Refactor arquitetural (uma sprint dedicada):**
9. `ScoringPipeline` composto de `Scorer`s — cada plano (A–G) vira uma stage.
10. **Supervision layer** unificada: `data/supervision.json` como fonte única
    de decisões humanas/LLM; cache e variations viram views derivadas.

**Fase 4 — Empacotamento (fora do escopo deste doc):**
11. Instalar como pacote (`uv pip install -e .`), rodar via console_script.
12. PyInstaller/Nuitka para o executável do colaborador (design já discutido
    com o usuário: OCR só na estação de curadoria).

## 5. O que NÃO fazer

- **Não** dividir os módulos gigantes antes de arrumar as abstrações (dividir
  `conta_matcher.py` em vários arquivos com a arquitetura atual só espalha o
  spaghetti).
- **Não** subir para strict-mode do mypy num commit só — 84 erros pendentes,
  a maioria são tipos legítimos que exigem análise caso a caso.
- **Não** trocar RapidFuzz por embeddings semânticos antes de resolver o
  ScoringPipeline — cada mudança rebate no matcher hoje, e um sistema de
  pipeline claro torna a troca uma stage isolada.

## 6. Estado atual (após este passe)

- 162 testes passando (era 141 no início da série de melhorias).
- 715 achados do ruff → 13 restantes, todos menores.
- 88 erros do mypy → 84, com todos os **bugs reais** corrigidos (o `.txt`
  agora funciona, `builtins.any` como tipo removido, dead code eliminado).
- Trainer O(n²) → O(n). Suíte caiu de 30s para 8s.
- Nenhum ciclo de import.
- Nenhum código órfão pendente.

A base está pronta para as próximas fases sem dívida técnica escondida.
