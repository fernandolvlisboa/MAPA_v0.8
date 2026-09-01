# Projeto BP — Guia de Implementação para Claude Code

**Template de referência:** `Template_GT_BP_Padrao_v3.xlsx`
**Owner:** Fernando Lisboa | GT Valuation
**Público-alvo deste documento:** Claude Code (ou qualquer desenvolvedor que vá implementar o programa BP)

---

## 1. Visão geral — a abordagem híbrida

O programa BP roda em Python e faz **duas coisas separadas** que se combinam num único arquivo final:

**Parte A — Extração e padronização (código Python)**
- Recebe um arquivo financeiro do cliente (TXT, PDF, XLS, XLSX ou CSV)
- Extrai as contas contábeis com valores
- Mapeia cada conta do cliente para um código padronizado do plano ECF (L100A para Balanço, L300A para DRE)
- Gera um relatório intermediário com contas match e contas unmatched

**Parte B — Consolidação no template GT (arquivo Excel estático)**
- O template GT é um `.xlsx` pronto, com formatação, fórmulas, cores, blocos de análise já montados
- O programa **não recria** o template em código — apenas **alimenta** uma aba oculta com os dados extraídos
- As fórmulas SUMIFS do template resolvem sozinhas a agregação por código

**Por que híbrido?**
Separar o que é dinâmico (dados) do que é estático (formatação/estrutura) evita duas armadilhas comuns:
- Recriar formatação em código é frágil e caro de manter
- Deixar toda a lógica em Excel torna auditoria e versionamento impossíveis

O template é a **camada de apresentação**, o Python é a **camada de dados**.

---

## 2. Estrutura de arquivos esperada no repositório

```
BP/
├── templates/
│   └── Template_GT_BP_Padrao_v3.xlsx    # Template GT (não mexer via código)
├── data/
│   └── plano_master.xlsx                 # Plano ECF completo (referência)
├── src/
│   └── bp/
│       ├── parsers/                      # Parsers por formato
│       ├── mapping/                      # Lógica de mapeamento para códigos ECF
│       ├── output/
│       │   └── build_output.py           # Alimenta o template
│       └── main.py
├── output/                                # Arquivos gerados (gitignored)
└── docs/
    └── TEMPLATE_GT_BP.md                 # Este documento
```

---

## 3. O arquivo de saída final — estrutura das abas

O arquivo `.xlsx` gerado pelo programa deve conter **múltiplas abas em um único arquivo** (não gerar ZIP com vários arquivos):

| Aba | Origem | Finalidade |
|---|---|---|
| `_instrucoes` | Template | Documentação embutida |
| `BP_GT` | Template | Balanço Sintético — preenchido via fórmulas SUMIFS |
| `DRE_GT` | Template | DRE Sintética — preenchida via fórmulas SUMIFS |
| `Sumário` | **Programa cria** | Metadados: cliente, data-base, match rate, contagem de contas, timestamp |
| `Contas Tratadas` | **Programa cria** | Balancete completo padronizado (dados brutos com match) |
| `Contas Não Identificadas` | **Programa cria** | Contas do cliente sem match no plano ECF (para revisão manual) |
| `_dados_padronizados` | **Programa alimenta** (oculta) | Aba oculta que as fórmulas SUMIFS do template consultam |

**A ordem sugerida** (esquerda para direita nas abas): Sumário → BP_GT → DRE_GT → Contas Tratadas → Contas Não Identificadas → _instrucoes → _dados_padronizados (oculta).

---

## 4. Como alimentar `_dados_padronizados` — schema e regras

### 4.1 Schema da aba

| Coluna | Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|---|
| A | `codigo_padronizado` | Texto | **Sim** | Código ECF do plano oficial (ex: `1.01.01.02.01`, `3.01.01.07.01.02`) |
| B | `descricao_original` | Texto | Não | Descrição exata que veio do balancete do cliente (rastreabilidade) |
| C | `2021` | Número | Não | Valor em milhares de reais |
| D | `2022` | Número | Não | Valor em milhares de reais |
| E | `2023` | Número | Não | Valor em milhares de reais |
| F | `2024` | Número | Não | Valor em milhares de reais |
| G | `2025` | Número | Não | Valor em milhares de reais |

