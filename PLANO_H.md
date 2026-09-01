# Plano H — Saída no Template GT (a entrega ao cliente)

Implementa a especificação de `docs/TEMPLATE_GT_BP.md`: o programa deixa de
entregar uma planilha própria e passa a **povoar o template da empresa**.

## Arquitetura híbrida

| Camada | Quem faz | O quê |
|--------|----------|-------|
| **Apresentação** | `templates/Template_GT_BP_Padrao_v3.xlsx` | formatação, fórmulas SUMIFS, blocos de análise, identidade visual GT |
| **Dados** | Python | alimenta **apenas** a aba oculta `_dados_padronizados` |

O código nunca recria nem reformata o template: copia, escreve o nome do
cliente em `B4` e despeja os dados na aba oculta. As fórmulas fazem o resto.

## O bug que isto revelou (e corrige)

O template agrega por `SUMIFS(..., $C<linha> & "*")` — 86 prefixos ECF na
coluna C. **Qualquer código fora desses prefixos não é somado por ninguém: o
valor some, sem erro e sem aviso.**

Medido sobre os 317 códigos que o treino aprendeu:

| | Antes da projeção |
|--|---:|
| Códigos capturados pelo template | 116 / 317 |
| **Peso (ocorrências) que viraria ZERO** | **75,2%** |

Duas famílias eram perdidas:

1. **Contas enriquecidas** (`1.90.*`, `2.90.*`, `3.90.*`) — criadas nos Planos
   E/G para cobrir linhas de balancete ausentes na ECF. **0 de 117** eram
   capturadas: são códigos que nós inventamos, não existem no plano oficial.
2. **Bloco paralelo `3.11.*`** — a ECF duplica a DRE em `3.01.*` (Lucro Real) e
   `3.11.*` (Presumido), com descrições idênticas. O template usa `3.01.*`;
   **45 códigos** aprendidos em `3.11.*` se perderiam. Todos os 45 têm
   equivalente exato em `3.01.*`.

## A solução — camada de projeção

`src/bp/output/template_map.py` (`TemplateProjector`). Os 86 prefixos são lidos
**do próprio `.xlsx`** em runtime — editar o template no Excel basta, nada é
duplicado em código.

Ordem de projeção:

1. **Agrupador de topo** (`1.01`, `3.01.01`) → **não projeta**. É subtotal do
   balancete do cliente; projetar causaria **dupla contagem**, pois o template
   já soma as analíticas. Vai para revisão com o motivo registrado.
2. **Mapa explícito** (`data/template_projection.json`) — enriquecidas e casos
   especiais da ECF que o template não lista.
3. **Normalização `3.11.* → 3.01.*`** — aplicada antes do casamento direto *e*
   da subida hierárquica.
4. **Direto** — já capturado por um prefixo.
5. **Subida na hierarquia** — remove o último segmento até achar um prefixo.

### Resultado

| | Antes | Depois |
|--|---:|---:|
| Códigos projetados | 116 / 317 | **271 / 317** |
| **Peso recuperado** | 24,8% | **92,2%** |

Os ~8% restantes são, corretamente, subtotais (`ATIVO CIRCULANTE`,
`PATRIMÔNIO LÍQUIDO`) que **não devem** virar linha.

## Sinais — divergência resolvida

`docs/TEMPLATE_GT_BP.md` §4.2 diz "passivos negativos", mas a fórmula de check
do próprio template é `=IF(ROUND(D26-D52,2)=0,"OK","NOK")` — que só fecha com
**Ativo e Passivo positivos**. Segui o template (o artefato) e não a prosa.

O sinal é derivado do **rótulo da coluna B**: linha começando com `(-)` é
negativa, o resto positiva. Assim o DRE fecha (`EBITDA = D22+SUM(D25:D30)`
exige despesas negativas) e o Balanço também. Editar o template mantém código e
convenção em sincronia automaticamente.

## Público das abas

Você observou que o Sumário e as contas não identificadas servem mais ao
**usuário-chave** que ao cliente final. As abas geradas trazem isso explícito
no topo: *"Uso interno — a entrega ao cliente são as abas BP_GT e DRE_GT."*

| Aba | Público |
|-----|---------|
| `Sumário` | interno — qualidade do processamento, avisos |
| `BP_GT` / `DRE_GT` | **cliente** — a entrega |
| `Contas Tratadas` | interno — auditoria do de-para |
| `Contas Não Identificadas` | interno — fila de revisão |
| `_dados_padronizados` | oculta — insumo do SUMIFS |

## Verificação

Gerado com balancete real (`Balancete Real Life.xlsx`, ano-base 2024) e
simulado o SUMIFS de cada linha sobre os dados escritos:

```
_dados_padronizados: 52 linhas
TOTAL escrito   : 250.182,1
TOTAL capturado : 250.182,1
Linhas ÓRFÃS    : 0
```

**Nada se perde e nada é contado duas vezes.** BP_GT e DRE_GT saíram povoados
(Caixa 9.479,0 · Receita bruta 8.010,0 · (-) Custos -5.222,5 · etc.), com os
sinais na convenção do template.

`182 testes passando` (+17 novos), incluindo o teste de regressão do bug
central: *nenhuma linha escrita pode ficar órfã*.

> LibreOffice não conclui o recálculo neste sandbox (perfil frio, timeout em
> 300s), então a verificação replicou a semântica do SUMIFS em Python. Ao abrir
> no Excel, os valores aparecem calculados.

## Uso

```python
from src.bp.output.build_gt_output import build_gt_output, FonteBalancete

# um exercício
build_gt_output("balancete.xlsx", "output/gt/Cliente_2024.xlsx", ano_base=2024,
                nome_cliente="Cliente Ltda")

# série histórica — um arquivo por ano
build_gt_output([
    FonteBalancete("bal_2022.xlsx", 2022),
    FonteBalancete("bal_2023.xlsx", 2023),
    FonteBalancete("bal_2024.xlsx", 2024),
], "output/gt/Cliente.xlsx", nome_cliente="Cliente Ltda")
```

Ver [`PLANO_I.md`](PLANO_I.md) para anos flexíveis, multi-arquivo e a correção
do alinhamento de colunas.

## Arquivos

- novo: `templates/Template_GT_BP_Padrao_v3.xlsx` (template da empresa)
- novo: `docs/TEMPLATE_GT_BP.md` (especificação)
- novo: `src/bp/output/template_map.py` (`TemplateProjector`)
- novo: `src/bp/output/build_gt_output.py` (construtor)
- novo: `data/template_projection.json` (mapa de projeção, auditável)
- novo: `tests/test_gt_output.py` (17 testes)
