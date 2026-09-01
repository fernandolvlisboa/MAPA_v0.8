# Plano D — Suporte Multilíngue (PT / EN / ES)

Responde à pergunta: **e se o balancete chegar em inglês ou espanhol?**

## Comportamento anterior

O matching casa a descrição de origem contra o Plano Referencial (em
**português**), e a camada de sinônimos só tinha vocabulário PT-BR. Resultado
medido: **balancetes em EN/ES caíam 100% em revisão** (score 0.00) — "Cash and
cash equivalents" e "Caixa e Equivalentes de Caixa" não têm nenhum token em
comum.

O que já funcionava independente do idioma: a classe por código (Plano C, se o
código é numérico) e a guarda anti-lixo.

## Solução: dicionário trilíngue

Estende `data/accounting_synonyms.json` com seções `phrase_en` e `phrase_es`
que mapeiam termos de balancete em inglês/espanhol para o **vocabulário
canônico PT** já usado internamente. Exemplos:

| Origem | → canônico PT | casa em |
|--------|---------------|---------|
| `trade payables` / `proveedores` | `fornecedores` | `2.01.01.03` |
| `inventories` / `existencias` | `estoques` | `1.01.03…` |
| `property, plant and equipment` / `inmovilizado` | `imobilizado` | `1.02.03…` |
| `retained earnings` / `reservas de utilidades` | `reservas de lucros` | `2.03.02…` |
| `sales revenue` / `ventas netas` | `receita de vendas` | `3.01.01…` |

Como a expansão de sinônimos já é aplicada **só ao lado da consulta**, as
seções `_en`/`_es` são simplesmente mescladas no mapa de frases no
carregamento (`src/bp/utils/synonyms.py`). **Não há detecção de idioma**: como
um balancete PT não contém as frases EN/ES, aplicar todos os idiomas ao mesmo
tempo é inócuo e mantém o pipeline determinístico.

### Detalhe técnico — resolução de cadeias

Alguns termos encadeiam (EN → intermediário PT → terminal). O mapa é
**pré-resolvido no carregamento** (`_resolve_chains`), com proteção contra
ciclos, de modo que o casamento em runtime seja um único passe e nunca "cresça"
por substring. Ex.: `cash and cash equivalents` → `caixa`.

## Resultado medido

Num conjunto de 20 linhas comuns de balanço/DRE em EN e ES:

| | Antes | Depois |
|--|------:|-------:|
| Casados (namespace + classe corretos) | **0/20** | **20/20** |

A cauda longa (termos não listados) continua indo para revisão — e pode ser
ampliada adicionando entradas ao dicionário, ou plugando o `ai_classifier`
(Plano B) como fallback multilíngue por LLM.

## Como estender

Edite `data/accounting_synonyms.json`, seções `phrase_en` / `phrase_es`
(chaves **sem pontuação**, valor = forma canônica PT que casa no referencial).
Nenhuma mudança de código é necessária.

## Arquivos

- alterado: `data/accounting_synonyms.json` — seções `phrase_en`, `phrase_es`
- alterado: `src/bp/utils/synonyms.py` — merge das seções por idioma + `_resolve_chains`
- alterado: `tests/test_synonyms.py` — testes EN/ES e de cadeia (`+3`)