### 4.2 Regras de preenchimento

1. **Uma linha por conta do cliente.** NÃO consolidar antes de escrever — o template consolida via wildcard automaticamente. Se o cliente tem 3 contas bancárias, escreva 3 linhas com códigos `1.01.01.02.01`, `1.01.01.02.02`, `1.01.01.02.03`.

2. **Códigos no formato oficial ECF.** Números separados por pontos, sem espaços, sem hífens, sem descrição concatenada:
   - ✅ `"1.01.01.02.01"`
   - ❌ `"1.01.01.02.01 - Bancos"`
   - ❌ `"1.1.1.2.1"` (sem zeros de padding)
   - ❌ `"1,01,01,02,01"` (separador errado)

3. **Valores em milhares de reais.** Se o balancete do cliente vem em unidade cheia, dividir por 1.000 antes de escrever.

4. **Sinais preservados (convenção ECF):**
   - Ativos e receitas: **positivos**
   - Passivos, deduções, custos, despesas, depreciação, IRPJ/CSLL: **negativos**

5. **Contas sem match não vão para `_dados_padronizados`.** Vão para a aba `Contas Não Identificadas` para revisão manual pelo analista.

6. **Anos ausentes ficam vazios.** SUMIFS trata vazio como zero.

### 4.3 Exemplo de conteúdo

```
codigo_padronizado    descricao_original                  2021    2022      2023      2024      2025
1.01.01.02.01         Banco do Brasil c/c 12345-6         200     130       1.5       100       250
1.01.01.02.02         Itaú c/c 98765-4                    15      12        0.36      23        41
1.01.02.03.01         IPI a Recuperar                     0       5         10        15        20
2.01.01.03.01         Fornecedores Nacionais              80      120       160       200       300
3.01.01.01.01.04      Receita Venda Produto Próprio       0       15000     20000     30000     25000
3.01.01.07.01.02      Salários e Ordenados                0       -3500     -4200     -5100     -3800
3.02.01.01            IRPJ e CSLL Correntes               0       -800      -1200     -1500     -400
```

No BP_GT, a linha `Caixa e equivalentes de caixa` (código `1.01.01`) vai puxar automaticamente BB + Itaú = 145 em 2022.

---

## 5. Como o template funciona por dentro (para você entender, não mexer)

### 5.1 Coluna C do template — código ECF sintético

Cada linha analítica do BP_GT e DRE_GT tem, na **coluna C** (visível), um código ECF sintético — ex: `1.01.02.02` para "Contas a receber de clientes".

### 5.2 Fórmula SUMIFS com wildcard

Cada célula de valor tem:

```excel
=IFERROR(SUMIFS(_dados_padronizados!D:D,
                _dados_padronizados!$A:$A,
                $C<linha>&"*"), 0)
```

Traduzindo: "some tudo da coluna do ano onde o código na aba de dados começa com o código sintético desta linha do template."

**Efeito prático:** a linha `Contas a receber de clientes` (código `1.01.02.02`) captura automaticamente qualquer conta do cliente cujo código comece com `1.01.02.02` — incluindo `1.01.02.02.01`, `1.01.02.02.03`, etc.

### 5.3 Fórmula SUMIFS com união (quando aparece `|` no código)

Algumas linhas do template têm mais de um código separado por `|`. Ex: `Despesas com pessoal` tem código:
```
3.01.01.07.01.01|3.01.01.07.01.02|3.01.01.07.01.03|3.01.01.07.01.05|3.01.01.07.01.06|3.01.01.07.01.07|3.01.01.07.01.30|3.01.01.07.01.33
```

A fórmula gerada é uma soma de vários SUMIFS, um por prefixo. **O programa não precisa fazer nada especial por causa disso** — a fórmula já está pronta no template.

### 5.4 Totalizadores

- **Totalizadores de grupo** (Total do Ativo Circulante, Total do Passivo, etc.): fórmulas SUM sobre as linhas analíticas do grupo.
- **Totalizadores compostos** (Ativo Total, Receita Líquida, EBITDA, EBIT, Lucro Líquido, etc.): fórmulas específicas somando outros totalizadores.

