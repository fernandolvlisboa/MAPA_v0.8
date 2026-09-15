# Contrato de Exportação — BP System

**Versão:** 1.0  
**Data:** 2025-12-01  
**Status:** Draft (Requer Revisão)

---

## 📋 Visão Geral

Este documento define o **contrato de exportação** do sistema BP - a estrutura mínima e os critérios de validação que todo arquivo exportado deve atender.

**Objetivo:** Garantir que exports sejam consistentes, válidos e úteis, independente do formato de entrada (CSV/XLS/XLSX/PDF/TXT).

---

## 📊 Estrutura do Arquivo de Export (.XLSX)

### Abas Obrigatórias

O arquivo exportado deve conter no mínimo as seguintes abas:

#### 1. **Summary** (Resumo)
Métricas gerais do balancete processado.

**Colunas:**
- `Metric` (String): Nome da métrica
- `Value` (Variável): Valor da métrica

**Linhas Obrigatórias:**
| Métrica | Tipo | Validação |
|---------|------|-----------|
| Generated At | datetime | ISO 8601 format |
| Total Accounts | int | > 0 |
| Synthetic (Mappable) | int | >= 0 |
| Analytical (Detail) | int | >= 0 |
| Matched | int | >= 0 |
| Match Rate % (Synthetic) | float | 0.0 a 100.0 |
| Needs Review | int | >= 0 |
| Ignored | int | >= 0 |
| Rollup Discrepancies | int | >= 0 |

**Critérios de Sucesso:**
- ✅ `Total Accounts > 0` (pelo menos 1 conta extraída)
- ✅ `Synthetic + Analytical = Total Accounts`
- ✅ `Match Rate %` válido (0-100)

---

#### 2. **Accounts** (Contas)
Lista completa de todas as contas extraídas com metadados de matching e validação.

**Colunas Obrigatórias:**

| Coluna | Tipo | Pode ser NULL? | Validação |
|--------|------|----------------|-----------|
| `codigo_original` | String | ✅ Sim (flat structures) | Formato hierárquico (X.X.X) se presente |
| `descricao_original` | String | ❌ **NUNCA** | Não vazia, comprimento > 0 |
| `saldo` | Float | ❌ Não | Numérico válido |
| `nivel` | Integer | ❌ Não | >= 1 |
| `parent_id` | String | ✅ Sim | Código válido existente se presente |
| `is_analytical` | Boolean | ❌ Não | True/False |
| `match_codigo` | String | ✅ Sim | Código do plano de contas se matched |
| `match_descricao` | String | ✅ Sim | Descrição do plano se matched |
| `match_score` | Float | ❌ Não | 0.0 a 1.0 |
| `needs_review` | Boolean | ❌ Não | True/False |
| `ignored` | Boolean | ❌ Não | True/False |
| `saldo_calculado` | Float | ❌ Não | Soma dos filhos diretos |
| `rollup_diff` | Float | ❌ Não | saldo - saldo_calculado |
| `rollup_ok` | Boolean | ❌ Não | True se diff dentro da tolerância |

**Critérios de Validação:**
1. ✅ Nenhuma linha com `descricao_original` vazia
2. ✅ Todos os `saldo` são numéricos e válidos
3. ✅ `match_score` entre 0.0 e 1.0 para todas as linhas
4. ✅ Se `match_codigo` existe, `match_descricao` também existe
5. ✅ `is_analytical = True` → `match_codigo = NULL` (analíticas não são mapeadas)

---

#### 3. **Hierarchy** (Hierarquia)
Estrutura hierárquica das contas ordenada por código.

**Colunas Obrigatórias:**
- `codigo` (String): Código da conta
- `descricao` (String): Descrição
- `nivel` (Integer): Nível hierárquico
- `parent_id` (String | NULL): Código do pai
- `saldo` (Float): Saldo original
- `saldo_calculado` (Float): Soma dos filhos
- `diff` (Float): Diferença
- `ok` (Boolean): Validação de rollup

**Critérios:**
- ✅ Ordenação por código (crescente)
- ✅ Todas as relações pai-filho são válidas
- ✅ Contas raiz têm `parent_id = NULL`

---

