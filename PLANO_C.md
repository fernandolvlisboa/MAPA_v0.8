# Plano C — Desambiguação por Classe Contábil (Ativo/Passivo/Resultado)

Terceira camada de qualidade, sobre o Plano A (alvo referencial) e o Plano B
(sinônimos + desempate). Resolve o erro que nem o texto nem o nível sintético
conseguem evitar sozinhos: **casar uma conta na classe contábil errada**.

## Problema

`token_set_ratio` casa por texto; descrições parecidas podem viver em classes
opostas. Sem saber a classe da conta de origem, o matcher auto-aceitava, com
score alto:

- `CLIENTES` (Ativo) → `Adiantamentos de Clientes` (Passivo)
- `IRRF A RECOLHER` (Passivo) → conta do Ativo
- `PASSIVO NÃO CIRCULANTE` (Passivo) → `1.02` (Ativo)
- `PROVISÕES` (Passivo) → conta de Resultado

## Solução

A classe está no **dígito-raiz do código** — tanto na origem quanto no
referencial:

| Raiz do código | Classe |
|----------------|--------|
| `1`            | ATIVO |
| `2`            | PASSIVO / PL |
| `3`+ (origem `3..9`; referencial `3`) | RESULTADO (DRE) |

`classe_from_codigo()` (em `conta_matcher.py`) deriva a classe; retorna `None`
quando o código não começa por dígito (alguns balancetes usam códigos
textuais), caso em que **nenhuma restrição é aplicada** — a heurística é segura
por construção.

No `ContaMatcher`, quando a classe da origem é conhecida e o candidato é de
outra classe, o score é multiplicado por `0.5` — o que o joga para longe do
auto-accept (0.85), enviando-o para a classe correta ou para revisão. Aplicado
nas duas vias (fuzzy e heurística).

A classe é propagada automaticamente a partir do `codigo` de origem no
treinador (`trainer.py`), no exportador (`xlsx_exporter.py`) e no
`match_batch`. Também pode ser passada explicitamente:
`matcher.match(desc, codigo_origem="2.1.01")` ou `matcher.match(desc,
classe="PASSIVO")`.

## Efeito medido

A mesma descrição passa a rotear pela classe da origem:

| Descrição | Origem | Resultado |
|-----------|--------|-----------|
| `Clientes` | Ativo (`1.1.02`) | **revisão** (não há "clientes" no ativo do referencial) |
| `Clientes` | Passivo (`2.1.05`) | `2.01.01.05.01 Adiantamentos de Clientes` |
| `Fornecedores` | Passivo (`2.1.01`) | `2.01.01.03 FORNECEDORES – CIRCULANTE` |

**Contaminação cross-class eliminada:** no corpus, sob o Plano B (sem classe),
**280 de 1.240 auto-matches (22,6%) casavam na classe errada**. O Plano C
elimina 100% desses casos.

| Métrica (cold, referencial) | Plano B | Plano C |
|-----------------------------|--------:|--------:|
| Auto-match bruto            | 29,0%   | 25,6%   |
| Auto-matches **cross-class**| 22,6%   | **0%**  |

Como nas etapas anteriores, a taxa bruta cai — porque os matches removidos eram
**confiantemente errados**. A métrica que importa (match na classe certa)
melhora: 100% dos auto-matches agora respeitam Ativo/Passivo/Resultado.

## Arquivos

- alterado: `src/bp/matchers/conta_matcher.py` — `classe_from_codigo()`,
  parâmetros `classe`/`codigo_origem` em `match()`, penalidade cross-class em
  `_fuzzy_match` e `_apply_heuristics`
- alterado: `src/bp/training/trainer.py` — propaga `codigo_origem`
- alterado: `src/bp/exporters/xlsx_exporter.py` — propaga `codigo_origem`
- alterado: `tests/test_matchers.py` — testes de classe (`+3`)

## Limite conhecido / próximo passo

A classe só é derivada quando o código de origem é **numérico**. Balancetes com
códigos textuais (ex.: alguns exportados sem hierarquia) não recebem a
restrição. Próximo passo possível: inferir a classe pela **posição/hierarquia**
(seção do balancete) quando o código não for numérico.
