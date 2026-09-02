# 🧠 Learners — o módulo que aprende com o uso

> **Reuso natural:** toda tarefa repetitiva de categorização que evolua no tempo. É a peça que faz o sistema **melhorar sozinho** conforme o analista revisa. Serve para qualquer domínio, não só contas contábeis.

O ponto: um matcher puro só sabe o que já sabe. Se você mostrar `"VAMOS LOCACAO S.A"` para ele hoje e ele errar, e o analista corrigir, essa correção deveria contar amanhã. O learner é o que grava isso e passa para o matcher, sem re-treino, sem retrabalho.

---

## Duas peças, dois papéis

| Peça | Quando roda | Escreve em |
|---|---|---|
| **`AccountTrainer`** — processamento em lote | você tem uma pasta cheia de balancetes novos | `account_variations.json`, `training_stats.json`, cache, `processed_files.json` |
| **`review_wizard`** — assistente interativo | o trainer marcou linhas "precisa revisão" | `account_variations.json`, `training_ignore.json` |

O ciclo é **treinar → revisar → treinar** — a cada revisão o próximo treino aproveita o que foi ensinado.

---

## O caminho comum

**1. Coloque balancetes na pasta de treino.**

```bash
cp meus_balancetes/*.xlsx src/bp/training/DFS_Exemple/
```

**2. Rode o treino incremental.** Processa **só arquivos novos** (checa `processed_files.json`).

```bash
uv run python src/bp/training/train.py
```

Isso lê cada arquivo pelo dispatcher, chama o matcher, filtra ruído (linhas-lixo, contas analíticas com CNPJ, número de agência, etc.) e escreve:

- `account_variations.json` — cada código do plano-alvo com as variações de descrição que apareceram, e frequência de ocorrência (`{"1.01.01": {"variations": ["caixa", "caixa geral", ...], "frequency": 24}}`). **Esse arquivo é o que o matcher carrega para ficar mais esperto.**
- `training_stats.json` — número de arquivos processados, taxa de acerto por sessão.
- `training_cache.json` — cache de matching acumulado no treino.
- `output/training_report.md` — relatório humano ("400 lidas, 320 casadas, 80 revisar, top 5 novas variações aprendidas").

**3. Revise as pendências.** O relatório lista o que ficou sem match confiável. Abre o assistente:

```bash
uv run python -m src.bp.training.review_wizard --all --limit 10
```

Dentro do assistente:

| Tecla | Ação |
|---|---|
| `s` | Buscar candidatos por descrição (fuzzy) |
| `h` | Navegar pela hierarquia (Ativo → Circulante → …) |
| `c` | Informar o código manualmente |
| `i` | **Ignorar** permanentemente (ruído específico do cliente) |
| `k` | Pular nesta sessão |
| `q` | Sair |

Cada decisão vai para `account_variations.json` (`s`/`h`/`c`) ou para `training_ignore.json` (`i`). Rode o **passo 2 de novo** para consolidar — o matcher já usa o novo conhecimento na próxima classificação.

---

## API programática (`AccountTrainer`)

O trainer também pode ser chamado de código, sem passar pelo `train.py`.

```python
from src.bp.training.trainer import AccountTrainer

t = AccountTrainer()   # usa data/plano_referencial.json por default
resultado = t.train(verbose=True)

print(f"processados : {len(resultado['processed'])}")
print(f"match rate  : {resultado['match_rate']:.1f}%")
print(f"pendentes   : {resultado['needs_review']}")

t.export_report("output/training_report.md")
```

O trainer é a peça que decide **o que vale gravar**: filtra linhas cujo `codigo` é analítico demais (`1.1.1.4.2.001.045` — específico de cliente, não generaliza), descarta descrições-lixo (totais, cabeçalhos que viraram linha), e agrupa por código-alvo antes de gravar a variação. Sem esses filtros, o `account_variations.json` viraria um dicionário do dia — em vez de vocabulário.

---

## Os arquivos que o módulo escreve

Todos ficam em `src/bp/training/*.json`. Você deve tratá-los como **estado versionável** apenas nos dois primeiros — os outros são cache/log e podem ser regenerados.

| Arquivo | Conteúdo | Versionar? |
|---|---|---|
| `account_variations.json` | Vocabulário aprendido (código → variações) — **isto é o que faz o matcher acertar mais** | **sim**, é a inteligência acumulada |
| `learned_patterns.json` | Sinônimos e abreviações identificados no treino | sim |
| `training_cache.json` | Cache de matching acumulado no treino | opcional |
| `training_stats.json` | Estatísticas por sessão | opcional |
| `training_ignore.json` | Descrições marcadas como ruído permanente (`i` no wizard) | sim, é decisão humana |
| `processed_files.json` | Lista de arquivos já processados (incremental) | **não** — nomes de arquivo de cliente |

> **Importante:** `processed_files.json` costuma conter nomes de arquivo com **nome de cliente**. Fora do repo público. O `.gitignore` do MAPA_v0.8 já o protege.

---

## Como reaproveitar fora do MAPA

Este módulo é uma **loop de curadoria humana**: apresente candidatos, deixe alguém decidir, grave a decisão, use na próxima vez. A implementação atual é específica de balancete, mas o desenho é geral. Para levar para outra automação:

1. Copie `src/bp/training/trainer.py` e `review_wizard.py` como referência.
2. Substitua o parser (o que lê os arquivos de entrada) e a heurística de filtro por regra do seu domínio (o que descarta linhas-lixo).
3. Reaproveite o `match_cache.py` e o formato `account_variations.json` — ambos são genéricos.
4. O `review_wizard` é `argparse` + prompts — fácil de portar para uma tela.

Casos onde essa mecânica se paga:

- **Classificação de fornecedores/produtos** — cada correção do time entra no dicionário.
- **Categorização de despesas** em ferramenta interna — o sistema aprende com o que os analistas corrigem.
- **Anotação de documentos** com fine-tuning tardio — grava as decisões antes de treinar o modelo grande.
- **Tarefas de review em compliance/QC** — separa o "OK automático" do "precisa olhar", e aprende a diferença.

---

## Como o matcher usa o que o learner escreve

Automaticamente. Quando você instancia `ContaMatcher(plano)`, ele carrega `account_variations.json` (se existir) e usa as variações como **atalhos**: se a descrição bater com uma variação já vista, ele decide direto, com score alto e `source="cache"` ou `"heuristic"`.

Ou seja: o learner **não fala com o matcher em tempo real**. A comunicação é assíncrona via arquivo. Você treina hoje, o matcher em qualquer processo Python que abrir amanhã já vai mais rápido — inclusive dentro do `MAPA.exe` embarcado.

---

## Arquivos-chave

| Arquivo | Papel |
|---|---|
| `trainer.py` | `AccountTrainer` — orquestra ler → classificar → filtrar → gravar → relatório |
| `train.py` | CLI: `python -m src.bp.training.train` |
| `review_wizard.py` | Assistente interativo (`s`/`h`/`c`/`i`/`k`/`q`) |
| `apply_llm_mappings.py` | Aplica mapeamentos vindos de um passe LLM offline (ver Plano G) |
| `DFS_Exemple/` | **Fora do repo público** — pasta onde o analista deixa balancetes reais |

Testes: [`tests/test_trainer.py`](../../../tests/test_trainer.py).

Fundamento arquitetural: [`../../../GUIA_TREINAMENTO.md`](../../../GUIA_TREINAMENTO.md), [`../../../PLANO_B.md`](../../../PLANO_B.md) (qualidade), [`../../../PLANO_G.md`](../../../PLANO_G.md) (classificador LLM + enriquecimento).