#### 4. **Unmatched** (Não Mapeadas)
Contas que precisam revisão manual ou são analíticas.

**Colunas:**
- `codigo`
- `descricao`
- `saldo`
- `nivel`
- `is_analytical`
- `needs_review`
- `match_score`

**Critérios:**
- ✅ Contém TODAS contas com `needs_review = True`
- ✅ Contém TODAS contas com `is_analytical = True` (para visibilidade)
- ✅ Ordenado por `match_score` (crescente) para priorização

---

### Abas Opcionais (Recomendadas)

#### 5. **Variations** (Variações Aprendidas)
Histórico de variações de descrição aprendidas do treinamento.

**Fonte:** `src/bp/training/account_variations.json`

**Colunas:**
- `codigo`: Código do plano de contas
- `frequency`: Número de ocorrências
- `variations`: Lista de variações (limitado a 10 primeiras)

#### 6. **Synonyms** (Sinônimos)
Sinônimos aprendidos para termos contábeis.

**Fonte:** `src/bp/training/learned_patterns.json`

**Colunas:**
- `term`: Termo original
- `mapped_terms`: Termos mapeados (limitado a 15)

#### 7. **Validation** (Validação de Rollups)
Validação detalhada de saldos calculados vs originais.

**Colunas:**
- `codigo`
- `descricao`
- `saldo`
- `saldo_calculado`
- `diff`
- `rel_diff_%`
- `ok`

**Critérios:**
- ✅ Todas as discrepâncias acima da tolerância listadas
- ✅ `rel_diff_%` calculado corretamente

---

## ✅ Critérios Globais de Sucesso

### Nível 1: Básico (Mínimo Aceitável)
- [ ] Pelo menos **1 conta** extraída
- [ ] Todas as descrições **não vazias**
- [ ] Todos os saldos **numéricos válidos**
- [ ] Nenhuma **exceção durante export**
- [ ] Arquivo .xlsx gerado com **tamanho > 10KB**

### Nível 2: Funcional (Esperado)
- [ ] Pelo menos **50%** das contas sintéticas **matched**
- [ ] `Match Rate %` reportado corretamente
- [ ] Rollup calculado para contas hierárquicas
- [ ] Abas **Summary, Accounts, Hierarchy, Unmatched** criadas
- [ ] Formatação básica aplicada (headers em negrito, freeze panes)

### Nível 3: Excelência (Ideal)
- [ ] **>80%** das contas sintéticas matched
- [ ] Zero discrepâncias de rollup
- [ ] Todas as 7 abas criadas
- [ ] Formatação condicional (cores para needs_review, errors)
- [ ] Filtros automáticos habilitados
- [ ] Larguras de coluna ajustadas automaticamente

---

## 🔍 Validações por Etapa

### 1. Pós-Parse (Antes do Match)
```python
def validate_parsed_accounts(accounts: List[Dict]) -> ValidationResult:
    """Valida contas extraídas ANTES de passar para matcher"""
    
    errors = []
    warnings = []
    
    # CRÍTICO: Lista não vazia
    if not accounts:
        errors.append("No accounts extracted")
    
    # CRÍTICO: Todas têm descrição
    empty_desc = [i for i, a in enumerate(accounts) 
                  if not a.get('descricao', '').strip()]
    if empty_desc:
        errors.append(f"{len(empty_desc)} accounts with empty description")
    
    # CRÍTICO: Saldos válidos
    invalid_saldo = []
    for i, a in enumerate(accounts):
        try:
            float(a.get('saldo', 0))
        except (ValueError, TypeError):
            invalid_saldo.append(i)
    if invalid_saldo:
        errors.append(f"{len(invalid_saldo)} accounts with invalid saldo")
    
    # WARNING: Nível válido
    invalid_nivel = [i for i, a in enumerate(accounts) 
                     if not isinstance(a.get('nivel'), int) or a.get('nivel', 0) < 1]
    if invalid_nivel:
        warnings.append(f"{len(invalid_nivel)} accounts with invalid nivel")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )
```

