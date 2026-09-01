# Plano E — Enriquecimento do Plano-Alvo

Primeiro plano que **aumenta a taxa de match de verdade**, porque ataca a
causa que os Planos A–D não tocavam: **linhas que simplesmente não existem no
referencial**.

## Problema

O Plano Referencial (L100A + L300A) é a base fiscal da ECF. Vários conceitos
corriqueiros de balancete **não têm conta correspondente** nele — o matcher
não errava por falta de tuning, e sim por falta de **alvo**:

- `CLIENTES` / `DUPLICATAS A RECEBER` → melhor candidato "DEBÊNTURES"
- `CAPITAL SOCIAL` → só existe como "Capital Realizado/Subscrito"
- `DESPESAS COM PESSOAL`, `DESPESAS ADMINISTRATIVAS`, `INSS`, `VALE ALIMENTAÇÃO`
  → só existem como linhas redutoras "(-) ..." da apuração fiscal

## Solução

Um arquivo **separado e auditável** de contas enriquecidas
(`data/plano_referencial_extra.json`), mesclado pelo gerador
(`plano_referencial.py`). Regras:

- **Códigos na faixa reservada `x.90.*`** (livre de colisão com a ECF); a raiz
  (`1`/`2`/`3`) preserva a classe para o Plano C.
- **`forms: ["ENRIQUECIDO"]`** marca a origem — auditável e reversível.
- **Descrição = termo exato do balancete** (Clientes, Capital Social, Despesas
  com Pessoal, ...), casando direto no fuzzy sem sinônimos.
- **Só o que falta:** contas que já existem (Móveis, Máquinas, Fornecedores,
  Estoques) NÃO são duplicadas.

38 contas adicionadas, organizadas em grupos sintéticos (Contas a Receber,
Obrigações e Patrimônio, Despesas com Pessoal, Despesas Administrativas e
Gerais, Despesas com Vendas, ...) com suas linhas comuns.

## Resultado medido (cold, corpus completo)

| | Antes (Plano D) | Depois (Plano E) |
|--|---------------:|-----------------:|
| Auto-match | 26,0% | **37,4%** |
| Itens em revisão | 2.964 | 2.437 |
| Contaminação cross-class | 0% | **0%** |

- **+11,4 p.p. de taxa**, desta vez subindo (adicionamos alvos válidos, não
  removemos falsos-positivos).
- **562 auto-matches** passaram a cair em contas enriquecidas — todos corretos
  e na classe certa (verificado no corpus).
- Os enriquecidos **não sequestraram** matches corretos já existentes:
  `Salários a Pagar` (passivo) continua na conta RFB certa, `Fornecedores` e
  `Caixa` intactos. Classe + especificidade da descrição garantem isso.

## Como estender

Edite `data/plano_referencial_extra.json` (adicione ao array `contas` com
código `x.90.*`, descrição = termo de balancete, tipo/natureza/parent_id) e
rode `python -m src.bp.generators.plano_referencial`. Nenhuma mudança de código.

## Arquivos

- novo: `data/plano_referencial_extra.json` — contas enriquecidas (auditável)
- alterado: `src/bp/generators/plano_referencial.py` — `_merge_extras()`
- regenerado: `data/plano_referencial.json` (1.109 → 1.147 contas)
- atualizado: `output/review_worklist.csv` (1.117 → 1.025 descrições em revisão)
