# Migração do Template GT — correção do alinhamento de anos

**Data:** agosto/2026
**Script:** `scripts/fix_template_year_alignment.py`
**Arquivo alterado:** `templates/Template_GT_BP_Padrao_v3.xlsx`

---

## 1. O que estava errado

As fórmulas de `BP_GT`/`DRE_GT` somavam a coluna de valores da aba oculta
**uma posição à frente** do que o cabeçalho declarava:

| Coluna do BP_GT | Rótulo | Lia da aba de dados | Que na verdade era |
|---|---|---|---|
| D | 2021 | `_dados_padronizados!D` | **2022** |
| E | 2022 | `!E` | 2023 |
| F | 2023 | `!F` | 2024 |
| G | 2024 | `!G` | **2025** |
| H | 2025 | `!H` | *(coluna inexistente — sempre zero)* |

Efeitos práticos:

- a coluna `C` da aba de dados (2021) **não era lida por ninguém**;
- a coluna de 2025 no relatório **ficava sempre vazia**;
- todo valor aparecia **deslocado um exercício**.

`docs/TEMPLATE_GT_BP.md` §4.1 define `C=2021 … G=2025`, portanto os cabeçalhos
estavam certos e as **fórmulas** é que precisavam andar uma coluna à esquerda.

## 2. O que foi feito

`D:D → C:C`, `E:E → D:D`, `F:F → E:E`, `G:G → F:F`, `H:H → G:G`, aplicado
**apenas ao primeiro argumento do SUMIFS** (a faixa somada). A faixa de
critério `$A:$A` (códigos) **não foi tocada**.

**220 fórmulas** alteradas — inclui as linhas de união do DRE, onde uma célula
tem até 8 `SUMIFS` somados.

## 3. Verificação (o que foi conferido)

### 3.1 Alinhamento — antes e depois

```
ANTES                                          DEPOIS
[ERRO] BP_GT!D (2021) -> dados!D = 2022        [OK] BP_GT!D (2021) -> dados!C = 2021
[ERRO] BP_GT!E (2022) -> dados!E = 2023        [OK] BP_GT!E (2022) -> dados!D = 2022
[ERRO] BP_GT!F (2023) -> dados!F = 2024        [OK] BP_GT!F (2023) -> dados!E = 2023
[ERRO] BP_GT!G (2024) -> dados!G = 2025        [OK] BP_GT!G (2024) -> dados!F = 2024
[ERRO] BP_GT!H (2025) -> dados!H = (vazia)     [OK] BP_GT!H (2025) -> dados!G = 2025
(idem DRE_GT)                                  (idem DRE_GT)
```

Reproduza a qualquer momento:

```bash
python scripts/fix_template_year_alignment.py --verify
```

### 3.2 Integridade — nada além das fórmulas mudou

Comparação célula a célula entre o backup e o arquivo corrigido:

| Verificação | Resultado |
|---|---|
| Abas (nomes e ordem) | idênticas |
| Fórmulas de valor alteradas | 220 (o esperado) |
| **Outras células alteradas** | **0** |
| **Diferenças de formatação** (fonte, preenchimento, formato numérico) | **0** |
| Faixas de critério `$A:$A` | intactas (8 de 8 na união do DRE) |
| Totalizadores (`=SUM(D9:D14)`, `=D15+D24`, …) | intactos |
| Check `=IF(ROUND(D26-D52,2)=0,…)` | intacto |

### 3.3 Ponta a ponta — com dados reais

Série de 4 exercícios (2018-2021), um arquivo por ano:

```
ano     linhas   escrito        capturado      órfãs
2018      52      250.182,1      250.182,1       0
2019     117      126.665,1      126.665,1       0
2020     122   11.692.943,9   11.692.943,9       0
2021     215  165.621.987,9  165.621.987,9       0

ALINHAMENTO: OK — cada ano lê sua própria coluna
RESULTADO: TUDO CAPTURADO, ZERO ÓRFÃS
```

Coberto por teste de regressão: `tests/test_gt_output.py::test_template_alinhado_ano_a_ano`.

> O recálculo pelo LibreOffice não conclui neste ambiente (perfil frio, estoura
> 300s), então a verificação replica a semântica do `SUMIFS` em Python. Ao
> abrir no Excel os valores aparecem calculados normalmente.

---

## 4. Como voltar atrás

Três caminhos, do mais simples ao mais completo. **Qualquer um resolve.**

### Opção A — restaurar do backup automático (mais rápido)

O script grava `templates/Template_GT_BP_Padrao_v3.xlsx.bak` antes de escrever.

```bash
cp templates/Template_GT_BP_Padrao_v3.xlsx.bak \
   templates/Template_GT_BP_Padrao_v3.xlsx

python scripts/fix_template_year_alignment.py --verify   # deve voltar a acusar ERRO
```

### Opção B — restaurar do git (recomendada)

O template está versionado. Para voltar à versão anterior à correção:

```bash
# ver o histórico do arquivo
git log --oneline -- templates/Template_GT_BP_Padrao_v3.xlsx

# restaurar a versão do commit ANTERIOR à correção
git checkout 2c9c953 -- templates/Template_GT_BP_Padrao_v3.xlsx
```

`2c9c953` é o commit "Plano H", que trouxe o template original.

### Opção C — reverter o commit inteiro

Desfaz a correção **e** as mudanças de código que dependem dela:

```bash
git log --oneline          # localize o commit da migração
git revert <hash>
```

### Depois de reverter — atenção

O código em `src/bp/output/build_gt_output.py` **descobre o mapeamento
ano→coluna lendo as próprias fórmulas** (`_slots_de_ano`). Ele continua
funcionando com o template desalinhado: vai escrever nas colunas que as
fórmulas de fato leem. Ou seja, **reverter o template não quebra o programa** —
só volta a exibir os anos deslocados em relação ao cabeçalho.

Se quiser reverter também o comportamento de anos flexíveis, use a Opção C.

---

## 5. Por que o código não depende mais desta correção

`_slots_de_ano()` lê, para cada coluna de ano, qual coluna da aba de dados a
fórmula daquela coluna referencia. A escrita segue **a fórmula**, não o rótulo.

Consequências:

- se o template for reeditado no Excel e as colunas mudarem de lugar, o
  programa acompanha sozinho;
- a correção acima deixa de ser um pré-requisito e passa a ser o que é: o
  template exibindo o ano certo no cabeçalho certo.