### 2. Pós-Match (Antes do Export)
```python
def validate_matched_accounts(accounts: List[Dict]) -> ValidationResult:
    """Valida contas APÓS matching"""
    
    errors = []
    warnings = []
    
    # Validar scores
    invalid_scores = [i for i, a in enumerate(accounts)
                      if not (0.0 <= a.get('match_score', 0.0) <= 1.0)]
    if invalid_scores:
        errors.append(f"{len(invalid_scores)} accounts with invalid match_score")
    
    # Validar consistência match_codigo <-> match_descricao
    inconsistent = []
    for i, a in enumerate(accounts):
        has_codigo = a.get('match_codigo') is not None
        has_desc = a.get('match_descricao') is not None
        if has_codigo != has_desc:
            inconsistent.append(i)
    if inconsistent:
        errors.append(f"{len(inconsistent)} accounts with inconsistent match data")
    
    # Validar que analíticas NÃO estão matched
    analytical_matched = [i for i, a in enumerate(accounts)
                          if a.get('is_analytical') and a.get('match_codigo')]
    if analytical_matched:
        warnings.append(f"{len(analytical_matched)} analytical accounts were matched (should be NULL)")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )
```

### 3. Pós-Export (Validação do Arquivo)
```python
def validate_exported_file(xlsx_path: Path) -> ValidationResult:
    """Valida arquivo .xlsx gerado"""
    
    import openpyxl
    
    errors = []
    warnings = []
    
    # Arquivo existe e tem tamanho razoável
    if not xlsx_path.exists():
        errors.append("Export file not created")
        return ValidationResult(False, errors, warnings)
    
    if xlsx_path.stat().st_size < 10000:
        errors.append(f"Export file too small: {xlsx_path.stat().st_size} bytes")
    
    # Abas obrigatórias
    wb = openpyxl.load_workbook(xlsx_path)
    required_sheets = ['Summary', 'Accounts', 'Hierarchy', 'Unmatched']
    missing = [s for s in required_sheets if s not in wb.sheetnames]
    if missing:
        errors.append(f"Missing required sheets: {missing}")
    
    # Métricas Summary
    if 'Summary' in wb.sheetnames:
        summary = wb['Summary']
        total = summary['B3'].value
        if not total or total == 0:
            errors.append("Total Accounts is 0 in Summary")
    
    # Dados em Accounts
    if 'Accounts' in wb.sheetnames:
        accounts = wb['Accounts']
        if accounts.max_row < 2:
            errors.append("Accounts sheet has no data rows")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )
```

---

## 📐 Tolerâncias e Limites

### Rollup de Saldos
```python
TOLERANCIA_RELATIVA = 0.0005  # 0.05% diferença relativa
TOLERANCIA_ABSOLUTA = 0.01    # R$ 0.01 diferença absoluta

def rollup_is_ok(saldo_original: float, saldo_calculado: float) -> bool:
    """Valida se rollup está dentro da tolerância"""
    diff = abs(saldo_original - saldo_calculado)
    
    # Diferença absoluta muito pequena - OK
    if diff <= TOLERANCIA_ABSOLUTA:
        return True
    
    # Diferença relativa
    if saldo_original != 0:
        rel_diff = diff / abs(saldo_original)
        return rel_diff <= TOLERANCIA_RELATIVA
    
    # Saldo original zero mas calculado não - NOT OK
    return False
```

### Match Rate Mínimo
```python
MIN_MATCH_RATE_BASIC = 0.10      # 10% (básico)
MIN_MATCH_RATE_FUNCTIONAL = 0.50  # 50% (funcional)
MIN_MATCH_RATE_EXCELLENT = 0.80   # 80% (excelência)
```

---

## 🎯 Casos de Uso e Exemplos

### Caso 1: Estrutura Flat (sem códigos)
**Arquivo:** `Balancete Real Life.xlsx`

**Características:**
- Nenhuma coluna "Código"
- Apenas descrições e saldos
- `codigo_original = NULL` para todas contas
- `nivel = 1` para todas (flat)

**Validações Esperadas:**
- ✅ Total Accounts > 0
- ✅ Todas descrições não vazias
- ✅ `is_analytical` baseado apenas em padrões de descrição
- ✅ Matching funciona mesmo sem códigos
- ⚠️ Rollup não aplicável (todas no mesmo nível)