Nada disso é responsabilidade do programa Python — está tudo no template.

### 5.5 Colunas auxiliares (não tocar)

- **Coluna I**: Ajuste pro-forma (vazio, preenchido manualmente pelo avaliador)
- **Coluna J**: Ajustado = último ano + ajuste (fórmula)
- **Coluna L**: Classificação GT (pré-preenchida: Caixa/Dívida, Capital de Giro, Fluxo de Caixa, Ativo/Passivo não Op.)
- **Colunas N/O**: Ajuste a Valor Justo (usado apenas em PPA)
- **Coluna Q**: Metodologia de Avaliação
- **Coluna S**: Para Copiar e Colar

---

## 6. Fluxo canônico em Python

```python
from openpyxl import load_workbook
from pathlib import Path
import shutil
from datetime import datetime

TEMPLATE = Path("templates/Template_GT_BP_Padrao_v3.xlsx")


def gerar_output(
    dados_padronizados: list[dict],
    contas_tratadas: list[dict],
    contas_nao_identificadas: list[dict],
    nome_cliente: str,
    data_base: str,
    output_path: Path,
):
    """
    dados_padronizados: lista de dicts com chaves:
        'codigo_padronizado' (str),
        'descricao_original' (str),
        '2021', '2022', '2023', '2024', '2025' (float ou None)
    contas_tratadas: balancete completo do cliente após tratamento
    contas_nao_identificadas: contas sem match
    nome_cliente: nome que vai na célula B4 de BP_GT e DRE_GT
    data_base: data-base do trabalho (ex: "2024-12-31")
    output_path: caminho do arquivo final
    """
    # 1. Copiar o template para o destino (nunca sobrescrever o original)
    shutil.copy(TEMPLATE, output_path)

    # 2. Abrir a cópia
    wb = load_workbook(output_path)

    # 3. Escrever nome do cliente nas células B4 de BP_GT e DRE_GT
    wb["BP_GT"]["B4"] = nome_cliente
    wb["DRE_GT"]["B4"] = nome_cliente

    # 4. Escrever os dados em _dados_padronizados
    ws = wb["_dados_padronizados"]
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row)

    for i, linha in enumerate(dados_padronizados, start=2):
        ws.cell(row=i, column=1, value=linha["codigo_padronizado"])
        ws.cell(row=i, column=2, value=linha.get("descricao_original", ""))
        ws.cell(row=i, column=3, value=linha.get("2021"))
        ws.cell(row=i, column=4, value=linha.get("2022"))
        ws.cell(row=i, column=5, value=linha.get("2023"))
        ws.cell(row=i, column=6, value=linha.get("2024"))
        ws.cell(row=i, column=7, value=linha.get("2025"))

    # 5. Criar abas dinâmicas (Sumário, Contas Tratadas, Contas Não Identificadas)
    _criar_aba_sumario(wb, nome_cliente, data_base, dados_padronizados,
                       contas_tratadas, contas_nao_identificadas)
    _criar_aba_contas_tratadas(wb, contas_tratadas)
    _criar_aba_nao_identificadas(wb, contas_nao_identificadas)

    # 6. Salvar
    wb.save(output_path)


def _criar_aba_sumario(wb, nome_cliente, data_base, dados_pad, contas_tratadas, nao_ident):
    """Aba de metadados do processamento."""
    if "Sumário" in wb.sheetnames:
        del wb["Sumário"]
    ws = wb.create_sheet("Sumário", 0)  # Primeira aba

    total_contas = len(contas_tratadas) + len(nao_ident)
    match_rate = len(contas_tratadas) / total_contas if total_contas else 0

    linhas = [
        ("Cliente:", nome_cliente),
        ("Data-base:", data_base),
        ("Processado em:", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("", ""),
        ("Total de contas lidas:", total_contas),
        ("Contas com match:", len(contas_tratadas)),
        ("Contas sem match:", len(nao_ident)),
        ("Match rate:", f"{match_rate:.1%}"),
        ("", ""),
        ("Linhas em _dados_padronizados:", len(dados_pad)),
    ]
    for i, (label, value) in enumerate(linhas, 1):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=value)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 40


def _criar_aba_contas_tratadas(wb, contas_tratadas):
    """Balancete completo do cliente com códigos mapeados."""
    if "Contas Tratadas" in wb.sheetnames:
        del wb["Contas Tratadas"]
    ws = wb.create_sheet("Contas Tratadas")

    headers = ["codigo_original", "descricao_original", "codigo_padronizado",
               "descricao_padronizada", "2021", "2022", "2023", "2024", "2025"]
    ws.append(headers)
    for conta in contas_tratadas:
        ws.append([conta.get(h) for h in headers])


def _criar_aba_nao_identificadas(wb, nao_identificadas):
    """Contas do cliente que não obtiveram match — para revisão manual."""
    if "Contas Não Identificadas" in wb.sheetnames:
        del wb["Contas Não Identificadas"]
    ws = wb.create_sheet("Contas Não Identificadas")

    headers = ["codigo_original", "descricao_original", "motivo_no_match",
               "2021", "2022", "2023", "2024", "2025"]
    ws.append(headers)
    for conta in nao_identificadas:
        ws.append([conta.get(h) for h in headers])
```

