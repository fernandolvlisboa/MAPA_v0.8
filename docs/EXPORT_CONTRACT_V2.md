# Contrato de Exportação — BP System (VERSÃO 2)

**Versão:** 2.0  
**Data:** 2025-12-01  
**Status:** Revisão Conforme Especificação do Usuário

---

## 📋 Visão Geral

Este documento define o **contrato de exportação completo** do sistema BP, incorporando:
- **19 colunas obrigatórias** na aba Accounts
- **Suporte para controladora e controlada** (saldos separados)
- **Aba Original** com dados fonte preservados
- **Rastreabilidade completa** do pipeline (parse → match → export)

---

## 📊 Estrutura do Arquivo de Export (.XLSX)

### Abas Obrigatórias

O arquivo exportado deve conter **8 abas**:

1. **Summary** — Resumo executivo da exportação
2. **Accounts** — Lista completa de contas processadas (19 colunas obrigatórias)
3. **Hierarchy** — Visualização da estrutura hierárquica
4. **Unmatched** — Contas sintéticas não matcheadas (needs review)
5. **Variations** — Variações de descrição aprendidas
6. **Synonyms** — Sinônimos utilizados no matching
7. **Validation** — Resultados das validações de integridade
8. **Original** — Dados originais do arquivo fonte (tabela completa extraída)

---

## 📋 Aba "Accounts" — Colunas Obrigatórias

### Estrutura Completa (19 colunas)

**Colunas Sempre Presentes (1-5, 10-19):**

| # | Coluna | Tipo | Nullable | Descrição |
|---|--------|------|----------|-----------|
| 1 | `nivel` | int | ❌ No | Nível hierárquico (1, 2, 3...) |
| 2 | `codigo_original` | str | ✅ Yes | Código original da conta (extraído do arquivo fonte) |
| 3 | `codigo_alocado` | str | ✅ Yes | Código do plano de contas (resultado do matching) |
| 4 | `descricao_original` | str | ❌ No | Descrição original da conta (extraída do arquivo) |
| 5 | `descricao_plano_contas` | str | ✅ Yes | Descrição padronizada do plano de contas |
| 10 | `parent_id` | int | ✅ Yes | ID da conta pai (hierarquia) |
| 11 | `is_analytical` | bool | ❌ No | Se é conta analítica (folha) |
| 12 | `match_codigo` | str | ✅ Yes | Código matcheado (mesmo que `codigo_alocado`) |
| 13 | `match_descricao` | str | ✅ Yes | Descrição matcheada (mesmo que `descricao_plano_contas`) |
| 14 | `match_score` | float | ✅ Yes | Score de confiança do matching (0.0-1.0) |
| 15 | `needs_review` | bool | ❌ No | Se precisa revisão manual |
| 16 | `ignored` | bool | ❌ No | Se foi ignorada no matching |
| 17 | `saldo_somado` | float | ✅ Yes | Soma dos filhos (apenas contas sintéticas com filhos) |
| 18 | `rollup_diff` | float | ✅ Yes | Diferença saldo vs saldo_somado |
| 19 | `rollup_ok` | bool | ✅ Yes | Se rollup validou (diff < tolerância) |

**Colunas de Saldos — Controladora (quando aplicável, colunas 6-9):**

| # | Coluna | Tipo | Nullable | Descrição |
|---|--------|------|----------|-----------|
| 6 | `saldo_anterior_ctrl` | float | ✅ Yes | Saldo do exercício anterior (ou mais antigo disponível) |
| 9 | `saldo_atual_ctrl` | float | ✅ Yes | Saldo do exercício atual (ou mais recente disponível) |

**Colunas de Saldos — Controlada (quando aplicável, colunas 6-9):**

| # | Coluna | Tipo | Nullable | Descrição |
|---|--------|------|----------|-----------|
| 6 | `saldo_anterior_controlada` | float | ✅ Yes | Saldo do exercício anterior (ou mais antigo disponível) |
| 9 | `saldo_atual_controlada` | float | ✅ Yes | Saldo do exercício atual (ou mais recente disponível) |

**Colunas de Saldos — Balancetes de uma forma geral (quando aplicável):**

| # | Coluna | Tipo | Nullable | Descrição |
|---|--------|------|----------|-----------|
| 6 | `saldo_anterior` | float | ✅ Yes | Saldo do exercício anterior (ou mais antigo disponível) |
| 7 | `credito` | float | ✅ Yes | Movimentação a crédito do período |
| 8 | `debito` | float | ✅ Yes | Movimentação a débito do período |
| 9 | `saldo_atual` | float | ✅ Yes | Saldo do exercício atual (ou mais recente disponível) |

