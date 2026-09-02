# 🎯 Matchers — o mecanismo de classificação

> **Reuso natural:** qualquer padronização de dados que venham em formatos diferentes contra uma referência única. O matcher é agnóstico: você diz o alvo, ele classifica o que chega.

O problema que este módulo resolve: você tem uma lista de descrições que os clientes usam (`"BENS NUMERARIOS"`, `"CAIXA GERAL"`, `"DISPONIBILIDADES EM MOEDA NACIONAL"`) e precisa amarrar cada uma a um item do seu **plano-alvo** (`"1.01.01.01 — Caixa e Equivalentes"`). Fazer isso manualmente é insustentável quando os dados chegam em escala. Este módulo faz isso automaticamente, com escala de confiança, e sabe **quando pedir ajuda**.

---

## O caminho comum: `.match(descricao)`

```python
from src.bp.matchers import ContaMatcher
from src.bp.generators.plano_contas import PlanodeContas

plano = PlanodeContas("data/plano_referencial.json")
matcher = ContaMatcher(plano)

r = matcher.match("BENS NUMERARIOS")

if r.decision:
    print(f"{r.decision.codigo} — {r.decision.descricao}")
    print(f"score {r.decision.score:.2f}, veio de {r.decision.source}")
else:
    print("Precisa revisão. Top 3 candidatos:")
    for c in r.candidates[:3]:
        print(f"  {c.codigo} — {c.descricao} (score {c.score:.2f})")
```

**A regra de decisão:** o score varia entre 0 e 1. O matcher **aceita automaticamente** acima de `auto_accept_threshold` (default 0.85), **oferece candidatos** entre `requery_threshold` (0.60) e o auto-accept, e **desiste** abaixo disso — devolve `decision=None` e `needs_review=True`.

---

## O contrato

Três dataclasses. `MatchResult` é o que você recebe; `MatchDecision` e `MatchCandidate` são o que ele carrega.

```python
@dataclass
class MatchDecision:
    codigo: str         # o código do plano-alvo
    descricao: str      # a descrição canônica
    score: float        # 0.0 a 1.0
    source: Literal["fuzzy", "heuristic", "ai", "cache"]
    confidence: float
    method: str = ""    # "fuzzy_ratio", "synonym", "cached_decision", ...

@dataclass
class MatchCandidate:
    codigo: str
    descricao: str
    score: float
    tipo: str | None = None
    natureza: str | None = None
    nivel: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class MatchResult:
    query: str                             # a descrição que você pediu para casar
    decision: MatchDecision | None = None  # None quando precisa revisão
    candidates: list[MatchCandidate] = field(default_factory=list)  # top-N alternativas
    needs_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## Como decide

Uma cascata de estágios. O primeiro que fecha decide — os seguintes nem são consultados. Assim o caso comum é barato e o caso difícil é o único que paga o custo dos estágios pesados.

```
match(descricao)
  │
  ├─► 1. cache       — já vi essa descrição antes? Usa a mesma decisão.
  │
  ├─► 2. sinônimos   — expande via data/accounting_synonyms.json + variações aprendidas
  │                     (o que os learners escrevem em account_variations.json)
  │
  ├─► 3. fuzzy       — RapidFuzz normalizado; considera classe contábil (Ativo/Passivo/Resultado)
  │                     como filtro (ver Plano C) para não confundir contas homônimas
  │
  ├─► 4. heurísticas — palavras-chave, natureza, nível — desempata score parecido
  │
  └─► 5. IA (opcional) — quando `use_ai=True` e o resto ficou ambíguo, chama seu ai_classifier
```

---

## Plugue um LLM para desempate (opcional)

O matcher **não conhece nenhum provedor de IA**. Você passa uma função que recebe a descrição e os candidatos e devolve `MatchDecision` (ou `None` para desistir). Isso mantém o matcher testável e o cliente livre para escolher o modelo.

```python
def desempate_por_llm(descricao, candidatos, contexto):
    """Chame Claude, Ollama, GPT — o que quiser — e devolva um MatchDecision."""
    prompt = f"Qual destes códigos casa melhor com '{descricao}'?\n" + "\n".join(
        f"- {c.codigo}: {c.descricao}" for c in candidatos[:5]
    )
    resposta = seu_cliente_llm.completar(prompt)   # sua chamada aqui
    codigo, descricao = _extrair(resposta)
    return MatchDecision(codigo=codigo, descricao=descricao,
                         score=0.9, source="ai", confidence=0.9, method="llm")

matcher = ContaMatcher(plano, use_ai=True, ai_classifier=desempate_por_llm)
```

Se `use_ai=True` e `ai_classifier=None`, o matcher cai num stub que devolve `None` — útil para testes.

---

## Cache de decisões

Cada decisão pode ser gravada em disco (`data/match_cache.json` por default) — a próxima vez que a mesma descrição aparecer, o matcher devolve pelo cache em microssegundos, sem repetir a cascata. Você controla o caminho:

```python
matcher = ContaMatcher(plano, cache_path="/pasta/de/rede/match_cache_do_time.json")
```

Casos comuns:
- **Cache local**, para uma máquina só (default).
- **Cache compartilhado por pasta de rede** — todo mundo do time se beneficia das decisões dos outros. Cuidado: uma decisão errada gravada aqui vira erro para todos até você limpar.
- **Cache efêmero** (`cache_path=None` mais gerar em memória): útil quando a decisão do dia não deve influenciar as próximas.

---

## Como reaproveitar fora do MAPA

Esta camada **não sabe nada sobre balanço**. Ela sabe casar strings contra um catálogo de strings. Para levar para outra automação:

1. Copie `src/bp/matchers/`, `src/bp/utils/normalizer.py`, `src/bp/utils/synonyms.py` e `src/bp/generators/plano_contas.py`.
2. Descreva seu **plano-alvo** no mesmo formato JSON que o `PlanodeContas` espera (código, descrição, nível, natureza).
3. (Opcional) Escreva seu dicionário de sinônimos.
4. Instancie `ContaMatcher(seu_plano)` e chame `.match(descricao)`.

Alguns casos:

- **De-para de fornecedores** entre ERPs diferentes — mesma ideia, catálogo diferente.
- **Categorização de produtos** contra taxonomia interna.
- **Padronização de centros de custo** entre unidades de negócio.
- **NCM/CNAE inference** a partir de descrição livre.

---

## Arquivos-chave

| Arquivo | Papel |
|---|---|
| `conta_matcher.py` | `ContaMatcher` — a cascata inteira, os dataclasses e a API pública |
| `match_cache.py` | `MatchCache` — carrega/salva JSON, invalida entradas antigas |

Testes: [`tests/test_matchers.py`](../../../tests/test_matchers.py), [`tests/test_matching_complete.py`](../../../tests/test_matching_complete.py), [`tests/test_matching_quality.py`](../../../tests/test_matching_quality.py), [`tests/test_synonyms.py`](../../../tests/test_synonyms.py).

Fundamento arquitetural: [`../../../PLANO_B.md`](../../../PLANO_B.md) (qualidade), [`../../../PLANO_C.md`](../../../PLANO_C.md) (desambiguação por classe), [`../../../PLANO_D.md`](../../../PLANO_D.md) (multilíngue), [`../../../PLANO_G.md`](../../../PLANO_G.md) (classificador LLM).