---

## 7. Regras críticas para o Claude Code

### NUNCA:

- **NUNCA** escrever nas abas `BP_GT` ou `DRE_GT` (exceto B4 para o nome do cliente). As fórmulas fazem o resto.
- **NUNCA** sobrescrever o template original (`templates/Template_GT_BP_Padrao_v3.xlsx`). Sempre copiar antes.
- **NUNCA** usar `load_workbook(..., data_only=True)` ao abrir o template para gerar output. Isso perde as fórmulas.
- **NUNCA** reformatar células do template. Formatação é sagrada.
- **NUNCA** consolidar contas antes de escrever em `_dados_padronizados`. O wildcard SUMIFS consolida sozinho.
- **NUNCA** escrever códigos com caracteres extras (espaços, hífens, descrição concatenada, aspas).
- **NUNCA** alterar a estrutura de colunas do template via código. Se precisar mudar, editar `.xlsx` no Excel e commitar.
- **NUNCA** apagar as abas `_instrucoes`, `BP_GT`, `DRE_GT` ou `_dados_padronizados` do arquivo copiado.
- **NUNCA** desocultar a aba `_dados_padronizados` no output final.

### SEMPRE:

- **SEMPRE** copiar o template para uma nova localização antes de escrever.
- **SEMPRE** escrever apenas em `_dados_padronizados` (exceto o B4 do cliente).
- **SEMPRE** escrever cada conta do cliente em uma linha separada.
- **SEMPRE** preservar sinais originais do ECF (passivos e despesas negativos).
- **SEMPRE** valores em milhares de reais.
- **SEMPRE** salvar o arquivo final com nome descritivo: `{cliente}_{data_base}.xlsx`.
- **SEMPRE** manter `descricao_original` preenchida como trilha de auditoria.
- **SEMPRE** limpar linhas antigas de `_dados_padronizados` antes de escrever (preservando o header linha 1).
- **SEMPRE** criar as abas `Sumário`, `Contas Tratadas` e `Contas Não Identificadas` no output final.

---

## 8. Validações que o programa deve fazer antes de salvar

1. **Todos os códigos são strings não vazias no formato ECF** (regex: `^\d+(\.\d+)*$`).
2. **Nenhum código contém espaços, hífens, descrição ou caracteres não numéricos** além dos pontos.
3. **Todos os valores numéricos são float ou int** (nunca string).
4. **Soma dos códigos iniciando com "1"** (Ativo) ≈ **soma dos códigos iniciando com "2"** (Passivo + PL) — tolerância de arredondamento. Se não bater, marcar output como potencialmente inconsistente e gerar warning no log.
5. **Total de linhas escritas > 0.** Se vazio, provavelmente o parser falhou — gerar erro.
6. **Nenhum código duplicado exato** (mesma linha escrita duas vezes). Se ocorrer, consolidar antes de escrever.

Se qualquer validação falhar, gerar log estruturado e prosseguir — o próprio template mostra `OK/NOK` no check "Ativo = Passivo + PL" para o analista.

---

## 9. Mapeamento de contas do cliente para códigos ECF