---

### Regras de Preenchimento das Colunas de Saldo

**Decisão Automática pelo Parser:**

1. **Arquivo de Controladora:**
   - Criar colunas: `saldo_anterior_ctrl`, `credito_ctrl`, `debito_ctrl`, `saldo_atual_ctrl`
   - Exemplo: `Real Life.xlsx` com 4 colunas de saldo

2. **Arquivo de Controlada:**
   - Criar colunas: `saldo_anterior_controlada`, `credito_controlada`, `debito_controlada`, `saldo_atual_controlada`
   - Exemplo: Balancete específico de subsidiária

3. **Arquivo Consolidado (ambas):**
   - Criar TODAS as 8 colunas (4 ctrl + 4 controlada)
   - Exemplo: Relatório consolidado de grupo empresarial

4. **Arquivo com Saldo Único (sem histórico):**
   - Criar apenas `saldo_atual_ctrl` (padrão para saldo único)
   - Outras colunas (anterior/credito/debito) = NULL
   - Exemplo: `1544.csv` com apenas coluna "valor"

5. **Arquivo sem Saldo Anterior:**
   - Usar o **exercício mais antigo disponível** como saldo_anterior
   - Se só há 1 período: saldo_anterior = NULL

6. **Arquivo sem Saldo Atual:**
   - Usar o **exercício mais recente disponível** como saldo_atual

---

### Redundâncias Intencionais (para clareza)

Algumas colunas contêm informações duplicadas propositalmente:

- `codigo_alocado` **==** `match_codigo` (redundância para clareza)
- `descricao_plano_contas` **==** `match_descricao` (redundância para clareza)

**Motivo:** Facilitar leitura do export sem necessidade de entender lógica interna.

---

## 📊 Aba "Summary" — Métricas Executivas

Resumo com métricas chave do processamento:

```
Arquivo Fonte: Real Life.xlsx
Data Processamento: 2024-01-15 10:30:45
Parser Utilizado: XlsxParser
---
Total de Contas: 234
Contas Sintéticas: 180
Contas Analíticas: 54
---
Matching:
  Matched: 150 (83.3% das sintéticas)
  Unmatched: 30 (16.7% das sintéticas)
  Needs Review: 30
  Ignored: 5
---
Validações:
  Rollup OK: 175 (97.2%)
  Rollup Failed: 5 (2.8%)
  Tolerância Relativa: 0.05%
  Tolerância Absoluta: R$ 0.01
---
Saldos Totais:
  Ativo: R$ 1,234,567.89
  Passivo: R$ -1,234,567.89
  Diferença: R$ 0.00 ✓
---
Tipo de Arquivo:
  Controladora: Sim
  Controlada: Não
  Colunas de Saldo: saldo_anterior_ctrl, credito_ctrl, debito_ctrl, saldo_atual_ctrl
```

**Validações Summary:**
- ✅ `Total de Contas > 0`
- ✅ `Sintéticas + Analíticas = Total`
- ✅ `Match rate` válido (0-100%)
- ✅ `Tipo de Arquivo` identificado corretamente

---

## 📊 Aba "Original" — Dados Fonte Preservados

**Objetivo:** Rastreabilidade completa — permite comparar dados processados com fonte original.

**Formato:**
- Extração "bruta" do parser (antes de transformações)
- Todas as colunas do arquivo fonte preservadas
- Ordem das linhas mantida (quando possível)
- Valores sem conversão/normalização

**Exemplo — Real Life.xlsx:**

| Código | Descrição | Saldo Anterior | Crédito | Débito | Saldo Atual |
|--------|-----------|----------------|---------|--------|-------------|
| 1 | ATIVO | 1000000.00 | 500000.00 | 0.00 | 1500000.00 |
| 1.1 | ATIVO CIRCULANTE | 800000.00 | 400000.00 | 0.00 | 1200000.00 |
| 1.1.1 | CAIXA E EQUIVALENTES | 50000.00 | 30000.00 | 0.00 | 80000.00 |

**Exemplo — RBM.xlsx:**

| Nivel | Descrição | Saldo Atual |
|-------|-----------|-------------|
| 1 | ATIVO | 1500000.00 |
| 2 | ATIVO CIRCULANTE | 1200000.00 |
| 3 | CAIXA | 80000.00 |

