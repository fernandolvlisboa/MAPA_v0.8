# Plano I — Anos flexíveis, multi-arquivo e correção do alinhamento

Três entregas que resolvem o mesmo tema: **qual ano vai em qual coluna**.

---

## 1. O bug: colunas de ano desalinhadas

As fórmulas de `BP_GT`/`DRE_GT` liam a aba de dados **uma coluna à frente** do
rótulo. A coluna 2021 dos dados não era lida por ninguém; a coluna 2025 do
relatório apontava para uma coluna inexistente e ficava sempre zero; tudo
aparecia deslocado um exercício.

**Impacto no que já tinha sido entregue:** o arquivo gerado no Plano H escrevia
2024 na coluna que o relatório exibia como 2023. Valores certos, ano errado.

Corrigido por `scripts/fix_template_year_alignment.py` — 220 fórmulas
deslocadas uma coluna à esquerda, com a faixa de critério `$A:$A` intacta.
Passo a passo da verificação e **três caminhos de rollback** em
[`docs/MIGRACAO_TEMPLATE.md`](docs/MIGRACAO_TEMPLATE.md).

### Integridade conferida célula a célula

| Verificação | Resultado |
|---|---|
| Fórmulas de valor alteradas | 220 (o esperado) |
| **Outras células alteradas** | **0** |
| **Diferenças de formatação** | **0** |
| Critérios `$A:$A`, totalizadores, checks | intactos |

---

## 2. Anos flexíveis

Os rótulos de ano são **texto literal** em três lugares (`BP_GT!D7:H7`,
`DRE_GT!D7:H7`, `_dados_padronizados!C1:G1`) e não entram em nenhuma fórmula —
o `SUMIFS` referencia colunas por posição. Logo, a faixa 2021-2025 nunca foi
uma restrição, só o default de fábrica.

`_aplicar_anos()` reescreve os rótulos conforme os anos realmente fornecidos e
**limpa os slots sobrando**, para o relatório não exibir exercício sem dado.

```python
build_gt_output("bal.xlsx", "saida.xlsx", ano_base=2019)
# rótulos: 2019 | (vazio) | (vazio) | (vazio) | (vazio)
```

---

## 3. Multi-arquivo, um por exercício

### Por que não multi-ano dentro de um arquivo

Os balancetes reais do corpus têm **todos** a mesma estrutura:

```
Código | Descrição | Saldo Anterior | Débito | Crédito | Saldo Atual
```

Isso **não são vários anos**. `Saldo Anterior` é a abertura do mesmo período;
`Débito`/`Crédito` são movimentação. **Um balancete = um exercício.**

Extrair "vários anos de um arquivo" custaria 1-2 dias e traria o pior tipo de
risco deste domínio: confundir a coluna `Débito` com um exercício produziria
uma demonstração **errada e silenciosa** — exatamente o que os Planos A-H
passaram a existir para eliminar.

### A forma correta

```python
build_gt_output([
    FonteBalancete("bal_2022.xlsx", 2022),
    FonteBalancete("bal_2023.xlsx", 2023),
    FonteBalancete("bal_2024.xlsx", 2024),
], "saida.xlsx")
```

Cada arquivo é parseado, casado e auditado **em separado**; o `Sumário` traz um
bloco por exercício (lidas / match / sem match), e `Contas Tratadas` e
`Contas Não Identificadas` ganham a coluna `ano`.

Validações que falham cedo: nenhuma fonte, dois arquivos para o mesmo
exercício, mais exercícios do que o template comporta, arquivo inexistente.

---

## 4. O código não depende mais do template estar alinhado

`_slots_de_ano()` descobre, **lendo as próprias fórmulas**, qual coluna de dados
cada coluna de ano soma. A escrita segue a fórmula, não o rótulo.

Verificado nos dois estados do template:

| Template | Resultado |
|---|---|
| Corrigido | tudo capturado, zero órfãs |
| **Desalinhado** (após rollback) | **tudo capturado, zero órfãs** |

Ou seja: **reverter o template não quebra o programa.** Coberto pelo teste
`test_resiste_a_template_desalinhado`, que gera um template deliberadamente
torto e confere que a saída continua íntegra.

---

## 5. Verificação ponta a ponta

Série de 4 exercícios, um arquivo por ano:

```
ano     linhas   escrito        capturado      órfãs
2018      52      250.182,1      250.182,1       0
2019     117      126.665,1      126.665,1       0
2020     122   11.692.943,9   11.692.943,9       0
2021     215  165.621.987,9  165.621.987,9       0

ALINHAMENTO: OK — cada ano lê sua própria coluna
RESULTADO: TUDO CAPTURADO, ZERO ÓRFÃS
```

`189 testes passando` (+8 novos).

---

## 6. Sobre a pergunta no GUI

A ideia original era perguntar *"o arquivo tem vários anos ou serão vários
arquivos?"*. Pelos dados, para balancete a resposta é **sempre "vários
arquivos"** — a pergunta transfere ao usuário uma dúvida que o programa já
resolve.

Desenho sugerido: o usuário solta N arquivos e o programa **propõe o exercício
de cada um**, deduzindo do nome (`Balancete ASP 2023`, `01012024-31122024`) ou
do conteúdo; o usuário só confirma. Menos pergunta, menos erro. A API já está
pronta para isso — `FonteBalancete(path, ano)` é exatamente o par que a tela
precisa devolver.

---

## Arquivos

- novo: `scripts/fix_template_year_alignment.py` (migração, com `--dry-run` e `--verify`)
- novo: `docs/MIGRACAO_TEMPLATE.md` (verificação + 3 caminhos de rollback)
- alterado: `templates/Template_GT_BP_Padrao_v3.xlsx` (220 fórmulas)
- alterado: `src/bp/output/build_gt_output.py` (`FonteBalancete`, `_slots_de_ano`, `_aplicar_anos`)
- alterado: `tests/test_gt_output.py` (+8 testes)