O parser precisa transformar o balancete do cliente (formato livre) em códigos ECF do plano oficial. Estratégias em ordem de prioridade:

1. **Match direto por código** — se o cliente já usa códigos ECF, usar direto (validando formato).
2. **Match por dicionário de sinônimos** — manter dicionário `descricao_variacao → codigo_ecf` alimentado ao longo do tempo pelo analista.
3. **Match por similaridade semântica** — para descrições novas, comparar contra plano oficial e sugerir o código com maior similaridade (analista valida antes de aceitar).
4. **Não match** — vai para aba `Contas Não Identificadas` para revisão manual.

**Fonte de verdade do mapeamento:** arquivo `data/plano_master.xlsx`, abas `L100A` (Balanço) e `L300A` (DRE), coluna `CÓDIGO`.

---

## 10. Como atualizar o template quando necessário

Se precisar adicionar uma linha nova ou ajustar mapeamento de código:

1. **Abrir o template no Excel** — nunca via código.
2. Editar coluna B (descrição) ou C (código ECF) da linha específica.
3. As fórmulas SUMIFS na linha continuam funcionando — usam `$C<linha>&"*"`.
4. Se adicionar linha nova dentro de um grupo, **ajustar o range do SUM do totalizador** correspondente.
5. Commitar com mensagem: `template: <descrição da mudança>`
6. **Versionamento**: mudança estrutural gera nova versão (`v3` → `v4`). Código Python aponta para versão atual em `templates/`.

---

## 11. Troubleshooting comum

**Valores aparecem zero mesmo com dados na aba de dados**
- Causa: código escrito com formato diferente do template (`1.1.1.02.01` em vez de `1.01.01.02.01`, ou com hífen).
- Solução: validar que o parser produz códigos no formato canônico ECF.

**Todas as linhas mostram zero**
- Causa: aba `_dados_padronizados` foi renomeada ou o arquivo foi salvo com openpyxl sem recalcular.
- Solução: verificar nome exato da aba (com underscore, minúscula); ao testar, forçar recálculo abrindo no Excel ou via LibreOffice headless.

**Fórmulas aparecem como texto**
- Causa: usou `data_only=True` ao abrir template.
- Solução: usar `load_workbook(path)` sem parâmetros extras.

**Aba `_dados_padronizados` não aparece no Excel**
- Correto — ela é oculta por design. Botão direito em qualquer aba → "Reexibir" para ver.

**Check "Ativo = Passivo + PL" retorna NOK**
- Causa: contas não mapeadas, sinais invertidos, ou dados incompletos do cliente.
- Solução: revisar aba `Contas Não Identificadas`; conferir convenção de sinais.

**Um valor aparece duplicado**
- Causa: conta mapeada para código muito genérico (ex: `1.01` em vez de `1.01.02.03.01`). Wildcard soma em todos os níveis intermediários.
- Solução: sempre usar código analítico completo (nível mais profundo) para cada conta.

---

## 12. Referências

- **Template:** `templates/Template_GT_BP_Padrao_v3.xlsx`
- **Plano oficial:** `data/plano_master.xlsx` (abas L100A e L300A)
- **Instrução Normativa RFB nº 2.004/2021** — Escrituração Contábil Fiscal (ECF)
- **Repositório GitHub:** [preencher URL quando criado]

---

## 13. Histórico de versões do template

**v3 (atual)** — Estrutura sintética para valuation baseada nos agrupadores L100A/L300A. Preserva identidade visual GT (fontes Century Gothic, cores roxo #4F2D7F e teal #00A7B5, blocos laterais de Classificação GT, Ajuste a Valor Justo, Metodologia, Para Copiar e Colar). Coluna A como respiro estreito, coluna B descrição, coluna C visível com código ECF, colunas D-H com anos, I e J com Ajuste/Ajustado. Fórmulas SUMIFS com wildcard e união por `|`.

**v2 (deprecada)** — Estrutura genérica L100A/L300A completa, mas sem identidade visual GT. Substituída pela v3.

**v1 (deprecada)** — Baseada em cliente específico (Dimensa Agger). Não genérica.

---

*Documento mantido por Fernando Lisboa. Última revisão: agosto/2026.*