**Exemplo — 1544.csv:**

| conta | descricao | valor |
|-------|-----------|-------|
| 1 | Ativo Total | 234567.89 |
| 1.1 | Ativo Circulante | 123456.78 |

**Observações:**
- Útil para debug de parsing issues
- Permite verificar transformações aplicadas (codigo_alocado vs codigo_original)
- Essencial para auditoria e compliance
- **DEVE** preservar encoding original (UTF-8, Latin-1, etc)

---

## ✅ Critérios de Validação por Nível

### Nível 1: Básico (Mínimo Aceitável)

**Critério:** Export executou sem crash e gerou arquivo válido.

✅ **Validações Obrigatórias:**
- Arquivo Excel criado (existe no filesystem)
- Contém 8 abas: Summary, Accounts, Hierarchy, Unmatched, Variations, Synonyms, Validation, Original
- Aba "Accounts": Total de contas > 0
- Aba "Accounts": 19 colunas obrigatórias presentes (1-5, 10-19)
- Aba "Accounts": Colunas de saldo adequadas ao tipo (ctrl/controlada/ambas)
- Aba "Accounts": Todas `descricao_original` não vazias
- Aba "Accounts": Todos valores de saldo numéricos
- Aba "Original": Dados do arquivo fonte preservados

❌ **Falha se:**
- Arquivo não criado
- Qualquer aba obrigatória ausente
- Aba "Accounts" vazia (0 contas)
- Colunas obrigatórias ausentes
- Qualquer `descricao_original` vazia
- Qualquer saldo não-numérico
- Aba "Original" vazia

---

### Nível 2: Funcional (Esperado)

**Critério:** Matching funcionou e dados estão estruturados corretamente.

✅ **Validações Adicionais:**
- Todas 8 abas presentes e populadas
- Match rate ≥ 50% (das contas sintéticas)
- Todos `match_score` entre 0.0 e 1.0
- Contas analíticas NÃO têm `codigo_alocado`/`match_codigo`
- Consistência: `codigo_alocado` == `match_codigo`
- Consistência: `descricao_plano_contas` == `match_descricao`
- Hierarchy válida (`parent_id` correto)
- Rollup validation executada (`saldo_somado` preenchido)
- Colunas de saldo adequadas ao tipo de arquivo (ctrl/controlada)
- Aba "Original" corresponde ao arquivo fonte (mesmo número de linhas)

❌ **Falha se:**
- Qualquer aba obrigatória vazia
- Match rate < 50%
- `match_score` fora de range [0.0, 1.0]
- Conta analítica com `codigo_alocado`
- Inconsistência entre `codigo_alocado` e `match_codigo`
- `parent_id` inconsistente
- Colunas de saldo ausentes quando deveriam estar presentes
- Aba "Original" com número de linhas diferente do arquivo fonte

---

### Nível 3: Excelência (Ideal)

**Critério:** Alta qualidade de matching e validações rigorosas.

✅ **Validações Rigorosas:**
- Match rate ≥ 80%
- Rollup OK rate ≥ 95%
- Total Ativo + Total Passivo ≈ 0 (dentro de tolerância)
- `needs_review` ≤ 20% das sintéticas
- `ignored` ≤ 5% das sintéticas
- Todas 19 colunas obrigatórias consistentes
- Rastreabilidade completa: Original → Accounts (todas linhas mapeadas)
- Saldos coerentes: `saldo_anterior + credito - debito ≈ saldo_atual` (quando aplicável)

❌ **Falha se:**
- Match rate < 80%
- Rollup failures > 5%
- Desbalanceamento Ativo/Passivo significativo
- Inconsistências nos saldos de movimentação (quando aplicável)

---

## 🔍 Implementação dos Validadores

### 1. Validação Pós-Parse

**Executada:** Imediatamente após `ParseyCaller.parse()`

**Objetivo:** Garantir que parser extraiu dados minimamente válidos.

```python
from bp.validators import validate_parsed_accounts

def parse_and_validate(file_path: str) -> Tuple[List[Dict], pd.DataFrame]:
    parser = ParseyCaller(file_path)
    accounts, original_df = parser.parse()  # Retorna contas + DataFrame original
    
    # Validação crítica
    validation = validate_parsed_accounts(accounts)
    if not validation.valid:
        raise ValueError(f"Parse failed validation:\n{validation}")
    
    # Warnings não bloqueiam
    if validation.warnings:
        logger.warning(f"Parse warnings:\n{validation}")
    
    return accounts, original_df
```