### Caso 2: Estrutura Hierárquica
**Arquivo:** `Balancete 072022 122022 - RBM.xlsx`

**Características:**
- Códigos hierárquicos (1.1.1.01, etc)
- Descrições completas
- Níveis calculados automaticamente
- Rollup aplicável

**Validações Esperadas:**
- ✅ Todos códigos no formato X.X.X...
- ✅ `nivel` corresponde ao count('.') + 1
- ✅ `parent_id` corretamente identificado
- ✅ Rollup calculado para todas contas sintéticas
- ✅ Discrepâncias reportadas em Validation

### Caso 3: CSV Simples
**Arquivo:** `1544 - BALANCETE 1222024.csv`

**Características:**
- Delimitador auto-detectado
- Possível BOM UTF-8
- Headers podem estar em linhas diferentes

**Validações Esperadas:**
- ✅ CSV parseado sem erro
- ✅ Colunas detectadas corretamente
- ✅ Encoding preservado

---

## 🚨 Erros Comuns e Como Prevenir

### Erro 1: Export Vazio (0 contas)
**Causa:** Parser falhou silenciosamente  
**Prevenção:** Validação `validate_parsed_accounts()` ANTES do matching  
**Ação:** Lançar `ValueError` com mensagem clara

### Erro 2: Descrições Vazias
**Causa:** Coluna errada detectada como "descrição"  
**Prevenção:** Validação de conteúdo durante `_find_description_column()`  
**Ação:** Rejeitar colunas com >50% valores vazios

### Erro 3: Saldos Não Numéricos
**Causa:** Strings com formatação (R$, vírgulas) não convertidas  
**Prevenção:** `_normalize_saldo()` mais robusto  
**Ação:** Regex para limpar strings antes de conversão

### Erro 4: Match Score Inválido
**Causa:** Matcher retornando valores fora do range  
**Prevenção:** Clamp score entre 0.0 e 1.0 no matcher  
**Ação:** Assert no teste de validação

### Erro 5: Rollup Divergente
**Causa:** Contas analíticas não filtradas corretamente  
**Prevenção:** Marcar `is_analytical` ANTES de calcular rollup  
**Ação:** Warning se divergência > tolerância

---

## 📝 Checklist de Revisão

Antes de aceitar um export como válido:

### Parse
- [ ] Total contas > 0
- [ ] Todas descrições não vazias
- [ ] Todos saldos numéricos
- [ ] Níveis válidos (>=1)

### Match
- [ ] Match scores entre 0.0 e 1.0
- [ ] Contas analíticas NÃO matched
- [ ] Match rate reportado corretamente
- [ ] Needs review identificados

### Export
- [ ] Arquivo .xlsx criado
- [ ] Tamanho > 10KB
- [ ] 4 abas obrigatórias presentes
- [ ] Summary com métricas válidas
- [ ] Accounts com dados
- [ ] Formatação aplicada

### Qualidade
- [ ] Match rate >= 50% (funcional)
- [ ] Rollup sem discrepâncias graves
- [ ] Nenhum erro crítico
- [ ] Warnings documentados

---

## 🔄 Versionamento do Contrato

| Versão | Data | Mudanças | Autor |
|--------|------|----------|-------|
| 1.0 | 2025-12-01 | Criação inicial do contrato | Sistema |

---

## 📌 Notas de Implementação

### Para Desenvolvedores
- Este contrato define o **"what"**, não o **"how"**
- Implementações podem variar desde que o contrato seja respeitado
- Validações devem ser **fail-fast** (errar cedo e claro)
- Warnings não bloqueiam export, apenas alertam

### Para QA/Testers
- Use este documento como base para testes E2E
- Todo export deve passar pelas 3 validações (parse, match, file)
- Casos de borda estão listados na seção "Casos de Uso"

### Para Usuários Finais
- Exports que atendem Nível 2 (Funcional) são aceitáveis para uso
- Nível 3 (Excelência) é ideal mas não obrigatório
- Contas em "Unmatched" requerem revisão manual via review wizard

---

**FIM DO CONTRATO**

> **IMPORTANTE:** Este é um documento VIVO. Revise e atualize conforme necessário para refletir requisitos de negócio e melhorias do sistema.
