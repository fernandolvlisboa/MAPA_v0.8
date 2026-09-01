# Plano G — Classificador LLM + Enriquecimento Guiado por Dados

Faz o que o Plano B deixou pronto: **plugar o classificador LLM** como fallback
para as descrições que o fuzzy/heurística não resolve. Só que em vez de uma
chamada online por conta, usa **decisões em lote, auditáveis e offline**
(compatíveis com o requisito de app executável sem internet).

## Ideia

- Um humano (ou LLM) analisa a **worklist de revisão**, ordenada por
  frequência.
- Escreve mapeamentos `descrição → código` num arquivo separado
  (`data/llm_mappings.json`), com nota e classe esperada.
- Um script (`apply_llm_mappings.py`) **valida** (o código existe? a classe
  bate?) e mescla em `account_variations.json` + `training_cache.json`.
- Onde o alvo certo não existia no referencial, adicionamos **contas
  enriquecidas** (mesmo mecanismo do Plano E).
- Re-treino consolida tudo.

Neste ciclo eu (Claude) fui o classificador: dois batches, 127 decisões
totais, todas passaram na validação de código e classe.

## Fluxo end-to-end

```
Worklist ordenada por freq  ─►  Classificador (LLM ou humano)
                                       │
                                       ▼
                          data/llm_mappings.json (auditável)
                                       │
                              apply_llm_mappings.py
                    (valida código + classe do Plano C)
                                       │
                                       ▼
                    account_variations.json + cache
                                       │
                                       ▼
                                 train.py
                                       │
                                       ▼
                        Matcher passa a acertar sozinho
```

## Resultado medido (corpus completo, 31 arquivos)

| Etapa | Matched | Rate | Revisão | Variações | Fora do referencial |
|--|---:|---:|---:|---:|---:|
| Pós-Plano F (baseline) | 2.474 | 33,5% | 4.425 | 252 | 0 |
| + batch 1 (61 mappings + 50 enriched) | 3.097 | 42,0% | 3.802 | 292 | 0 |
| + batch 2 (127 mappings + 117 enriched) | **3.466** | **47,0%** | **3.433** | **317** | **0** |

- **+13,5 p.p. de taxa** (33,5% → 47,0%)
- **+992 matches** consolidados no dicionário aprendido
- **117 contas enriquecidas no referencial** (era 38 no Plano E)
- **Qualidade preservada**: 0 códigos fora do referencial, 100% respeitam classe

## Por que isso NÃO viola "app offline"

O LLM é usado **na estação de curadoria** (a sua), como ferramenta de
ingestão. O produto que sai — `account_variations.json`,
`plano_referencial.json` + `plano_referencial_extra.json` — é **JSON estático
que viaja junto com o app**. O executável do colaborador continua sem rede,
sem OCR, sem chamadas externas. Cada rodada de curadoria deixa o app mais
inteligente na versão seguinte.

## Como plugar um LLM real (roadmap)

O `ContaMatcher` já aceita `ai_classifier` (Plano B). Quem quiser rodar isso
automaticamente é só passar uma função que devolve `MatchDecision`. Duas
opções compatíveis:

- **Local (100% offline)**: Ollama + Llama/Qwen, chamado pelo
  `ai_classifier`. Só na estação de curadoria.
- **API (Anthropic Messages)**: Claude via SDK. Também só na curadoria.

Em ambos, o resultado é gravado em `llm_mappings.json` para trilha de auditoria
antes de virar `account_variations`.

## Arquivos

- novo: `data/llm_mappings.json` — 127 decisões auditáveis
- novo: `src/bp/training/apply_llm_mappings.py` — validação e merge
- alterado: `data/plano_referencial_extra.json` — 117 contas (era 38)
- regenerado: `data/plano_referencial.json` (1.147 → 1.226 contas)

## Próximo passo

Batch 3 sobre os itens 220–500 da worklist deve levar a taxa a 55%+; o
retorno começa a decair depois disso porque a cauda é dominada por nomes
próprios de fornecedores/clientes e ruído de DFs (que **não devem** ser
mapeados — o correto é ficar em revisão para o contador).