**Validações:**
- ✅ Total accounts > 0
- ✅ Todas `descricao_original` não vazias
- ✅ Todos saldos numéricos
- ✅ Colunas obrigatórias presentes (descricao, saldo, nivel)
- ⚠️ Níveis válidos (int ≥ 1)
- ⚠️ Códigos hierárquicos (formato X.X.X quando presente)

---

### 2. Validação Pós-Matching

**Executada:** Após `ContaMatcher.match_all()`

**Objetivo:** Garantir que matching produziu dados consistentes.

```python
from bp.validators import validate_matched_accounts

def match_and_validate(accounts: List[Dict]) -> List[Dict]:
    matcher = ContaMatcher()
    matched_accounts = matcher.match_all(accounts)
    
    # Validação crítica
    validation = validate_matched_accounts(matched_accounts)
    if not validation.valid:
        raise ValueError(f"Matching failed validation:\n{validation}")
    
    # Log métricas
    logger.info(f"Match rate: {validation.metrics['match_rate_%']}%")
    logger.info(f"Needs review: {validation.metrics['needs_review']}")
    
    # Adicionar campos derivados (redundâncias intencionais)
    for account in matched_accounts:
        account['codigo_alocado'] = account.get('match_codigo')  # Redundância
        account['descricao_plano_contas'] = account.get('match_descricao')  # Redundância
        account['codigo_original'] = account.get('codigo')  # Preserva original
        account['descricao_original'] = account.get('descricao')  # Preserva original
    
    return matched_accounts
```

**Validações:**
- ✅ Match scores entre 0.0 e 1.0
- ✅ Consistência `match_codigo` <-> `match_descricao`
- ✅ Consistência `codigo_alocado` == `match_codigo`
- ✅ Consistência `descricao_plano_contas` == `match_descricao`
- ✅ Contas analíticas NÃO têm match
- ⚠️ Match rate ≥ 50% (warning se < 50%)

---

### 3. Validação Pós-Export

**Executada:** Após `export_balance_sheet_to_xlsx()`

**Objetivo:** Garantir que arquivo exportado está completo e correto.

```python
from bp.validators import validate_exported_file

def export_and_validate(
    accounts: List[Dict], 
    output_path: str,
    original_data: pd.DataFrame = None  # Dados originais do parser
) -> str:
    # Export (agora com aba Original)
    export_balance_sheet_to_xlsx(
        accounts, 
        output_path,
        original_data=original_data  # Passa dados originais
    )
    
    # Validação do arquivo gerado
    validation = validate_exported_file(output_path)
    if not validation.valid:
        raise ValueError(f"Export file validation failed:\n{validation}")
    
    logger.info(f"Export successful: {output_path}")
    logger.info(f"File size: {validation.metrics['file_size_kb']} KB")
    logger.info(f"Tabs: {validation.metrics['tabs']}")
    
    return output_path
```

**Validações:**
- ✅ Arquivo existe
- ✅ Todas 8 abas presentes
- ✅ Aba Accounts: 19 colunas obrigatórias presentes
- ✅ Aba Accounts: Dados consistentes (`codigo_alocado` == `match_codigo`)
- ✅ Aba Original: Dados fonte preservados
- ✅ Rollup validations executadas (`saldo_somado` preenchido)
- ✅ Totais Ativo/Passivo balanceados
- ⚠️ File size > 10 KB (se < 10 KB, provavelmente vazio)

---

## 🎯 Casos de Uso Completos

### Caso 1: Real Life.xlsx (Controladora com Histórico)

**Input:** Excel com 6 colunas [Código, Descrição, Saldo Anterior, Crédito, Débito, Saldo Atual]

**Características:**
- Códigos hierárquicos presentes (1, 1.1, 1.1.1)
- 4 colunas de saldo (histórico completo)
- Arquivo de **Controladora**

**Colunas Export:**
- Obrigatórias: 1-5, 10-19 (14 colunas)
- Saldos Controladora: 6-9 (`saldo_anterior_ctrl`, `credito_ctrl`, `debito_ctrl`, `saldo_atual_ctrl`)
- **Total: 19 colunas**

