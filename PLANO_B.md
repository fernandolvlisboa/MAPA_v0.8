# Plano B — Qualidade de Matching sobre o Plano Referencial

Construído em cima do Plano A (alvo único e consistente `L100A + L300A`).
O foco do B é **qualidade e higiene** do matching, não apenas taxa bruta.

## O que foi implementado

### 1. Camada de sinônimos/abreviações contábeis (PT-BR)
- `data/accounting_synonyms.json` — dicionário (frase / token / abreviação).
- `src/bp/utils/synonyms.py::expand_synonyms()` — expande a **descrição de
  origem** para o vocabulário canônico ANTES do fuzzy. Aplicada só ao lado da
  consulta; o plano-alvo permanece canônico.
- Ataca a fraqueza medida do `token_set_ratio` puro: descrições corretas com
  **zero tokens em comum** com o alvo. Ex.: `BENS NUMERÁRIOS` → `caixa e
  equivalentes de caixa`; `FORNECEDORES/CREDORES` → `fornecedores`;
  `REC.RECEBIDAS ANTECIPADAMENTE` → `receitas diferidas`.
- Trata pontuação grudada (`c/`, `s/`, `rec.recebidas`, `forn/cred`).

### 2. Guarda anti-lixo
- `src/bp/utils/synonyms.py::is_garbage_description()` — descarta linhas cuja
  "descrição" é numérica/simbólica (`199687591.84`, `-203123324.74`, `0.0`,
  `(-)`), tipicamente totais e colunas de valor lidas como descrição por
  desalinhamento. Aplicada no matcher e no treinador.
- Efeito: **447 linhas-lixo** deixaram de entrar na fila de revisão.

### 3. Desempate de matching (correção de falso-positivo)
O `token_set_ratio` dá **score 1.00** sempre que a consulta está **contida**
num candidato mais longo — inclusive quando o sentido muda. Ex.: `Fornecedores`
casava com o *analítico* `Fornecedores - Operações com Partes Relacionadas` em
vez do *sintético* `2.01.01.03 FORNECEDORES – CIRCULANTE`.

Correções em `ContaMatcher._fuzzy_match`:
- **Pool de candidatos ampliado** (`limit=40`): para consultas curtas dezenas
  de contas empatam em 100; um limite baixo descartava a certa antes do
  desempate.
- **Desempate por proximidade real**: `token_sort_ratio` sobre o *core* da
  descrição (sem sufixos `- no País`, `– Circulante`; trata hífen e travessão).
- **Preferência por conta sintética**: linha genérica de balancete mapeia
  melhor para o nível sintético do que para a folha analítica.

Resultado: `Fornecedores → 2.01.01.03` (sintético, passivo, correto);
`Clientes`/`Duplicatas a Receber → REVISÃO` honesta (o referencial PJ-em-geral
não tem conta de "clientes" no ativo — melhor revisar que casar errado).

### 4. Desempate por IA — real e injetável
`ContaMatcher(..., ai_classifier=fn)`: função `(descricao, candidatos,
contexto) -> MatchDecision | None`, chamada nos casos ambíguos. Desacopla o
matcher do provedor (Claude/Ollama/etc.), com falha isolada (nunca derruba o
pipeline). Testado com classificador simulado.

## Números (cold determinístico, referencial)

| Etapa                     | auto-match | revisão | lixo removido |
|---------------------------|-----------:|--------:|--------------:|
| Plano A (referencial)     | 27,4%      | 3.349   | 0             |
| Plano B (esta entrega)    | **29,0%**  | 2.827   | **447**       |

O ganho de **taxa bruta** é pequeno de propósito: o efeito principal do B é
converter matches **confiantes-errados** (analítico/errado a 1.00) em
**corretos** (sintético certo) ou em **revisão honesta**, além de tirar 447
linhas-lixo. Taxa isolada não captura isso — a métrica que importa é *match
correto*, e essa melhora qualitativamente.

## Próximo passo recomendado (Plano C)

O disambiguador que falta é **tipo/natureza**: o dígito-raiz do código de
origem (1=Ativo, 2=Passivo, 3/4=Resultado) e do referencial já separam
Ativo×Passivo. Propagar `tipo` para `ContaMatcher.match()` resolveria casos
como `Clientes` (ativo) × `Adiantamentos de Clientes` (passivo) via o boost de
tipo já existente. Fica como próxima etapa por exigir mapear a convenção de
raiz de cada balancete.

## Arquivos

- novo: `data/accounting_synonyms.json`
- novo: `src/bp/utils/synonyms.py`
- novo: `tests/test_synonyms.py`
- alterado: `src/bp/matchers/conta_matcher.py` (expansão, guarda, desempate, IA injetável)
- alterado: `src/bp/training/trainer.py` (guarda anti-lixo)
- alterado: `tests/test_matchers.py` (+2 testes de IA injetável)
