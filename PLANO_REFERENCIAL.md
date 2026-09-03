# Plano de Contas Referencial — Alvo Único de Matching

## Problema (o que travava o "aprendizado")

O `data/plano_contas.json` (master) foi gerado a partir de **todos** os blocos
da ECF/SPED. Isso coloca vários "planos referenciais" incompatíveis no mesmo
espaço de matching, cada um com **seu próprio esquema de código**:

| Bloco        | O que é                                  | Esquema de código (ex.) |
|--------------|------------------------------------------|-------------------------|
| `L100A/L300A`| **PJ em Geral** — Balanço + DRE          | `1.01.01`, `2.01.02.01`, `3.07.02` |
| `L100B/L300B`| Instituições **financeiras** (bancos)    | `1.1.1.1.1.10.00` |
| `L100C/L300C`| **Seguradoras**                          | `1.02.03.08` |
| `U100/U150`  | Outros segmentos / folha                 | `1.1.1.03.02`, `4.03.99` |
| `M300/M350`  | **e-Lalur / apuração fiscal** (LALUR)    | COFINS em `3.01.01.01.01.04.10` |

Como o matcher casa **por texto da descrição** entre as 7.741 linhas, a mesma
conta cai em códigos de segmentos errados.

### Medição da contaminação (auto-matches do master, 21 balancetes, cold)

- Total auto-match: **2.345**
- Dentro do balancete correto (`L100A/L300A`): **721 (30,7%)**
- **Fora (namespace errado): 1.624 (69,3%)**

Exemplos reais:
- `CAIXA E EQUIVALENTES DE CAIXA` → `1.1.1.1.1.10.00` (plano **de bancos**, L100B)
  em vez de `1.01.01`.
- `BANCO PIX` → conta de **receita** PIX do L300B.

Ou seja: a "taxa de ~68%" celebrada era majoritariamente **matches no plano
errado**. O sistema aprendia a partir desses matches → nunca convergia
("Aprendizado falta" / "Quase aprendeu").

## Solução

Extrair um **alvo único e consistente**: o Plano de Contas Referencial da RFB
para **PJ em Geral** = `L100A` (Balanço) + `L300A` (DRE).

- **1.226 contas**, um só esquema (`1.x` Ativo, `2.x` Passivo/PL, `3.x` DRE)
- Árvore íntegra (todos os `parent_id` presentes)
- **0% de contaminação por construção**

Gerador: `src/bp/generators/plano_referencial.py`
→ produz `data/plano_referencial.json` (mesma estrutura do master, carregável
por `PlanodeContas` sem alterações).

Para regenerar:

```bash
python -m src.bp.generators.plano_referencial
```

## Resultado do re-treino (contra o referencial)

Medição **cold determinística** (fuzzy puro, sem variações aprendidas, cache
vazio), 21 balancetes, 4.610 contas sintéticas:

| Métrica                          | Master (contaminado) | Referencial |
|----------------------------------|----------------------|-------------|
| Auto-match "bruto"               | 2.345 (50,9%) inflado| 1.261 (27,4%) |
| Matches **corretos** (namespace) | **721 (15,6%)**      | **1.261 (27,4%)** |
| Contaminação (namespace errado)  | 1.624 (69,3%)        | **0%**      |
| Códigos aprendidos fora do alvo  | —                    | **0 / 139** |

O ganho do A **não é a taxa bruta** — o fuzzy puro é fraco para sinônimos
contábeis, então a taxa cai. O ganho é a **qualidade**: mesmo a frio, o
referencial entrega ~**1,75× mais matches corretos** (27,4% vs 15,6%) e um
dicionário de aprendizado **100% consistente** (139 códigos, todos no alvo).

> Nota de reprodutibilidade: com as variações aprendidas já ativas (estado
> "morno"), a taxa observada sobe para a faixa de ~40–59%. Esse ganho é o que
> as próximas etapas (sinônimos aprendidos + desempate por IA — plano B)
> consolidam de forma consistente, agora que o alvo é único. Os 27,4% acima são
> o piso honesto, a frio.

## Mudanças

- **Novo:** `src/bp/generators/plano_referencial.py` (gerador)
- **Novo:** `data/plano_referencial.json` (alvo limpo, 1.226 contas)
- **Alterado:** `AccountTrainer` agora usa `data/plano_referencial.json` como
  padrão (antes: `data/plano_contas.json`).
- **Backup:** o estado de treino antigo (baseado no master, contaminado) foi
  preservado em `src/bp/training/_backup_master_train/`.
- O master `data/plano_contas.json` **não** foi apagado — continua disponível
  para o gerador e para segmentos futuros (financeiras/seguradoras).