**Validações Específicas:**
- Níveis inferidos do código (nivel = count('.') + 1)
- `parent_id` baseado em código pai
- Rollup validado na hierarquia
- `codigo_original` preservado exatamente
- Aba Original: 6 colunas fonte preservadas
- Validação de movimentação: `saldo_anterior + credito - debito ≈ saldo_atual`

**Output Esperado:**
- Aba Accounts: 234 contas + 4 colunas ctrl
- Aba Original: Tabela fonte com 6 colunas
- Match rate ≥ 80%

---

### Caso 2: RBM.xlsx (Controladora sem Histórico)

**Input:** Excel com 3 colunas [Nivel, Descrição, Saldo Atual]

**Características:**
- Hierarquia explícita via coluna "Nivel"
- SEM códigos originais
- SEM saldo anterior/movimentações
- Arquivo de **Controladora** (padrão)

**Colunas Export:**
- Obrigatórias: 1-5, 10-19 (14 colunas)
- Saldos: Apenas `saldo_atual_ctrl` preenchido (6-9 com 3 NULL)
- **Total: 19 colunas**

**Validações Específicas:**
- `parent_id` baseado em sequência de níveis
- `codigo_original` = NULL
- Rollup validado mesmo sem códigos
- Aba Original: 3 colunas fonte

**Output Esperado:**
- Aba Accounts: 180 contas + apenas `saldo_atual_ctrl`
- Colunas `saldo_anterior_ctrl`, `credito_ctrl`, `debito_ctrl` = NULL
- Aba Original: 3 colunas (Nivel, Descrição, Saldo)
- Match rate ≥ 70%

---

### Caso 3: 1544.csv (Saldo Único)

**Input:** CSV com 3 colunas [conta, descricao, valor]

**Características:**
- Códigos hierárquicos na coluna "conta"
- Apenas um saldo (sem histórico)
- Tipo indefinido → usa colunas **ctrl** por padrão

**Colunas Export:**
- Obrigatórias: 1-5, 10-19 (14 colunas)
- Saldos: Apenas `saldo_atual_ctrl` preenchido
- **Total: 19 colunas**

**Validações Específicas:**
- Níveis inferidos do código
- Saldo único → `saldo_atual_ctrl`
- `saldo_anterior_ctrl`, `credito_ctrl`, `debito_ctrl` = NULL
- `codigo_original` preserva coluna "conta"
- Aba Original: 3 colunas CSV

**Output Esperado:**
- Aba Accounts: Todas contas + apenas `saldo_atual_ctrl`
- Aba Original: CSV completo (conta, descricao, valor)
- Match rate ≥ 75%

---

## 📐 Tolerâncias e Limites

### Rollup de Saldos
```python
TOLERANCIA_RELATIVA = 0.0005  # 0.05% diferença relativa
TOLERANCIA_ABSOLUTA = 0.01    # R$ 0.01 diferença absoluta

def rollup_is_ok(saldo: float, saldo_somado: float) -> bool:
    """Valida se rollup está dentro da tolerância"""
    diff = abs(saldo - saldo_somado)
    
    # Diferença absoluta muito pequena - OK
    if diff <= TOLERANCIA_ABSOLUTA:
        return True
    
    # Diferença relativa
    if saldo != 0:
        rel_diff = diff / abs(saldo)
        return rel_diff <= TOLERANCIA_RELATIVA
    
    # Saldo zero mas somado não - NOT OK
    return False
```

### Validação de Movimentação
```python
def movimento_is_ok(
    saldo_anterior: float,
    credito: float,
    debito: float,
    saldo_atual: float
) -> bool:
    """Valida equação contábil: Saldo Atual = Saldo Anterior + Crédito - Débito"""
    if any(v is None for v in [saldo_anterior, credito, debito, saldo_atual]):
        return True  # Não validar se dados incompletos
    
    calculado = saldo_anterior + credito - debito
    return rollup_is_ok(saldo_atual, calculado)
```

---

## 🚨 Prevenção de Erros Comuns

### Erro 1: Export Vazio (0 Contas)

**Problema:** Parser falha silenciosamente e retorna lista vazia

**Solução:**
```python
validation = validate_parsed_accounts(accounts)
if not validation.valid:
    raise ValueError(f"Parse failed: {validation.errors}")
if validation.metrics['total_accounts'] == 0:
    raise ValueError("Parser returned 0 accounts - likely corrupted file")
```

### Erro 2: Descrições Vazias

**Problema:** Parser retorna `{"descricao_original": "", "saldo": 100}`

**Solução:**
```python
# Validator já detecta isso
validation = validate_parsed_accounts(accounts)
if not validation.valid:
    # Errors incluem "accounts with empty description"
    raise ValueError(f"Parse validation failed: {validation.errors}")
```

### Erro 3: Colunas de Saldo Erradas

**Problema:** Arquivo de controladora exportado com colunas de controlada

**Solução:**
```python
# No parser: detectar tipo de arquivo automaticamente
def detect_account_type(df: pd.DataFrame) -> str:
    """Retorna: 'controladora', 'controlada', 'consolidado', 'unico'"""
    columns_lower = [c.lower() for c in df.columns]
    
    has_ctrl = any('controladora' in c or 'matriz' in c for c in columns_lower)
    has_controlada = any('controlada' in c or 'subsidiaria' in c for c in columns_lower)
    
    if has_ctrl and has_controlada:
        return 'consolidado'
    elif has_controlada:
        return 'controlada'
    elif has_ctrl:
        return 'controladora'
    else:
        # Padrão: se tem 4 colunas saldo, assume controladora
        # Se tem apenas 1 saldo, assume 'unico'
        return 'controladora' if len([c for c in columns_lower if 'saldo' in c]) > 1 else 'unico'
```

### Erro 4: Perda de Rastreabilidade

**Problema:** Não é possível comparar dados exportados com arquivo original

**Solução:**
```python
# Preservar DataFrame original no parser
class BaseParser:
    def parse(self) -> Tuple[List[Dict], pd.DataFrame]:
        raw_df = self._extract_raw_data()  # DataFrame original
        accounts = self._transform_to_accounts(raw_df)
        return accounts, raw_df

# No export
def export_balance_sheet_to_xlsx(
    accounts: List[Dict],
    output_path: str,
    original_data: pd.DataFrame = None
):
    # ... criar outras abas ...
    
    # Aba Original
    if original_data is not None:
        original_data.to_excel(writer, sheet_name='Original', index=False)
    else:
        logger.warning("No original data provided - Original tab will be empty")
```

---

## 📝 Checklist de Export Válido

### Parse ✓
- [ ] Total accounts > 0
- [ ] Todas `descricao_original` preenchidas
- [ ] Todos saldos numéricos
- [ ] Níveis válidos (int ≥ 1)
- [ ] `codigo_original` preservado (quando presente)
- [ ] DataFrame original capturado para aba Original

### Matching ✓
- [ ] Match rate ≥ 50%
- [ ] Match scores entre 0.0-1.0
- [ ] Analíticas não matcheadas
- [ ] `codigo_alocado` == `match_codigo` (consistência)
- [ ] `descricao_plano_contas` == `match_descricao` (consistência)
- [ ] `needs_review` identificados

### Export ✓
- [ ] Arquivo criado (> 10 KB)
- [ ] 8 abas presentes
- [ ] Aba Accounts: 19 colunas obrigatórias (1-5, 10-19 + saldos)
- [ ] Aba Accounts: Colunas de saldo adequadas (ctrl/controlada/ambas/unico)
- [ ] Aba Original: Dados fonte preservados (mesmo encoding)
- [ ] Hierarchy válida (`parent_id` correto)
- [ ] Rollup validado (`saldo_somado` preenchido)
- [ ] Totais balanceados (Ativo + Passivo ≈ 0)

### Qualidade ✓
- [ ] Match rate ≥ 80%
- [ ] Rollup OK ≥ 95%
- [ ] `needs_review` ≤ 20%
- [ ] `ignored` ≤ 5%
- [ ] Rastreabilidade: Original → Accounts (todas linhas mapeadas)
- [ ] Saldos coerentes: `saldo_anterior + credito - debito ≈ saldo_atual` (quando aplicável)

---

## 🔄 Versionamento do Contrato

| Versão | Data | Mudanças | Autor |
|--------|------|----------|-------|
| 1.0 | 2025-12-01 | Criação inicial do contrato | Sistema |
| 2.0 | 2025-12-01 | Especificação de 19 colunas obrigatórias, suporte controladora/controlada, aba Original | Usuário + Sistema |

---

**FIM DO CONTRATO V2**

> **IMPORTANTE:** Este documento define EXATAMENTE as 19 colunas obrigatórias que todo export deve conter. Validadores, exporters e testes E2E devem ser atualizados para refletir esta estrutura.
